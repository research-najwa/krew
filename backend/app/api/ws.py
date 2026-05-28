"""WebSocket gateway for real-time chat & activity feed.

Auth: httpOnly cookie `krew_chat_jwt` (set by chat_login alongside the JSON
response) OR `?token=<jwt>` query param fallback. The cross-origin Next.js
dev setup can't always deliver the SameSite=Lax cookie on the WS upgrade
request, so we accept the token from the query string as well.

Outgoing envelope (v1):
    {"v": 1, "id": <ulid>, "type": <str>, "ts": <iso>, "ref": <str|None>, "payload": {...}}

Supported message types (v1):
    Server -> Client:
        - connection.ready
        - ping
        - chat.message.created   (user or assistant message persisted)
        - chat.tool.start        (agent tool execution started)
        - chat.tool.result       (agent tool execution completed)
        - chat.complete          (end of a chat turn)
        - error                  (non-fatal error surface)
    Client -> Server:
        - pong
        - chat.send              (request an agent response)

Anything else from the client is acknowledged silently for now; full event
registry comes in a later task.
"""
from __future__ import annotations

import asyncio
import json
import logging
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import JWTError, ExpiredSignatureError
from pydantic import BaseModel
from sqlalchemy import select, or_
from sqlalchemy.exc import IntegrityError

from app.auth.jwt import decode_token
from app.auth.token_blacklist import is_blacklisted
from app.config import get_settings
from app.database import async_session
from app.models.conversation import Conversation, Message, ConversationStatus
from app.models.employee import Employee, EmployeeStatus
from app.models.direct_message import DirectConversation, DirectMessage
from app.security.rate_limiter import get_redis

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter()


# ── Constants ──────────────────────────────────────────────────────
HEARTBEAT_INTERVAL_SEC = 25
HEARTBEAT_TIMEOUT_SEC = 10
IDLE_TIMEOUT_SEC = 30 * 60

# Close codes
WS_CLOSE_AUTH_REQUIRED = 4401
WS_CLOSE_HEARTBEAT_TIMEOUT = 4408
WS_CLOSE_IDLE_TIMEOUT = 4410


# ── Envelope ───────────────────────────────────────────────────────
class WsEnvelope(BaseModel):
    v: int = 1
    id: str
    type: str
    ts: str
    ref: str | None = None
    payload: dict = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    # Lightweight ulid-ish identifier — sortable + random suffix.
    return f"{int(time.time() * 1000):013d}{secrets.token_hex(6)}"


def _envelope(type_: str, payload: dict, ref: str | None = None) -> dict:
    return WsEnvelope(
        id=_new_id(),
        type=type_,
        ts=_now_iso(),
        ref=ref,
        payload=payload,
    ).model_dump()


# ── Connection manager ────────────────────────────────────────────
@dataclass
class _ConnectionManager:
    _conns: dict[str, set[WebSocket]] = field(default_factory=dict)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _send_locks: dict[str, asyncio.Semaphore] = field(default_factory=dict)

    async def register(self, user_id: str, ws: WebSocket) -> None:
        async with self._lock:
            self._conns.setdefault(user_id, set()).add(ws)
            if user_id not in self._send_locks:
                self._send_locks[user_id] = asyncio.Semaphore(1)

    async def unregister(self, user_id: str, ws: WebSocket) -> None:
        async with self._lock:
            bucket = self._conns.get(user_id)
            if not bucket:
                return
            bucket.discard(ws)
            if not bucket:
                self._conns.pop(user_id, None)
                self._send_locks.pop(user_id, None)

    def get_send_lock(self, user_id: str) -> asyncio.Semaphore:
        """Return per-user semaphore to serialize chat.send processing."""
        return self._send_locks.get(user_id) or asyncio.Semaphore(1)

    async def send_to_user(self, user_id: str, payload: dict) -> int:
        """Push an envelope dict to every live socket for a user. Returns count."""
        async with self._lock:
            sockets = list(self._conns.get(user_id, ()))
        sent = 0
        for ws in sockets:
            try:
                await ws.send_json(payload)
                sent += 1
            except Exception:
                logger.debug("ws send failed for user=%s", user_id, exc_info=True)
        return sent


manager = _ConnectionManager()


# ── Auth helper ───────────────────────────────────────────────────
async def _auth_from_cookie(token: str | None) -> Optional[dict]:
    if not token:
        return None
    try:
        payload = decode_token(token)
    except (JWTError, ExpiredSignatureError):
        return None
    if payload.get("type") != "chat":
        return None
    jti = payload.get("jti")
    if jti and await is_blacklisted(jti):
        return None
    if "sub" not in payload or "tenant_id" not in payload:
        return None
    return payload


