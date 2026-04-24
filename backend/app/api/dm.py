"""Direct messaging API — human-to-human chat between employees."""
import logging
import uuid as _uuid
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from pydantic import BaseModel
from sqlalchemy import select, or_, and_, func, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.employee import Employee, EmployeeStatus
from app.models.direct_message import DirectConversation, DirectMessage
from app.auth.chat_dependencies import get_chat_employee, ChatEmployee

UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "uploads" / "dm"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
ALLOWED_TYPES = {
    "image/jpeg", "image/png", "image/gif", "image/webp",
    "application/pdf", "text/plain", "text/csv",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "audio/webm", "audio/ogg", "audio/mpeg", "audio/mp4",
}

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dm", tags=["direct-messages"])


# ── Response schemas ─────────────────────────────────────────────

class ColleagueOut(BaseModel):
    id: str
    name: str
    name_ar: str | None
    job_title: str
    department_name: str | None
    department_name_ar: str | None
    is_bot: bool = False

class ConversationOut(BaseModel):
    id: str
    peer_id: str
    peer_name: str
    peer_name_ar: str | None
    peer_job_title: str
    last_message: str | None
    last_message_at: str | None
    unread_count: int

class MessageOut(BaseModel):
    id: str
    sender_id: str
    content: str
    created_at: str
    is_edited: bool
    is_deleted: bool = False
    message_type: str = "human"
    agent_name: str | None = None
    reply_to_id: str | None = None
    reactions: dict | None = None
    attachments: list | None = None


# ── Helpers ──────────────────────────────────────────────────────

def _ordered_pair(id_a: UUID, id_b: UUID) -> tuple[UUID, UUID]:
    """Return (participant_a, participant_b) with a < b invariant."""
    return (id_a, id_b) if str(id_a) < str(id_b) else (id_b, id_a)


# ── GET /dm/colleagues ──────────────────────────────────────────

@router.get("/colleagues", response_model=list[ColleagueOut])
async def list_colleagues(
    q: str = Query("", max_length=100),
    db: AsyncSession = Depends(get_db),
    chat_emp: ChatEmployee = Depends(get_chat_employee),
):
    """List employees + active deployed AI agents the current user can message."""
    from app.models.employee import Department
    from app.models.deployed_agent import DeployedAgent, AgentStatus

    stmt = (
        select(Employee, Department.name, Department.name_ar)
        .outerjoin(Department, Employee.department_id == Department.id)
        .where(
            Employee.tenant_id == chat_emp.tenant_id,
            Employee.status.in_([EmployeeStatus.active, EmployeeStatus.onboarding]),
            Employee.id != chat_emp.employee_id,
        )
        .order_by(Employee.first_name)
        .limit(100)
    )
    if q.strip():
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                (Employee.first_name + " " + Employee.last_name).ilike(pattern),
                Employee.first_name_ar.ilike(pattern),
                Employee.last_name_ar.ilike(pattern),
                Employee.job_title.ilike(pattern),
            )
        )

    rows = (await db.execute(stmt)).all()
    results = [
        ColleagueOut(
            id=str(emp.id),
            name=f"{emp.first_name} {emp.last_name}",
            name_ar=f"{emp.first_name_ar or ''} {emp.last_name_ar or ''}".strip() or None,
            job_title=emp.job_title,
            department_name=dept_name,
            department_name_ar=dept_name_ar,
        )
        for emp, dept_name, dept_name_ar in rows
    ]

    # Also include active deployed AI agents
    agent_stmt = (
        select(DeployedAgent, Department.name, Department.name_ar)
        .outerjoin(Department, DeployedAgent.department_id == Department.id)
        .where(
            DeployedAgent.tenant_id == chat_emp.tenant_id,
            DeployedAgent.status == AgentStatus.active,
        )
        .order_by(DeployedAgent.name)
    )
    if q.strip():
        pattern = f"%{q.strip()}%"
        agent_stmt = agent_stmt.where(
            or_(
                DeployedAgent.name.ilike(pattern),
                DeployedAgent.name_ar.ilike(pattern),
                DeployedAgent.role_title.ilike(pattern),
            )
        )

    agent_rows = (await db.execute(agent_stmt)).all()
    for agent, dept_name, dept_name_ar in agent_rows:
        results.append(ColleagueOut(
            id=str(agent.id),
            name=agent.name,
            name_ar=agent.name_ar,
            job_title=agent.role_title,
            department_name=dept_name,
            department_name_ar=dept_name_ar,
            is_bot=True,
        ))

    return results


