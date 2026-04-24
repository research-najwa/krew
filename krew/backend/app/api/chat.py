"""Web chat endpoint — for testing Deema without WhatsApp/Slack."""
import asyncio
import logging
from uuid import UUID

import anthropic
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.employee import Employee, EmployeeStatus
from app.models.conversation import Conversation, Message, ConversationStatus
from app.agents.orchestrator import AgentOrchestrator
from app.security.rate_limiter import check_chat_rate_limit, check_chat_ip_rate_limit
from app.security.input_validator import validate_chat_message
from app.auth.chat_dependencies import get_chat_employee, ChatEmployee

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    employee_id: str = ""  # Ignored when authenticated — kept for backward compat
    message: str
    agent: str = ""  # Optional: UI passes this when user explicitly selected an agent
    conversation_id: str = ""  # Optional: resume a specific conversation


class ChatResponse(BaseModel):
    agent: str
    response: str
    conversation_id: str
    topic: str = ""
    suggestions: list[str] = []


@router.post("", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    chat_emp: ChatEmployee = Depends(get_chat_employee),
):
    """Send a message as an employee and get a response from a Krew agent."""
    # Use employee_id from JWT token — never trust the request body
    emp_id = chat_emp.employee_id

    # Rate limit before validation to avoid wasting CPU on flood attacks
    # IP-based limit prevents rotating employee_ids to bypass per-employee limit
    await check_chat_ip_rate_limit(request)
    await check_chat_rate_limit(str(emp_id))

    cleaned_message = validate_chat_message(req.message)

    # Find employee — enforce tenant isolation + active status
    result = await db.execute(
        select(Employee).where(
            Employee.id == emp_id,
            Employee.tenant_id == chat_emp.tenant_id,
            Employee.status == EmployeeStatus.active,
        )
    )
    employee = result.scalar_one_or_none()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    # Find or create web conversation — enforce tenant isolation
    conversation = None

    # If client requests a specific conversation, resume it
    if req.conversation_id:
        try:
            conv_uuid = UUID(req.conversation_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid conversation_id")
        conv_result = await db.execute(
            select(Conversation).where(
                Conversation.id == conv_uuid,
                Conversation.employee_id == emp_id,
                Conversation.tenant_id == chat_emp.tenant_id,
            )
        )
        conversation = conv_result.scalar_one_or_none()
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        # Reactivate resolved conversations so the user can continue
        if conversation.status == ConversationStatus.resolved:
            conversation.status = ConversationStatus.active
            conversation.resolved_at = None

    # Otherwise find the most recent active conversation or create a new one
    if not conversation:
        conv_result = await db.execute(
            select(Conversation).where(
                Conversation.employee_id == emp_id,
                Conversation.tenant_id == chat_emp.tenant_id,
                Conversation.channel == "web",
                Conversation.status == ConversationStatus.active,
            ).order_by(Conversation.id.desc()).limit(1)
        )
        conversation = conv_result.scalar_one_or_none()

    if not conversation:
        conversation = Conversation(
            tenant_id=employee.tenant_id,
            employee_id=emp_id,
            agent_name=req.agent or "pending",
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
                    Conversation.employee_id == emp_id,
                    Conversation.tenant_id == chat_emp.tenant_id,
                    Conversation.channel == "web",
                    Conversation.status == ConversationStatus.active,
                )
            )
            conversation = conv_result.scalar_one()

    # Check if conversation is escalated — block agent response
    if conversation.status == ConversationStatus.escalated:
        # Save the employee message but return a system message
        db.add(Message(
            conversation_id=conversation.id,
            role="employee",
            content=cleaned_message,
            channel="web",
            language=employee.preferred_language,
        ))
        escalated_response = (
            "Your conversation has been escalated to a human HR specialist. "
            "They will review your case and respond shortly. Please wait for their reply.\n\n"
            "تم تصعيد محادثتك إلى أخصائي موارد بشرية. "
            "سيقومون بمراجعة حالتك والرد عليك قريبا. يرجى انتظار ردهم."
        )
        db.add(Message(
            conversation_id=conversation.id,
            role="system",
            content=escalated_response,
            channel="web",
            language=employee.preferred_language,
        ))
        await db.commit()
        return ChatResponse(
            agent="system",
            response=escalated_response,
            conversation_id=str(conversation.id),
            topic=conversation.topic or "",
        )

    # Load conversation history — newest 20 messages, then reverse to chronological
    # Exclude system messages (escalation notices etc.) — Claude only expects user/assistant
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

    # Route and respond
    # If user explicitly selected an agent in the UI, prefer that over keyword routing
    stored_agent = conversation.agent_name
    # "pending" means new conversation — let the router decide based on message content
    current_agent = req.agent if req.agent else (stored_agent if stored_agent != "pending" else None)

    orchestrator = AgentOrchestrator(db, employee.tenant_id)
    agent_name, response = await orchestrator.handle_message(
        message=cleaned_message,
        employee_name=employee.first_name,
        employee_id=str(employee.id),
        conversation_history=history,
        current_agent=current_agent,
        language=employee.preferred_language,
        conversation_id=conversation.id,
    )

    # Update conversation
    conversation.agent_name = agent_name

    # Generate topic on first exchange (when topic is still empty)
    if not conversation.topic:
        conversation.topic = _generate_quick_title(cleaned_message)

    # Save messages
    db.add(Message(
        conversation_id=conversation.id,
        role="employee",
        content=cleaned_message,
        channel="web",
        language=employee.preferred_language,
    ))
    db.add(Message(
        conversation_id=conversation.id,
        role="agent",
        content=response,
        channel="web",
        language=employee.preferred_language,
    ))
    await db.commit()

    # Extract structured follow-up suggestions from the agent (CUX-02)
    suggestions: list[str] = []
    if hasattr(orchestrator, 'last_agent') and orchestrator.last_agent:
        suggestions = getattr(orchestrator.last_agent, '_last_suggestions', [])

    # Fire background AI title generation (improves the quick title)
    conv_id = conversation.id
    asyncio.create_task(
        _generate_ai_title(conv_id, cleaned_message, response, employee.preferred_language)
    )

    return ChatResponse(
        agent=agent_name,
        response=response,
        conversation_id=str(conversation.id),
        topic=conversation.topic or "",
        suggestions=suggestions,
    )