# ── chat.send handler ────────────────────────────────────────────
async def _handle_chat_send(
    websocket: WebSocket,
    *,
    envelope: dict,
    employee_id: UUID,
    tenant_id: UUID,
) -> None:
    """Process an incoming chat.send envelope and stream results back.

    Mirrors the REST /chat endpoint flow (see app/api/chat.py): find/create the
    active web conversation, load history, dispatch to the orchestrator,
    persist both the user and the agent message, then emit envelopes.

    On orchestrator failure, emits an `error` envelope but keeps the socket
    open.
    """
    # Imported lazily to avoid a startup-time circular import and so tests can
    # monkeypatch app.agents.orchestrator.AgentOrchestrator before the first
    # chat.send arrives.
    from app.agents.orchestrator import AgentOrchestrator
    from app.security.rate_limiter import check_chat_rate_limit

    ref = envelope.get("id")
    raw_payload = envelope.get("payload") or {}
    text = (raw_payload.get("text") or "").strip()
    requested_agent = (raw_payload.get("agent") or "").strip()
    conv_id_raw = raw_payload.get("conversation_id")
    locale_override = (raw_payload.get("locale") or "").strip().lower() or None

    # Z1: Rate limit — same 20/min limit as REST chat endpoint
    try:
        await check_chat_rate_limit(str(employee_id))
    except Exception:
        await websocket.send_json(_envelope(
            "error",
            {"code": "rate_limited", "message": "Too many messages. Please wait a moment."},
            ref=ref,
        ))
        return

    # H2: Validate + sanitize chat message (length, empty, strip)
    from app.security.input_validator import validate_chat_message as _validate_msg
    try:
        text = _validate_msg(text)
    except Exception:
        await websocket.send_json(_envelope(
            "error",
            {"code": "invalid_payload", "message": "Message is empty or too long (max 4000 chars)."},
            ref=ref,
        ))
        return

    try:
        async with async_session() as db:
            # Load employee and enforce tenant isolation
            emp_result = await db.execute(
                select(Employee).where(
                    Employee.id == employee_id,
                    Employee.tenant_id == tenant_id,
                    Employee.status.in_([EmployeeStatus.active, EmployeeStatus.onboarding]),
                )
            )
            employee = emp_result.scalar_one_or_none()
            if employee is None:
                await websocket.send_json(_envelope(
                    "error",
                    {"code": "employee_not_found", "message": "Employee not found"},
                    ref=ref,
                ))
                return

            # Resolve conversation (resume by id, or most-recent active, or create)
            conversation: Conversation | None = None
            if conv_id_raw:
                try:
                    conv_uuid = UUID(str(conv_id_raw))
                except ValueError:
                    await websocket.send_json(_envelope(
                        "error",
                        {"code": "invalid_conversation_id", "message": "Invalid conversation_id"},
                        ref=ref,
                    ))
                    return
                conv_result = await db.execute(
                    select(Conversation).where(
                        Conversation.id == conv_uuid,
                        Conversation.employee_id == employee_id,
                        Conversation.tenant_id == tenant_id,
                    )
                )
                conversation = conv_result.scalar_one_or_none()
                if conversation is None:
                    await websocket.send_json(_envelope(
                        "error",
                        {"code": "conversation_not_found", "message": "Conversation not found"},
                        ref=ref,
                    ))
                    return
                if conversation.status == ConversationStatus.resolved:
                    conversation.status = ConversationStatus.active
                    conversation.resolved_at = None

            if conversation is None:
                conv_result = await db.execute(
                    select(Conversation).where(
                        Conversation.employee_id == employee_id,
                        Conversation.tenant_id == tenant_id,
                        Conversation.channel == "web",
                        Conversation.status == ConversationStatus.active,
                    ).order_by(Conversation.id.desc()).limit(1)
                )
                conversation = conv_result.scalar_one_or_none()

            if conversation is None:
                conversation = Conversation(
                    tenant_id=tenant_id,
                    employee_id=employee_id,
                    agent_name=requested_agent or "pending",
                    channel="web",
                    language=employee.preferred_language,
                )
                db.add(conversation)
                try:
                    await db.flush()
                except IntegrityError:
                    await db.rollback()
                    conv_result = await db.execute(
                        select(Conversation).where(
                            Conversation.employee_id == employee_id,
                            Conversation.tenant_id == tenant_id,
                            Conversation.channel == "web",
                            Conversation.status == ConversationStatus.active,
                        ).order_by(Conversation.id.desc()).limit(1)
                    )
                    conversation = conv_result.scalar_one_or_none()
                    if conversation is None:
                        await websocket.send_json(_envelope(
                            "error",
                            {"code": "conversation_error", "message": "Could not create conversation."},
                            ref=ref,
                        ))
                        return

            # H1: Block if conversation is escalated to a human
            if conversation.status == ConversationStatus.escalated:
                escalated_msg = (
                    "Your conversation has been escalated to a human HR specialist. "
                    "Please wait for their reply.\n\n"
                    "تم تصعيد محادثتك إلى أخصائي موارد بشرية. يرجى انتظار ردهم."
                )
                await websocket.send_json(_envelope(
                    "chat.message.created",
                    {
                        "conversation_id": str(conversation.id),
                        "message_id": _new_id(),
                        "role": "assistant",
                        "agent": "system",
                        "text": escalated_msg,
                        "created_at": _now_iso(),
                    },
                    ref=ref,
                ))
                await websocket.send_json(_envelope(
                    "chat.complete",
                    {"conversation_id": str(conversation.id), "message_id": _new_id()},
                    ref=ref,
                ))
                return

            # Load history for the orchestrator
            msg_result = await db.execute(
                select(Message)
                .where(
                    Message.conversation_id == conversation.id,
                    Message.role.in_(["employee", "agent"]),
                )
                .order_by(Message.created_at.desc())
                .limit(20)
            )
            history = [
                {
                    "role": "user" if m.role == "employee" else "assistant",
                    "content": m.content,
                }
                for m in reversed(msg_result.scalars().all())
            ]

            # Derive role/dept for access control (same helpers chat.py uses)
            from app.utils.employee_role import derive_employee_role
            employee_role = await derive_employee_role(db, tenant_id, employee_id)
            employee_dept_id = employee.department_id

            stored_agent = conversation.agent_name
            current_agent = requested_agent if requested_agent else (
                stored_agent if stored_agent != "pending" else None
            )
            last_mentioned = getattr(conversation, "last_mentioned_agent", None)

            orchestrator = AgentOrchestrator(db, tenant_id)
            try:
                agent_name, response_text, new_last_mentioned = await orchestrator.handle_message(
                    message=text,
                    employee_name=employee.first_name,
                    employee_id=str(employee.id),
                    conversation_history=history,
                    current_agent=current_agent,
                    language=employee.preferred_language,
                    conversation_id=conversation.id,
                    last_mentioned_agent=last_mentioned,
                    employee_role=employee_role,
                    employee_dept_id=employee_dept_id,
                )
            except Exception as exc:
                import uuid as _erruuid
                correlation_id = str(_erruuid.uuid4())[:8]
                logger.exception("orchestrator failed in ws chat.send [%s]", correlation_id)
                await db.rollback()
                err_type = type(exc).__name__
                if "quota" in str(exc).lower() or "rate" in str(exc).lower():
                    user_msg = "The AI service is temporarily at capacity. Please try again in a moment."
                elif "timeout" in err_type.lower() or "timeout" in str(exc).lower():
                    user_msg = "The request took too long. Please try a simpler question or try again."
                else:
                    user_msg = "Something went wrong processing your request. Please try again."
                await websocket.send_json(_envelope(
                    "error",
                    {
                        "code": "agent_error",
                        "message": user_msg,
                        "ref": correlation_id,
                    },
                    ref=ref,
                ))
                return

            # Snapshot fields we need AFTER a potential rollback (rollback expires ORM state).
            conv_id = conversation.id
            conv_lang = locale_override if locale_override in ("ar", "en") else employee.preferred_language
            topic_to_set = None
            if not conversation.topic:
                clean = text.replace("\n", " ").strip()
                topic_to_set = clean if len(clean) <= 50 else clean[:50].rsplit(" ", 1)[0] + "..."

            conversation.agent_name = agent_name
            conversation.last_mentioned_agent = new_last_mentioned
            if topic_to_set:
                conversation.topic = topic_to_set

            user_msg = Message(
                conversation_id=conv_id,
                role="employee",
                content=text,
                channel="web",
                language=conv_lang,
                agent_name=agent_name,
            )
            agent_msg = Message(
                conversation_id=conv_id,
                role="agent",
                content=response_text,
                channel="web",
                language=conv_lang,
                agent_name=agent_name,
            )
            db.add(user_msg)
            db.add(agent_msg)
            try:
                await db.commit()
                await db.refresh(user_msg)
                await db.refresh(agent_msg)
            except Exception:
                # Tool calls may have poisoned the current transaction. Roll back and
                # persist the messages in a fresh session so the chat turn still
                # completes gracefully (the orchestrator's text response is already
                # a graceful error like "I had a technical problem").
                logger.warning("primary commit failed, retrying in fresh session", exc_info=True)
                await db.rollback()
                async with async_session() as fresh_db:
                    # Also update the conversation state in the fresh session
                    fresh_conv = await fresh_db.get(Conversation, conv_id)
                    if fresh_conv is not None:
                        fresh_conv.agent_name = agent_name
                        fresh_conv.last_mentioned_agent = new_last_mentioned
                        if topic_to_set and not fresh_conv.topic:
                            fresh_conv.topic = topic_to_set
                    fresh_user = Message(
                        conversation_id=conv_id,
                        role="employee",
                        content=text,
                        channel="web",
                        language=conv_lang,
                        agent_name=agent_name,
                    )
                    fresh_agent = Message(
                        conversation_id=conv_id,
                        role="agent",
                        content=response_text,
                        channel="web",
                        language=conv_lang,
                        agent_name=agent_name,
                    )
                    fresh_db.add(fresh_user)
                    fresh_db.add(fresh_agent)
                    await fresh_db.commit()
                    await fresh_db.refresh(fresh_user)
                    await fresh_db.refresh(fresh_agent)
                    user_msg = fresh_user
                    agent_msg = fresh_agent

            conv_id_str = str(conv_id)
            user_created_at = user_msg.created_at.isoformat() if user_msg.created_at else _now_iso()
            agent_created_at = agent_msg.created_at.isoformat() if agent_msg.created_at else _now_iso()

        # Extract tool call data from the agent instance (if available)
        tool_events: list[dict] = []
        _agent_instance = getattr(orchestrator, "last_agent", None)
        _tc_count = len(getattr(_agent_instance, "_last_tool_calls", [])) if _agent_instance else 0
        if _agent_instance is not None:
            from app.agents.tool_registry import find_by_function
            for tc in getattr(_agent_instance, "_last_tool_calls", []):
                descriptor = find_by_function(agent_name, tc["tool_name"])
                tool_id = descriptor.tool_id if descriptor else f"{agent_name}.unknown.{tc['tool_name']}"
                display_en = descriptor.display_name_en if descriptor else tc["tool_name"]
                display_ar = descriptor.display_name_ar if descriptor else tc["tool_name"]
                # Build a brief result summary (first 120 chars of result)
                _summary = ""
                try:
                    _parsed = json.loads(tc["tool_result"]) if isinstance(tc["tool_result"], str) else tc["tool_result"]
                    if isinstance(_parsed, dict):
                        if _parsed.get("error"):
                            _summary = _parsed.get("message", "Error")[:120]
                        elif "message" in _parsed:
                            _summary = str(_parsed["message"])[:120]
                        else:
                            # Pick a meaningful field
                            for _key in ("balance", "total", "status", "count", "name"):
                                if _key in _parsed:
                                    _summary = f"{_key}: {_parsed[_key]}"
                                    break
                            if not _summary:
                                _summary = str(_parsed)[:120]
                    else:
                        _summary = str(_parsed)[:120]
                except (json.JSONDecodeError, TypeError):
                    _summary = str(tc["tool_result"])[:120]

                # Parse full result data for rich frontend rendering
                _result_data = None
                try:
                    _rd = json.loads(tc["tool_result"]) if isinstance(tc["tool_result"], str) else tc["tool_result"]
                    if isinstance(_rd, dict):
                        _result_data = _rd
                    elif isinstance(_rd, list):
                        # Many tools return a JSON array (e.g. leave balances).
                        # Wrap in a dict so the frontend renderer can access it uniformly.
                        _result_data = {"items": _rd}
                except (json.JSONDecodeError, TypeError):
                    pass

                # Compute duration from timing recorded in base agent
                _duration_ms = None
                _start = tc.get("start_time")
                _end = tc.get("end_time")
                if _start is not None and _end is not None:
                    _duration_ms = int((_end - _start) * 1000)

                tool_events.append({
                    "tool_id": tool_id,
                    "tool_name": tc["tool_name"],
                    "display_name_en": display_en,
                    "display_name_ar": display_ar,
                    "agent": agent_name,
                    "success": tc["success"],
                    "result_summary": _summary,
                    "result_data": _result_data,
                    "duration_ms": _duration_ms,
                })

        # DB session closed — send envelopes
        await websocket.send_json(_envelope(
            "chat.message.created",
            {
                "conversation_id": conv_id_str,
                "message_id": str(user_msg.id),
                "role": "user",
                "text": text,
                "created_at": user_created_at,
            },
            ref=ref,
        ))

        # Emit tool execution cards (between user and assistant messages)
        for tevt in tool_events:
            await websocket.send_json(_envelope(
                "chat.tool.start",
                {
                    "tool_id": tevt["tool_id"],
                    "tool_name": tevt["tool_name"],
                    "display_name_en": tevt["display_name_en"],
                    "display_name_ar": tevt["display_name_ar"],
                    "agent": tevt["agent"],
                },
                ref=ref,
            ))
            await websocket.send_json(_envelope(
                "chat.tool.result",
                {
                    "tool_id": tevt["tool_id"],
                    "tool_name": tevt["tool_name"],
                    "display_name_en": tevt["display_name_en"],
                    "display_name_ar": tevt["display_name_ar"],
                    "agent": tevt["agent"],
                    "success": tevt["success"],
                    "result_summary": tevt["result_summary"],
                    "result_data": tevt["result_data"],
                    "duration_ms": tevt["duration_ms"],
                },
                ref=ref,
            ))

        await websocket.send_json(_envelope(
            "chat.message.created",
            {
                "conversation_id": conv_id_str,
                "message_id": str(agent_msg.id),
                "role": "assistant",
                "agent": agent_name,
                "text": response_text,
                "created_at": agent_created_at,
            },
            ref=ref,
        ))
        await websocket.send_json(_envelope(
            "chat.complete",
            {
                "conversation_id": conv_id_str,
                "message_id": str(agent_msg.id),
                "agent": agent_name,
            },
            ref=ref,
        ))
    except Exception as exc:
        logger.exception("ws chat.send unexpected failure: %s", exc)
        try:
            await websocket.send_json(_envelope(
                "error",
                {
                    "code": "internal_error",
                    "message": "Something went wrong. Please try again.",
                },
                ref=ref,
            ))
        except Exception:
            pass