# ── GET /dm/conversations ───────────────────────────────────────

@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(
    db: AsyncSession = Depends(get_db),
    chat_emp: ChatEmployee = Depends(get_chat_employee),
):
    """List all DM conversations for the current user, sorted by most recent."""
    me = chat_emp.employee_id

    stmt = (
        select(DirectConversation)
        .where(
            DirectConversation.tenant_id == chat_emp.tenant_id,
            or_(
                DirectConversation.participant_a_id == me,
                DirectConversation.participant_b_id == me,
            ),
        )
        .order_by(DirectConversation.last_message_at.desc().nullslast())
    )
    convos = (await db.execute(stmt)).scalars().all()

    # Batch-load peer employee info
    peer_ids = set()
    for c in convos:
        peer_ids.add(c.participant_b_id if c.participant_a_id == me else c.participant_a_id)

    peers: dict[UUID, Employee] = {}
    if peer_ids:
        peer_result = await db.execute(
            select(Employee).where(Employee.id.in_(peer_ids))
        )
        peers = {e.id: e for e in peer_result.scalars().all()}

    # Also check for deployed agent peers (IDs not found as employees)
    from app.models.deployed_agent import DeployedAgent, AgentStatus
    agent_peer_ids = peer_ids - set(peers.keys())
    agent_peers: dict[UUID, DeployedAgent] = {}
    if agent_peer_ids:
        agent_result = await db.execute(
            select(DeployedAgent).where(DeployedAgent.id.in_(agent_peer_ids))
        )
        agent_peers = {a.id: a for a in agent_result.scalars().all()}

    # Fetch last message per conversation
    last_msgs: dict[UUID, DirectMessage] = {}
    if convos:
        conv_ids = [c.id for c in convos]
        # Subquery for max created_at per conversation
        sub = (
            select(
                DirectMessage.conversation_id,
                func.max(DirectMessage.created_at).label("max_ts"),
            )
            .where(DirectMessage.conversation_id.in_(conv_ids))
            .group_by(DirectMessage.conversation_id)
            .subquery()
        )
        last_msg_result = await db.execute(
            select(DirectMessage)
            .join(sub, and_(
                DirectMessage.conversation_id == sub.c.conversation_id,
                DirectMessage.created_at == sub.c.max_ts,
            ))
        )
        for msg in last_msg_result.scalars().all():
            last_msgs[msg.conversation_id] = msg

    results = []
    for c in convos:
        is_a = c.participant_a_id == me
        peer_id = c.participant_b_id if is_a else c.participant_a_id
        peer = peers.get(peer_id)
        agent_peer = agent_peers.get(peer_id) if not peer else None
        read_cursor = c.read_cursor_a if is_a else c.read_cursor_b
        last_msg = last_msgs.get(c.id)

        # Count unread messages
        unread = 0
        if read_cursor is None and last_msg is not None:
            # Never opened — count all messages not by me
            count_result = await db.execute(
                select(func.count(DirectMessage.id)).where(
                    DirectMessage.conversation_id == c.id,
                    DirectMessage.sender_id != me,
                )
            )
            unread = count_result.scalar() or 0
        elif read_cursor is not None:
            count_result = await db.execute(
                select(func.count(DirectMessage.id)).where(
                    DirectMessage.conversation_id == c.id,
                    DirectMessage.sender_id != me,
                    DirectMessage.created_at > read_cursor,
                )
            )
            unread = count_result.scalar() or 0

        # Resolve peer name from employee or deployed agent
        if peer:
            p_name = f"{peer.first_name} {peer.last_name}"
            p_name_ar = f"{peer.first_name_ar or ''} {peer.last_name_ar or ''}".strip() or None
            p_title = peer.job_title
        elif agent_peer:
            p_name = agent_peer.name
            p_name_ar = agent_peer.name_ar
            p_title = agent_peer.role_title
        else:
            p_name = "Unknown"
            p_name_ar = None
            p_title = ""

        results.append(ConversationOut(
            id=str(c.id),
            peer_id=str(peer_id),
            peer_name=p_name,
            peer_name_ar=p_name_ar,
            peer_job_title=p_title,
            last_message=last_msg.content[:100] if last_msg else None,
            last_message_at=last_msg.created_at.isoformat() if last_msg else None,
            unread_count=unread,
        ))

    return results