def _generate_quick_title(message: str) -> str:
    """Instant title from the first message — truncated at word boundary."""
    clean = message.strip().replace("\n", " ")
    if len(clean) <= 50:
        return clean
    # Truncate at word boundary
    truncated = clean[:50].rsplit(" ", 1)[0]
    return truncated + "..." if truncated else clean[:50] + "..."


async def _generate_ai_title(
    conversation_id: UUID,
    user_message: str,
    agent_response: str,
    language: str,
) -> None:
    """Background task: generate a short AI title and update the conversation."""
    try:
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        lang_hint = "Arabic" if language == "ar" else "English"
        resp = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=60,
            messages=[{
                "role": "user",
                "content": (
                    f"Generate a short title (3-6 words, in {lang_hint}) summarizing this HR chat.\n\n"
                    f"Employee: {user_message[:200]}\n"
                    f"Agent: {agent_response[:200]}\n\n"
                    "Reply with ONLY the title, no quotes, no explanation."
                ),
            }],
        )
        title = resp.content[0].text.strip().strip('"\'')
        if not title or len(title) > 100:
            return

        # Update in a fresh DB session
        from app.database import async_session
        async with async_session() as db:
            result = await db.execute(
                select(Conversation).where(Conversation.id == conversation_id)
            )
            conv = result.scalar_one_or_none()
            if conv:
                conv.topic = title
                await db.commit()
    except Exception as exc:
        logger.debug("AI title generation failed (non-critical): %s", exc)


@router.get("/employees")
async def list_employees(
    db: AsyncSession = Depends(get_db),
    chat_emp: ChatEmployee = Depends(get_chat_employee),
):
    """List employees for the authenticated user's tenant in the chat UI dropdown."""
    tid = chat_emp.tenant_id
    result = await db.execute(
        select(Employee).where(
            Employee.status == EmployeeStatus.active,
            Employee.tenant_id == tid,
        ).order_by(Employee.employee_number)
    )
    employees = result.scalars().all()
    return [
        {
            "id": str(e.id),
            "name": e.full_name,
            "name_ar": (
                " ".join(filter(None, [e.first_name_ar, e.last_name_ar]))
                if e.first_name_ar else None
            ),
            "language": e.preferred_language,
        }
        for e in employees
    ]