# ── DM handlers ──────────────────────────────────────────────────

def _ordered_pair(id_a: UUID, id_b: UUID) -> tuple[UUID, UUID]:
    return (id_a, id_b) if str(id_a) < str(id_b) else (id_b, id_a)


async def _handle_dm_send(
    websocket: WebSocket,
    *,
    envelope: dict,
    employee_id: UUID,
    tenant_id: UUID,
) -> None:
    """Handle dm.send — persist a direct message, relay to recipient,
    and invoke an AI agent if the message contains an @mention."""
    from app.models.direct_message import DmMessageType

    ref = envelope.get("id")
    raw_payload = envelope.get("payload") or {}
    peer_id_raw = raw_payload.get("peer_id", "").strip()
    text = (raw_payload.get("text") or "").strip()
    reply_to_raw = raw_payload.get("reply_to_id", "").strip() if raw_payload.get("reply_to_id") else None
    attachments = raw_payload.get("attachments")  # list of attachment dicts or None

    if not peer_id_raw or not text:
        await websocket.send_json(_envelope(
            "error",
            {"code": "invalid_payload", "message": "peer_id and text are required."},
            ref=ref,
        ))
        return

    if len(text) > 4000:
        await websocket.send_json(_envelope(
            "error",
            {"code": "invalid_payload", "message": "Message too long (max 4000 chars)."},
            ref=ref,
        ))
        return

    try:
        peer_id = UUID(peer_id_raw)
    except ValueError:
        await websocket.send_json(_envelope(
            "error",
            {"code": "invalid_payload", "message": "Invalid peer_id."},
            ref=ref,
        ))
        return

    reply_to_id = None
    if reply_to_raw:
        try:
            reply_to_id = UUID(reply_to_raw)
        except ValueError:
            pass

    if peer_id == employee_id:
        await websocket.send_json(_envelope(
            "error",
            {"code": "invalid_payload", "message": "Cannot message yourself."},
            ref=ref,
        ))
        return

    a_id, b_id = _ordered_pair(employee_id, peer_id)

    try:
        async with async_session() as db:
            # Verify peer exists in same tenant (employee or deployed agent)
            peer_result = await db.execute(
                select(Employee).where(
                    Employee.id == peer_id,
                    Employee.tenant_id == tenant_id,
                    Employee.status.in_([EmployeeStatus.active, EmployeeStatus.onboarding]),
                )
            )
            peer = peer_result.scalar_one_or_none()
            deployed_agent_peer = None

            if peer is None:
                # Check if peer is a deployed AI agent
                from app.models.deployed_agent import DeployedAgent, AgentStatus
                agent_result = await db.execute(
                    select(DeployedAgent).where(
                        DeployedAgent.id == peer_id,
                        DeployedAgent.tenant_id == tenant_id,
                        DeployedAgent.status == AgentStatus.active,
                    )
                )
                deployed_agent_peer = agent_result.scalar_one_or_none()
                if deployed_agent_peer is None:
                    await websocket.send_json(_envelope(
                        "error",
                        {"code": "peer_not_found", "message": "Recipient not found."},
                        ref=ref,
                    ))
                    return

            # Load sender for agent context
            sender_result = await db.execute(
                select(Employee).where(Employee.id == employee_id, Employee.tenant_id == tenant_id)
            )
            sender = sender_result.scalar_one_or_none()

            # Find or create conversation
            conv_result = await db.execute(
                select(DirectConversation).where(
                    DirectConversation.tenant_id == tenant_id,
                    DirectConversation.participant_a_id == a_id,
                    DirectConversation.participant_b_id == b_id,
                )
            )
            conv = conv_result.scalar_one_or_none()
            now = datetime.now(timezone.utc)

            if conv is None:
                conv = DirectConversation(
                    tenant_id=tenant_id,
                    participant_a_id=a_id,
                    participant_b_id=b_id,
                    last_message_at=now,
                )
                db.add(conv)
                await db.flush()
            else:
                conv.last_message_at = now

            # Persist the human message
            msg = DirectMessage(
                conversation_id=conv.id,
                sender_id=employee_id,
                content=text,
                message_type=DmMessageType.human.value,
                reply_to_id=reply_to_id,
                attachments=attachments if attachments else None,
            )
            db.add(msg)
            await db.commit()
            await db.refresh(msg)

            msg_id = str(msg.id)
            conv_id = str(conv.id)
            created_at = msg.created_at.isoformat() if msg.created_at else _now_iso()

            # Snapshot for agent invocation (need these after DB session)
            sender_name = sender.first_name if sender else "User"
            sender_lang = sender.preferred_language if sender else "en"
            employee_dept_id = sender.department_id if sender else None

        # Build and broadcast the human message envelope
        dm_base_payload = {
            "conversation_id": conv_id,
            "message_id": msg_id,
            "sender_id": str(employee_id),
            "peer_id": str(peer_id),
            "text": text,
            "created_at": created_at,
            "message_type": "human",
            "reply_to_id": str(reply_to_id) if reply_to_id else None,
            "attachments": attachments,
        }
        dm_envelope = _envelope("dm.message.created", dm_base_payload, ref=ref)

        await websocket.send_json(dm_envelope)
        if not deployed_agent_peer:
            # Only relay to human peers (agents don't have WS connections)
            await manager.send_to_user(str(peer_id), dm_envelope)

        # ── Deployed agent auto-invoke (every message triggers the agent) ──
        if deployed_agent_peer is not None:
            asyncio.create_task(_invoke_deployed_agent_in_dm(
                websocket=websocket,
                deployed_agent_id=peer_id,
                message_text=text,
                employee_id=employee_id,
                employee_name=sender_name,
                employee_lang=sender_lang,
                employee_dept_id=employee_dept_id,
                tenant_id=tenant_id,
                conv_id_str=conv_id,
                ref=ref,
            ))
        else:
            # ── @mention agent detection (human-to-human DMs only) ──
            from app.utils.mention_parser import parse_mention, get_mentioned_raw
            mentioned_agent, cleaned_message = parse_mention(text)

            # If parse_mention didn't recognize it, try deployed agents
            if mentioned_agent is None:
                raw_mention = get_mentioned_raw(text)
                if raw_mention:
                    deployed_id = await _resolve_deployed_mention(
                        raw_mention.lstrip("@"), tenant_id
                    )
                    if deployed_id:
                        mentioned_agent = f"dept:{deployed_id}"
                        import re as _re
                        cleaned_message = _re.sub(r'(?:^|\s)@\S+', '', text, count=1).strip()

            if mentioned_agent is not None:
                if mentioned_agent.startswith("dept:"):
                    # Deployed agent — invoke directly
                    try:
                        deployed_uuid = UUID(mentioned_agent[5:])
                    except ValueError:
                        deployed_uuid = None
                    if deployed_uuid:
                        asyncio.create_task(_invoke_deployed_agent_in_dm(
                            websocket=websocket,
                            deployed_agent_id=deployed_uuid,
                            message_text=cleaned_message or text,
                            employee_id=employee_id,
                            employee_name=sender_name,
                            employee_lang=sender_lang,
                            employee_dept_id=employee_dept_id,
                            tenant_id=tenant_id,
                            conv_id_str=conv_id,
                            ref=ref,
                        ))
                else:
                    # Super agent — use orchestrator
                    asyncio.create_task(_invoke_agent_in_dm(
                        websocket=websocket,
                        mentioned_agent=mentioned_agent,
                        cleaned_message=cleaned_message,
                        original_text=text,
                        employee_id=employee_id,
                        employee_name=sender_name,
                        employee_lang=sender_lang,
                        employee_dept_id=employee_dept_id,
                        tenant_id=tenant_id,
                        peer_id=peer_id,
                        conv_id_str=conv_id,
                        ref=ref,
                    ))

    except Exception as exc:
        logger.exception("dm.send failed: %s", exc)
        try:
            await websocket.send_json(_envelope(
                "error",
                {"code": "internal_error", "message": "Failed to send message."},
                ref=ref,
            ))
        except Exception:
            pass