# ── GET /dm/conversations/{peer_id}/messages ────────────────────

@router.get("/conversations/{peer_id}/messages", response_model=list[MessageOut])
async def get_messages(
    peer_id: UUID,
    before: str | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    chat_emp: ChatEmployee = Depends(get_chat_employee),
):
    """Fetch messages in a DM conversation with a peer, newest first (paginated)."""
    me = chat_emp.employee_id
    a_id, b_id = _ordered_pair(me, peer_id)

    # Find the conversation
    result = await db.execute(
        select(DirectConversation).where(
            DirectConversation.tenant_id == chat_emp.tenant_id,
            DirectConversation.participant_a_id == a_id,
            DirectConversation.participant_b_id == b_id,
        )
    )
    conv = result.scalar_one_or_none()
    if conv is None:
        return []  # No conversation yet — not an error

    stmt = (
        select(DirectMessage)
        .where(DirectMessage.conversation_id == conv.id)
        .order_by(DirectMessage.created_at.desc())
        .limit(limit)
    )
    if before:
        try:
            before_dt = datetime.fromisoformat(before)
        except ValueError:
            raise HTTPException(400, "Invalid 'before' timestamp")
        stmt = stmt.where(DirectMessage.created_at < before_dt)

    msgs = (await db.execute(stmt)).scalars().all()
    return [
        MessageOut(
            id=str(m.id),
            sender_id=str(m.sender_id),
            content="This message was deleted" if m.is_deleted else m.content,
            created_at=m.created_at.isoformat(),
            is_edited=m.is_edited,
            is_deleted=m.is_deleted,
            message_type=m.message_type or "human",
            agent_name=m.agent_name,
            reply_to_id=str(m.reply_to_id) if m.reply_to_id else None,
            reactions=m.reactions,
            attachments=m.attachments,
        )
        for m in reversed(msgs)  # Return in chronological order
    ]


# ── POST /dm/conversations/{peer_id}/read ───────────────────────

@router.post("/conversations/{peer_id}/read")
async def mark_read(
    peer_id: UUID,
    db: AsyncSession = Depends(get_db),
    chat_emp: ChatEmployee = Depends(get_chat_employee),
):
    """Mark a DM conversation as read (updates the read cursor)."""
    me = chat_emp.employee_id
    a_id, b_id = _ordered_pair(me, peer_id)

    result = await db.execute(
        select(DirectConversation).where(
            DirectConversation.tenant_id == chat_emp.tenant_id,
            DirectConversation.participant_a_id == a_id,
            DirectConversation.participant_b_id == b_id,
        )
    )
    conv = result.scalar_one_or_none()
    if conv is None:
        return {"ok": True}

    now = datetime.now(timezone.utc)
    if conv.participant_a_id == me or (str(a_id) == str(me)):
        conv.read_cursor_a = now
    else:
        conv.read_cursor_b = now
    await db.commit()
    return {"ok": True}


# ── POST /dm/conversations/{peer_id}/send — REST message send ────

class SendMessageBody(BaseModel):
    text: str
    reply_to_id: str | None = None
    attachments: list | None = None