@router.get("/tenants")
async def list_tenants(request: Request, db: AsyncSession = Depends(get_db)):
    """List tenants for the chat UI login form — rate-limited, no auth required."""
    await check_chat_ip_rate_limit(request)
    from app.models.tenant import Tenant
    result = await db.execute(select(Tenant).order_by(Tenant.name))
    tenants = result.scalars().all()
    return [
        {"id": str(t.id), "name": t.name, "name_ar": t.name_ar}
        for t in tenants
    ]


@router.post("/reset/{employee_id}")
async def reset_conversation(
    employee_id: str,
    db: AsyncSession = Depends(get_db),
    chat_emp: ChatEmployee = Depends(get_chat_employee),
):
    """Reset active web conversation for an employee."""
    try:
        emp_id = UUID(employee_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid employee_id")

    # Enforce ownership — token employee must match path employee
    if chat_emp.employee_id != emp_id:
        raise HTTPException(status_code=403, detail="Cannot reset another employee's conversation")

    result = await db.execute(
        select(Conversation).where(
            Conversation.employee_id == emp_id,
            Conversation.tenant_id == chat_emp.tenant_id,
            Conversation.channel == "web",
            Conversation.status == ConversationStatus.active,
        )
    )
    conversations = result.scalars().all()
    for conversation in conversations:
        conversation.status = ConversationStatus.resolved
    if conversations:
        await db.commit()

    return {"status": "reset"}


@router.get("/conversations")
async def list_conversations(
    db: AsyncSession = Depends(get_db),
    chat_emp: ChatEmployee = Depends(get_chat_employee),
):
    """List all conversations for the authenticated employee (newest first)."""
    result = await db.execute(
        select(Conversation).where(
            Conversation.employee_id == chat_emp.employee_id,
            Conversation.tenant_id == chat_emp.tenant_id,
            Conversation.channel == "web",
        ).order_by(Conversation.started_at.desc()).limit(50)
    )
    conversations = result.scalars().all()

    # Backfill topics for conversations that don't have one yet
    needs_commit = False
    for c in conversations:
        if not c.topic:
            # Grab the first employee message and first agent response
            msgs_result = await db.execute(
                select(Message.role, Message.content).where(
                    Message.conversation_id == c.id,
                    Message.role.in_(["employee", "agent"]),
                ).order_by(Message.created_at.asc()).limit(2)
            )
            msgs = msgs_result.all()
            user_msg = next((m.content for m in msgs if m.role == "employee"), None)
            agent_msg = next((m.content for m in msgs if m.role == "agent"), None)
            if user_msg:
                c.topic = _generate_quick_title(user_msg)
                needs_commit = True
                # Also fire AI title in background for a better title
                if agent_msg:
                    asyncio.create_task(
                        _generate_ai_title(c.id, user_msg, agent_msg, c.language)
                    )

    if needs_commit:
        await db.commit()

    return [
        {
            "id": str(c.id),
            "agent_name": c.agent_name,
            "status": c.status.value,
            "topic": c.topic,
            "started_at": c.started_at.isoformat() if c.started_at else None,
            "resolved_at": c.resolved_at.isoformat() if c.resolved_at else None,
        }
        for c in conversations
    ]


@router.get("/conversations/{conversation_id}/messages")
async def get_conversation_messages(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    chat_emp: ChatEmployee = Depends(get_chat_employee),
):
    """Get all messages for a specific conversation. Enforces ownership."""
    try:
        conv_id = UUID(conversation_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid conversation_id")

    # Verify conversation belongs to the authenticated employee
    conv_result = await db.execute(
        select(Conversation).where(
            Conversation.id == conv_id,
            Conversation.employee_id == chat_emp.employee_id,
            Conversation.tenant_id == chat_emp.tenant_id,
        )
    )
    conversation = conv_result.scalar_one_or_none()
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    msg_result = await db.execute(
        select(Message).where(
            Message.conversation_id == conv_id,
        ).order_by(Message.created_at.asc())
    )
    messages = msg_result.scalars().all()
    return {
        "conversation": {
            "id": str(conversation.id),
            "agent_name": conversation.agent_name,
            "status": conversation.status.value,
            "started_at": conversation.started_at.isoformat() if conversation.started_at else None,
        },
        "messages": [
            {
                "id": str(m.id),
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in messages
        ],
    }