async def _resolve_deployed_mention(name: str, tenant_id: UUID) -> str | None:
    """Look up a deployed agent by name. Returns UUID string or None."""
    from app.models.deployed_agent import DeployedAgent, AgentStatus
    from sqlalchemy import func as sa_func
    name_lower = name.lower().strip()
    async with async_session() as db:
        result = await db.execute(
            select(DeployedAgent.id).where(
                DeployedAgent.tenant_id == tenant_id,
                DeployedAgent.status == AgentStatus.active,
                or_(
                    sa_func.lower(DeployedAgent.name) == name_lower,
                    sa_func.lower(DeployedAgent.name_ar) == name_lower,
                ),
            ).limit(1)
        )
        row = result.scalar_one_or_none()
        return str(row) if row else None


async def _invoke_agent_in_dm(
    *,
    websocket: WebSocket,
    mentioned_agent: str,
    cleaned_message: str,
    original_text: str,
    employee_id: UUID,
    employee_name: str,
    employee_lang: str,
    employee_dept_id: UUID | None,
    tenant_id: UUID,
    peer_id: UUID,
    conv_id_str: str,
    ref: str | None,
) -> None:
    """Invoke an AI agent from a DM @mention and post the response back into the thread."""
    from app.agents.orchestrator import AgentOrchestrator
    from app.utils.employee_role import derive_employee_role
    from app.models.direct_message import DmMessageType

    try:
        async with async_session() as db:
            employee_role = await derive_employee_role(db, tenant_id, employee_id)

            orchestrator = AgentOrchestrator(db, tenant_id)
            agent_name, response_text, _ = await orchestrator.handle_message(
                message=original_text,
                employee_name=employee_name,
                employee_id=str(employee_id),
                conversation_history=[],  # DM context — fresh agent invocation
                current_agent=None,
                language=employee_lang,
                conversation_id=None,
                last_mentioned_agent=None,
                employee_role=employee_role,
                employee_dept_id=employee_dept_id,
            )

            # Persist the agent response as a message in the DM thread
            conv_result = await db.execute(
                select(DirectConversation).where(DirectConversation.id == UUID(conv_id_str))
            )
            conv = conv_result.scalar_one_or_none()
            if conv is None:
                return

            agent_msg = DirectMessage(
                conversation_id=conv.id,
                sender_id=employee_id,  # "on behalf of" the invoker
                content=response_text,
                message_type=DmMessageType.agent.value,
                agent_name=agent_name,
            )
            db.add(agent_msg)
            conv.last_message_at = datetime.now(timezone.utc)
            await db.commit()
            await db.refresh(agent_msg)

            agent_msg_id = str(agent_msg.id)
            agent_created_at = agent_msg.created_at.isoformat() if agent_msg.created_at else _now_iso()

        # Send the agent response to both participants
        agent_envelope = _envelope(
            "dm.message.created",
            {
                "conversation_id": conv_id_str,
                "message_id": agent_msg_id,
                "sender_id": str(employee_id),
                "peer_id": str(peer_id),
                "text": response_text,
                "created_at": agent_created_at,
                "message_type": "agent",
                "agent_name": agent_name,
            },
            ref=ref,
        )

        await websocket.send_json(agent_envelope)
        await manager.send_to_user(str(peer_id), agent_envelope)

    except Exception:
        logger.exception("Agent invocation in DM failed")
        try:
            await websocket.send_json(_envelope(
                "error",
                {"code": "agent_error", "message": "Agent failed to respond in DM."},
                ref=ref,
            ))
        except Exception:
            pass