@router.post("/conversations/{peer_id}/send")
async def send_message(
    peer_id: UUID,
    body: SendMessageBody,
    db: AsyncSession = Depends(get_db),
    chat_emp: ChatEmployee = Depends(get_chat_employee),
):
    """Send a DM via REST (fallback when WebSocket is unavailable)."""
    from app.models.direct_message import DmMessageType

    me = chat_emp.employee_id
    if peer_id == me:
        raise HTTPException(400, "Cannot message yourself.")

    text = body.text.strip()
    if not text:
        raise HTTPException(400, "Message text is required.")
    if len(text) > 4000:
        raise HTTPException(400, "Message too long (max 4000 chars).")

    a_id, b_id = _ordered_pair(me, peer_id)

    # Verify peer exists in same tenant (employee or deployed agent)
    peer_result = await db.execute(
        select(Employee).where(
            Employee.id == peer_id,
            Employee.tenant_id == chat_emp.tenant_id,
            Employee.status.in_([EmployeeStatus.active, EmployeeStatus.onboarding]),
        )
    )
    peer = peer_result.scalar_one_or_none()
    is_agent_peer = False
    if peer is None:
        from app.models.deployed_agent import DeployedAgent, AgentStatus
        agent_result = await db.execute(
            select(DeployedAgent).where(
                DeployedAgent.id == peer_id,
                DeployedAgent.tenant_id == chat_emp.tenant_id,
                DeployedAgent.status == AgentStatus.active,
            )
        )
        if agent_result.scalar_one_or_none() is None:
            raise HTTPException(404, "Recipient not found.")
        is_agent_peer = True

    # Find or create conversation
    conv_result = await db.execute(
        select(DirectConversation).where(
            DirectConversation.tenant_id == chat_emp.tenant_id,
            DirectConversation.participant_a_id == a_id,
            DirectConversation.participant_b_id == b_id,
        )
    )
    conv = conv_result.scalar_one_or_none()
    now = datetime.now(timezone.utc)

    if conv is None:
        conv = DirectConversation(
            tenant_id=chat_emp.tenant_id,
            participant_a_id=a_id,
            participant_b_id=b_id,
            last_message_at=now,
        )
        db.add(conv)
        await db.flush()

    # Parse reply_to
    reply_to_id = None
    if body.reply_to_id:
        try:
            reply_to_id = UUID(body.reply_to_id)
        except ValueError:
            pass

    # Create message
    msg = DirectMessage(
        conversation_id=conv.id,
        sender_id=me,
        content=text,
        message_type=DmMessageType.human.value,
        reply_to_id=reply_to_id,
        attachments=body.attachments,
        created_at=now,
    )
    db.add(msg)
    conv.last_message_at = now

    # Update sender's read cursor
    if conv.participant_a_id == me:
        conv.read_cursor_a = now
    else:
        conv.read_cursor_b = now

    await db.commit()
    await db.refresh(msg)

    # ── @mention agent detection ──
    import asyncio
    from app.utils.mention_parser import parse_mention, get_mentioned_raw

    mentioned_agent, cleaned = parse_mention(text)

    # Try deployed agents if not a super agent
    if mentioned_agent is None:
        raw_mention = get_mentioned_raw(text)
        if raw_mention:
            from app.models.deployed_agent import DeployedAgent as DA2, AgentStatus as AS2
            from sqlalchemy import func as sa_func
            name_lower = raw_mention.lstrip("@").lower().strip()
            da_result = await db.execute(
                select(DA2.id).where(
                    DA2.tenant_id == chat_emp.tenant_id,
                    DA2.status == AS2.active,
                    or_(
                        sa_func.lower(DA2.name) == name_lower,
                        sa_func.lower(DA2.name_ar) == name_lower,
                    ),
                ).limit(1)
            )
            da_row = da_result.scalar_one_or_none()
            if da_row:
                mentioned_agent = f"dept:{da_row}"
                import re as _re
                cleaned = _re.sub(r'(?:^|\s)@\S+', '', text, count=1).strip()

    if mentioned_agent is not None:
        asyncio.create_task(_invoke_agent_in_dm_rest(
            mentioned_agent=mentioned_agent,
            cleaned_message=cleaned or text,
            original_text=text,
            employee_id=me,
            tenant_id=chat_emp.tenant_id,
            conv_id=conv.id,
        ))

    return {
        "id": str(msg.id),
        "conversation_id": str(conv.id),
        "sender_id": str(me),
        "content": msg.content,
        "created_at": msg.created_at.isoformat(),
        "message_type": "human",
        "reply_to_id": str(reply_to_id) if reply_to_id else None,
        "attachments": msg.attachments,
    }


