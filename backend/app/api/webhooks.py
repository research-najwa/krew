"""Webhook endpoints for incoming channel messages (WhatsApp, Slack, Teams)."""
import json
from uuid import UUID

from fastapi import APIRouter, Request, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.config import get_settings
from app.models.employee import Employee
from app.models.conversation import Conversation, Message, ConversationStatus
from app.agents.orchestrator import AgentOrchestrator
from app.channels.router import ChannelRouter
from app.security.rate_limiter import check_webhook_rate_limit
from app.security.input_validator import validate_chat_message
from app.security.webhook_signatures import verify_whatsapp_signature, verify_slack_signature
from app.security.webhook_auth import verify_webhook_api_key

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
settings = get_settings()
channel_router = ChannelRouter()


@router.get("/whatsapp")
async def whatsapp_verify(request: Request):
    """WhatsApp webhook verification (GET)."""
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == settings.whatsapp_verify_token:
        return int(challenge)
    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/whatsapp")
async def whatsapp_inbound(request: Request, db: AsyncSession = Depends(get_db)):
    """Handle incoming WhatsApp messages."""
    await verify_webhook_api_key(request, "whatsapp")
    await check_webhook_rate_limit(request)
    body = await verify_whatsapp_signature(request)
    payload = json.loads(body)
    parsed = channel_router.parse_inbound("whatsapp", payload)

    if not parsed:
        return {"status": "ignored"}

    return await _process_message(db, parsed)


@router.post("/slack")
async def slack_inbound(request: Request, db: AsyncSession = Depends(get_db)):
    """Handle incoming Slack messages."""
    await verify_webhook_api_key(request, "slack")
    await check_webhook_rate_limit(request)
    body = await verify_slack_signature(request)
    payload = json.loads(body)

    # Slack URL verification challenge
    if payload.get("type") == "url_verification":
        return {"challenge": payload["challenge"]}

    parsed = channel_router.parse_inbound("slack", payload)
    if not parsed:
        return {"status": "ignored"}

    return await _process_message(db, parsed)


async def _process_message(db: AsyncSession, parsed: dict) -> dict:
    """Core message processing — shared across all channels."""
    sender_id = parsed["sender_id"]
    message_text = parsed["message"]
    channel = parsed["channel"]

    # Validate message length (sanitize_user_input is called in BaseAgent.respond)
    try:
        message_text = validate_chat_message(message_text)
    except HTTPException:
        # For webhooks, silently truncate rather than returning 400 to the channel
        message_text = message_text[:4000].strip() if message_text else ""

    # Look up employee by channel identifier
    employee = await _find_employee(db, channel, sender_id)
    if not employee:
        return {"status": "unknown_sender"}

    # Find or create conversation
    conversation = await _get_active_conversation(db, employee.id, channel)

    # Route to agent and get response
    orchestrator = AgentOrchestrator(db, employee.tenant_id)

    # Build conversation history from DB
    history = await _get_message_history(db, conversation.id)

    agent_name, response = await orchestrator.handle_message(
        message=message_text,
        employee_name=employee.first_name,
        employee_id=str(employee.id),
        conversation_history=history,
        current_agent=conversation.agent_name,
        language=employee.preferred_language,
    )

    # Update conversation agent if it changed
    if conversation.agent_name != agent_name:
        conversation.agent_name = agent_name

    # Save messages
    db.add(Message(
        conversation_id=conversation.id,
        role="employee",
        content=message_text,
        channel=channel,
        language=employee.preferred_language,
    ))
    db.add(Message(
        conversation_id=conversation.id,
        role="agent",
        content=response,
        channel=channel,
        language=employee.preferred_language,
    ))
    await db.commit()

    # Send response back through channel
    await channel_router.send_outbound(channel, sender_id, response)

    return {"status": "ok", "agent": agent_name}


async def _find_employee(
    db: AsyncSession, channel: str, sender_id: str
) -> Employee | None:
    """Look up an employee by their channel-specific identifier."""
    column_map = {
        "whatsapp": Employee.whatsapp_number,
        "slack": Employee.slack_user_id,
        "teams": Employee.teams_user_id,
        "email": Employee.email,
    }
    column = column_map.get(channel)
    if not column:
        return None

    result = await db.execute(
        select(Employee).where(
            column == sender_id,
            Employee.status == "active",
        )
    )
    return result.scalar_one_or_none()


async def _get_active_conversation(
    db: AsyncSession, employee_id: UUID, channel: str
) -> Conversation:
    """Find active conversation or create a new one."""
    result = await db.execute(
        select(Conversation).where(
            Conversation.employee_id == employee_id,
            Conversation.channel == channel,
            Conversation.status == ConversationStatus.active,
        )
    )
    conversation = result.scalar_one_or_none()

    if not conversation:
        conversation = Conversation(
            tenant_id=(await db.execute(
                select(Employee.tenant_id).where(Employee.id == employee_id)
            )).scalar_one(),
            employee_id=employee_id,
            agent_name="deema",  # default, orchestrator will update
            channel=channel,
        )
        db.add(conversation)
        await db.flush()

    return conversation


async def _get_message_history(db: AsyncSession, conversation_id: UUID) -> list[dict]:
    """Load conversation history for Claude context."""
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
        .limit(20)  # last 20 messages for context
    )
    messages = result.scalars().all()

    return [
        {
            "role": "user" if m.role == "employee" else "assistant",
            "content": m.content,
        }
        for m in messages
    ]