async def _invoke_deployed_agent_in_dm(
    *,
    websocket: WebSocket,
    deployed_agent_id: UUID,
    message_text: str,
    employee_id: UUID,
    employee_name: str,
    employee_lang: str,
    employee_dept_id: UUID | None,
    tenant_id: UUID,
    conv_id_str: str,
    ref: str | None,
) -> None:
    """Invoke a deployed (department-level) AI agent in a DM conversation."""
    from app.agents.dynamic_agent import DynamicAgent
    from app.models.deployed_agent import DeployedAgent
    from app.utils.employee_role import derive_employee_role
    from app.models.direct_message import DmMessageType

    try:
        async with async_session() as db:
            # Load the deployed agent config
            agent_result = await db.execute(
                select(DeployedAgent).where(DeployedAgent.id == deployed_agent_id)
            )
            agent_config = agent_result.scalar_one_or_none()
            if agent_config is None:
                return

            employee_role = await derive_employee_role(db, tenant_id, employee_id)

            # Load recent conversation history for context
            conv_id = UUID(conv_id_str)
            history_result = await db.execute(
                select(DirectMessage)
                .where(DirectMessage.conversation_id == conv_id)
                .order_by(DirectMessage.created_at.desc())
                .limit(20)
            )
            history_msgs = list(reversed(history_result.scalars().all()))

            conversation_history = []
            for hm in history_msgs:
                role = "assistant" if (hm.message_type or "human") == "agent" else "user"
                conversation_history.append({"role": role, "content": hm.content})

            # Create and invoke the dynamic agent
            dynamic_agent = DynamicAgent(db, tenant_id, agent_config)
            dynamic_agent._employee_role = employee_role or "employee"
            dynamic_agent._employee_dept_id = employee_dept_id
            dynamic_agent._is_first_message = len(conversation_history) <= 1

            response_text = await dynamic_agent.respond(
                conversation_history,
                employee_name,
                employee_id=str(employee_id),
                language=employee_lang,
            )

            # Persist the agent response
            conv_result = await db.execute(
                select(DirectConversation).where(DirectConversation.id == conv_id)
            )
            conv = conv_result.scalar_one_or_none()
            if conv is None:
                return

            agent_msg = DirectMessage(
                conversation_id=conv.id,
                sender_id=employee_id,
                content=response_text,
                message_type=DmMessageType.agent.value,
                agent_name=agent_config.name,
            )
            db.add(agent_msg)
            conv.last_message_at = datetime.now(timezone.utc)
            await db.commit()
            await db.refresh(agent_msg)

            agent_msg_id = str(agent_msg.id)
            agent_created_at = agent_msg.created_at.isoformat() if agent_msg.created_at else _now_iso()

        # Send the agent response back to the user
        agent_envelope = _envelope(
            "dm.message.created",
            {
                "conversation_id": conv_id_str,
                "message_id": agent_msg_id,
                "sender_id": str(deployed_agent_id),
                "peer_id": str(employee_id),
                "text": response_text,
                "created_at": agent_created_at,
                "message_type": "agent",
                "agent_name": agent_config.name,
            },
            ref=ref,
        )
        await websocket.send_json(agent_envelope)

    except Exception:
        logger.exception("Deployed agent DM invocation failed")
        try:
            await websocket.send_json(_envelope(
                "error",
                {"code": "agent_error", "message": "Agent failed to respond."},
                ref=ref,
            ))
        except Exception:
            pass