async def _invoke_agent_in_dm_rest(
    *,
    mentioned_agent: str,
    cleaned_message: str,
    original_text: str,
    employee_id: UUID,
    tenant_id: UUID,
    conv_id: UUID,
) -> None:
    """Invoke an agent from a DM @mention (REST path). Persists the response."""
    from app.database import async_session
    from app.models.direct_message import DirectConversation, DirectMessage, DmMessageType
    from app.utils.employee_role import derive_employee_role
    from app.models.employee import Employee

    try:
        async with async_session() as db:
            # Load sender info
            sender_result = await db.execute(
                select(Employee).where(Employee.id == employee_id)
            )
            sender = sender_result.scalar_one_or_none()
            if not sender:
                return

            employee_role = await derive_employee_role(db, tenant_id, employee_id)

            if mentioned_agent.startswith("dept:"):
                # Deployed agent
                from app.agents.dynamic_agent import DynamicAgent
                from app.models.deployed_agent import DeployedAgent
                try:
                    agent_uuid = UUID(mentioned_agent[5:])
                except ValueError:
                    return
                agent_result = await db.execute(
                    select(DeployedAgent).where(DeployedAgent.id == agent_uuid)
                )
                agent_config = agent_result.scalar_one_or_none()
                if not agent_config:
                    return

                dynamic = DynamicAgent(db, tenant_id, agent_config)
                dynamic._employee_role = employee_role or "employee"
                dynamic._employee_dept_id = sender.department_id
                dynamic._is_first_message = True

                response_text = await dynamic.respond(
                    [{"role": "user", "content": cleaned_message}],
                    sender.first_name,
                    employee_id=str(employee_id),
                    language=sender.preferred_language,
                )
                agent_name = agent_config.name
                agent_sender_id = employee_id
            else:
                # Super agent
                from app.agents.orchestrator import AgentOrchestrator
                orchestrator = AgentOrchestrator(db, tenant_id)
                agent_name, response_text, _ = await orchestrator.handle_message(
                    message=original_text,
                    employee_name=sender.first_name,
                    employee_id=str(employee_id),
                    conversation_history=[],
                    current_agent=None,
                    language=sender.preferred_language,
                    conversation_id=None,
                    last_mentioned_agent=None,
                    employee_role=employee_role,
                    employee_dept_id=sender.department_id,
                )
                agent_sender_id = employee_id

            # Persist agent response
            conv_result = await db.execute(
                select(DirectConversation).where(DirectConversation.id == conv_id)
            )
            conv = conv_result.scalar_one_or_none()
            if not conv:
                return

            agent_msg = DirectMessage(
                conversation_id=conv.id,
                sender_id=agent_sender_id,
                content=response_text,
                message_type=DmMessageType.agent.value,
                agent_name=agent_name,
            )
            db.add(agent_msg)
            conv.last_message_at = datetime.now(timezone.utc)
            await db.commit()

    except Exception:
        logger.exception("Agent invocation in DM (REST) failed")


# ── POST /dm/messages/{message_id}/react ─────────────────────────

class ReactionBody(BaseModel):
    emoji: str  # e.g. "👍", "❤️", "🎉"

@router.post("/messages/{message_id}/react")
async def toggle_reaction(
    message_id: UUID,
    body: ReactionBody,
    db: AsyncSession = Depends(get_db),
    chat_emp: ChatEmployee = Depends(get_chat_employee),
):
    """Toggle an emoji reaction on a DM message."""
    me = str(chat_emp.employee_id)
    result = await db.execute(select(DirectMessage).where(DirectMessage.id == message_id))
    msg = result.scalar_one_or_none()
    if msg is None:
        raise HTTPException(404, "Message not found")

    # Verify caller is a participant
    conv_result = await db.execute(select(DirectConversation).where(
        DirectConversation.id == msg.conversation_id,
        DirectConversation.tenant_id == chat_emp.tenant_id,
    ))
    conv = conv_result.scalar_one_or_none()
    if conv is None or (chat_emp.employee_id != conv.participant_a_id and chat_emp.employee_id != conv.participant_b_id):
        raise HTTPException(403, "Not a participant")

    reactions = dict(msg.reactions or {})
    users = list(reactions.get(body.emoji, []))
    if me in users:
        users.remove(me)
    else:
        users.append(me)

    if users:
        reactions[body.emoji] = users
    else:
        reactions.pop(body.emoji, None)

    msg.reactions = reactions if reactions else None
    # Force SQLAlchemy to detect the JSONB change
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(msg, "reactions")
    await db.commit()
    return {"ok": True, "reactions": reactions}


# ── PATCH /dm/messages/{message_id} — edit ───────────────────────

class EditBody(BaseModel):
    content: str

@router.patch("/messages/{message_id}")
async def edit_message(
    message_id: UUID,
    body: EditBody,
    db: AsyncSession = Depends(get_db),
    chat_emp: ChatEmployee = Depends(get_chat_employee),
):
    """Edit a DM message (own messages only)."""
    result = await db.execute(select(DirectMessage).where(DirectMessage.id == message_id))
    msg = result.scalar_one_or_none()
    if msg is None:
        raise HTTPException(404, "Message not found")
    if msg.sender_id != chat_emp.employee_id:
        raise HTTPException(403, "Can only edit your own messages")
    if msg.is_deleted:
        raise HTTPException(400, "Message is deleted")
    if msg.message_type != "human":
        raise HTTPException(400, "Cannot edit agent messages")

    new_content = body.content.strip()
    if not new_content or len(new_content) > 4000:
        raise HTTPException(400, "Invalid content")

    msg.content = new_content
    msg.is_edited = True
    msg.edited_at = datetime.now(timezone.utc)
    await db.commit()
    return {"ok": True, "content": msg.content, "edited_at": msg.edited_at.isoformat()}


# ── DELETE /dm/messages/{message_id} ─────────────────────────────

@router.delete("/messages/{message_id}")
async def delete_message(
    message_id: UUID,
    db: AsyncSession = Depends(get_db),
    chat_emp: ChatEmployee = Depends(get_chat_employee),
):
    """Soft-delete a DM message (own messages only)."""
    result = await db.execute(select(DirectMessage).where(DirectMessage.id == message_id))
    msg = result.scalar_one_or_none()
    if msg is None:
        raise HTTPException(404, "Message not found")
    if msg.sender_id != chat_emp.employee_id:
        raise HTTPException(403, "Can only delete your own messages")

    msg.is_deleted = True
    msg.content = ""
    await db.commit()
    return {"ok": True}


# ── POST /dm/conversations/{peer_id}/pin ─────────────────────────

class PinBody(BaseModel):
    message_id: str

@router.post("/conversations/{peer_id}/pin")
async def pin_message(
    peer_id: UUID,
    body: PinBody,
    db: AsyncSession = Depends(get_db),
    chat_emp: ChatEmployee = Depends(get_chat_employee),
):
    """Pin/unpin a message in a DM conversation."""
    me = chat_emp.employee_id
    a_id, b_id = _ordered_pair(me, peer_id)

    result = await db.execute(
        select(DirectConversation).where(
            DirectConversation.tenant_id == chat_emp.tenant_id,
            DirectConversation.participant_a_id == a_id,
            DirectConversation.participant_b_id == b_id,
        )
    )
    conv = result.scalar_one_or_none()
    if conv is None:
        raise HTTPException(404, "Conversation not found")

    pins = list(conv.pinned_message_ids or [])
    if body.message_id in pins:
        pins.remove(body.message_id)
    else:
        pins.append(body.message_id)

    conv.pinned_message_ids = pins if pins else None
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(conv, "pinned_message_ids")
    await db.commit()
    return {"ok": True, "pinned_message_ids": pins}


# ── GET /dm/conversations/{peer_id}/search ───────────────────────