async def _handle_dm_typing(
    websocket: WebSocket,
    *,
    envelope: dict,
    employee_id: UUID,
) -> None:
    """Relay a typing indicator to the peer — not persisted."""
    raw_payload = envelope.get("payload") or {}
    peer_id_raw = raw_payload.get("peer_id", "").strip()
    if not peer_id_raw:
        return
    try:
        peer_id = UUID(peer_id_raw)
    except ValueError:
        return

    typing_envelope = _envelope(
        "dm.typing",
        {
            "sender_id": str(employee_id),
            "peer_id": str(peer_id),
        },
    )
    await manager.send_to_user(str(peer_id), typing_envelope)


def is_online(user_id: str) -> bool:
    """Check if a user has at least one active WebSocket connection."""
    return bool(manager._conns.get(user_id))


# ── Endpoint ──────────────────────────────────────────────────────
@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    # Prefer cookie; fall back to ?token=... query param for cross-origin dev only.
    token = websocket.cookies.get("krew_chat_jwt")
    if not token and settings.app_env == "development":
        token = websocket.query_params.get("token")
    payload = await _auth_from_cookie(token)
    if payload is None:
        await websocket.close(code=WS_CLOSE_AUTH_REQUIRED, reason="auth_required")
        return

    user_id = payload["sub"]
    tenant_id = payload["tenant_id"]
    role = payload.get("role", "employee")

    await manager.register(user_id, websocket)

    # Track liveness
    state = {
        "last_client_msg": time.monotonic(),
        "last_ping_sent": 0.0,
        "awaiting_pong": False,
    }

    # Optional Redis pub/sub
    redis_client = await get_redis()
    pubsub = None
    redis_task: asyncio.Task | None = None
    if redis_client is not None:
        try:
            pubsub = redis_client.pubsub()
            await pubsub.subscribe(
                f"tenant:{tenant_id}:broadcast",
                f"tenant:{tenant_id}:user:{user_id}",
            )
        except Exception:
            logger.warning("Redis pubsub subscribe failed; continuing without pub/sub", exc_info=True)
            pubsub = None
    else:
        logger.warning("Redis unavailable — ws connection running without pub/sub")

    # Send connection.ready
    session_id = _new_id()
    await websocket.send_json(_envelope(
        "connection.ready",
        {
            "session_id": session_id,
            "server_time": _now_iso(),
            "user": {
                "id": user_id,
                "tenant_id": tenant_id,
                "role": role,
            },
        },
    ))

    async def _redis_pump():
        if pubsub is None:
            return
        try:
            async for message in pubsub.listen():
                if message is None:
                    continue
                if message.get("type") != "message":
                    continue
                data = message.get("data")
                if isinstance(data, str):
                    try:
                        parsed = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    try:
                        await websocket.send_json(parsed)
                    except Exception:
                        return
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.debug("redis pump error", exc_info=True)

    async def _heartbeat_loop():
        try:
            while True:
                await asyncio.sleep(1)
                now = time.monotonic()
                # Idle timeout
                if now - state["last_client_msg"] > IDLE_TIMEOUT_SEC:
                    await websocket.close(code=WS_CLOSE_IDLE_TIMEOUT, reason="idle_timeout")
                    return
                # Heartbeat
                if state["awaiting_pong"]:
                    if now - state["last_ping_sent"] > HEARTBEAT_TIMEOUT_SEC:
                        await websocket.close(code=WS_CLOSE_HEARTBEAT_TIMEOUT, reason="heartbeat_timeout")
                        return
                elif now - state["last_ping_sent"] > HEARTBEAT_INTERVAL_SEC:
                    await websocket.send_json(_envelope("ping", {}))
                    state["last_ping_sent"] = now
                    state["awaiting_pong"] = True
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.debug("heartbeat loop error", exc_info=True)

    if pubsub is not None:
        redis_task = asyncio.create_task(_redis_pump())
    hb_task = asyncio.create_task(_heartbeat_loop())

    try:
        while True:
            raw = await websocket.receive_text()
            state["last_client_msg"] = time.monotonic()

            # Z2: Reject oversized frames (16 KB cap)
            if len(raw) > 16_384:
                await websocket.send_json(_envelope(
                    "error",
                    {"code": "payload_too_large", "message": "Message too large (max 16 KB)."},
                ))
                continue

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            mtype = msg.get("type")
            if mtype == "pong":
                state["awaiting_pong"] = False
            elif mtype == "chat.send":
                # Run in a background task so the receive loop keeps serving
                # heartbeats and other incoming events while the agent works.
                # Per-user semaphore serializes processing to prevent races.
                _send_sem = manager.get_send_lock(user_id)

                async def _guarded_send(_sem: asyncio.Semaphore, _msg: dict) -> None:
                    async with _sem:
                        await _handle_chat_send(
                            websocket,
                            envelope=_msg,
                            employee_id=UUID(user_id),
                            tenant_id=UUID(tenant_id),
                        )

                asyncio.create_task(_guarded_send(_send_sem, msg))
            elif mtype == "dm.send":
                asyncio.create_task(_handle_dm_send(
                    websocket,
                    envelope=msg,
                    employee_id=UUID(user_id),
                    tenant_id=UUID(tenant_id),
                ))
            elif mtype == "dm.typing":
                asyncio.create_task(_handle_dm_typing(
                    websocket,
                    envelope=msg,
                    employee_id=UUID(user_id),
                ))
            # Other client message types are no-ops for now.
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.debug("ws receive loop error", exc_info=True)
    finally:
        hb_task.cancel()
        if redis_task is not None:
            redis_task.cancel()
        if pubsub is not None:
            try:
                await pubsub.unsubscribe()
                await pubsub.close()
            except Exception:
                pass
        await manager.unregister(user_id, websocket)