@router.get("/conversations/{peer_id}/search", response_model=list[MessageOut])
async def search_messages(
    peer_id: UUID,
    q: str = Query("", min_length=1, max_length=200),
    db: AsyncSession = Depends(get_db),
    chat_emp: ChatEmployee = Depends(get_chat_employee),
):
    """Search messages in a DM conversation."""
    me = chat_emp.employee_id
    a_id, b_id = _ordered_pair(me, peer_id)

    result = await db.execute(
        select(DirectConversation).where(
            DirectConversation.tenant_id == chat_emp.tenant_id,
            DirectConversation.participant_a_id == a_id,
            DirectConversation.participant_b_id == b_id,
        )
    )
    conv = result.scalar_one_or_none()
    if conv is None:
        return []

    stmt = (
        select(DirectMessage)
        .where(
            DirectMessage.conversation_id == conv.id,
            DirectMessage.is_deleted == False,
            DirectMessage.content.ilike(f"%{q.strip()}%"),
        )
        .order_by(DirectMessage.created_at.desc())
        .limit(20)
    )
    msgs = (await db.execute(stmt)).scalars().all()
    return [
        MessageOut(
            id=str(m.id),
            sender_id=str(m.sender_id),
            content=m.content,
            created_at=m.created_at.isoformat(),
            is_edited=m.is_edited,
            is_deleted=m.is_deleted,
            message_type=m.message_type or "human",
            agent_name=m.agent_name,
            reply_to_id=str(m.reply_to_id) if m.reply_to_id else None,
            reactions=m.reactions,
            attachments=m.attachments,
        )
        for m in reversed(msgs)
    ]


# ── GET /dm/employees/{employee_id}/profile ──────────────────────

class ProfileOut(BaseModel):
    id: str
    name: str
    name_ar: str | None
    email: str
    phone: str | None
    job_title: str
    department_name: str | None
    department_name_ar: str | None
    hire_date: str | None
    is_saudi: bool

@router.get("/employees/{employee_id}/profile", response_model=ProfileOut)
async def get_profile(
    employee_id: UUID,
    db: AsyncSession = Depends(get_db),
    chat_emp: ChatEmployee = Depends(get_chat_employee),
):
    """Get a colleague's profile for the DM header."""
    from app.models.employee import Department

    result = await db.execute(
        select(Employee, Department.name, Department.name_ar)
        .outerjoin(Department, Employee.department_id == Department.id)
        .where(
            Employee.id == employee_id,
            Employee.tenant_id == chat_emp.tenant_id,
        )
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(404, "Employee not found")
    emp, dept_name, dept_name_ar = row
    return ProfileOut(
        id=str(emp.id),
        name=f"{emp.first_name} {emp.last_name}",
        name_ar=f"{emp.first_name_ar or ''} {emp.last_name_ar or ''}".strip() or None,
        email=emp.email,
        phone=emp.phone,
        job_title=emp.job_title,
        department_name=dept_name,
        department_name_ar=dept_name_ar,
        hire_date=emp.hire_date.isoformat() if emp.hire_date else None,
        is_saudi=emp.is_saudi,
    )


# ── POST /dm/upload — file/voice upload ──────────────────────────

@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    chat_emp: ChatEmployee = Depends(get_chat_employee),
):
    """Upload a file or voice note for a DM attachment.

    Returns a URL and metadata to be included in the dm.send attachments payload.
    """
    if file.content_type and file.content_type not in ALLOWED_TYPES:
        raise HTTPException(400, f"File type not allowed: {file.content_type}")

    data = await file.read()
    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(400, "File too large (max 10 MB)")

    ext = Path(file.filename or "file").suffix or ".bin"
    unique_name = f"{_uuid.uuid4().hex}{ext}"
    file_path = UPLOAD_DIR / unique_name
    file_path.write_bytes(data)

    # Determine attachment type
    ct = file.content_type or ""
    if ct.startswith("image/"):
        att_type = "image"
    elif ct.startswith("audio/"):
        att_type = "voice"
    else:
        att_type = "file"

    url = f"/uploads/dm/{unique_name}"

    return {
        "type": att_type,
        "url": url,
        "name": file.filename or unique_name,
        "size": len(data),
    }
