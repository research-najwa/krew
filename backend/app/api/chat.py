"""Web chat endpoint -- unified chat with @mention routing."""
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

# Agent display info -- synced with agentMap/agentColors in chat.html
AGENT_DISPLAY = {
    "deema":    {"name": "Deema",    "name_ar": "ديمة",  "role": "Employee Services",   "role_ar": "خدمات الموظفين",   "color": "#4F46E5", "letter": "D"},
    "waleed":   {"name": "Waleed",   "name_ar": "وليد",  "role": "Onboarding",          "role_ar": "التهيئة",          "color": "#16A34A", "letter": "W"},
    "mohammad": {"name": "Mohammad", "name_ar": "محمد",  "role": "Recruitment",         "role_ar": "التوظيف",          "color": "#2563EB", "letter": "M"},
    "yara":     {"name": "Yara",     "name_ar": "يارا",  "role": "Agent Factory",       "role_ar": "مصنع الوكلاء",     "color": "#CA8A04", "letter": "Y"},
    "ahmad":    {"name": "Ahmad",    "name_ar": "أحمد",  "role": "CHRO Analytics",      "role_ar": "تحليلات الموارد",   "color": "#1E3A5F", "letter": "A"},
}


class ChatRequest(BaseModel):
    employee_id: str = ""  # Ignored when authenticated -- kept for backward compat
    message: str
    agent: str = ""  # Optional: UI passes this when user explicitly selected an agent
    conversation_id: str = ""  # Optional: resume a specific conversation


class ChatResponse(BaseModel):
    agent: str                        # existing -- canonical agent name
    agent_display_name: str = ""      # human-readable name ("Deema")
    agent_name_ar: str = ""           # Arabic name for bilingual UI
    agent_color: str = ""             # hex color for UI badge
    response: str                     # existing
    conversation_id: str              # existing
    topic: str = ""                   # existing
    suggestions: list[str] = []       # existing
    available_agents: list[dict] = [] # access-filtered list for @mention autocomplete
    routed_by: str = ""               # "mention" | "keyword" | "sticky" | "switch" | "default" | "error"


@router.post("", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    chat_emp: ChatEmployee = Depends(get_chat_employee),
):
    """Send a message as an employee and get a response from a Krew agent."""
    # Use employee_id from JWT token -- never trust the request body
    emp_id = chat_emp.employee_id

    # Rate limit before validation to avoid wasting CPU on flood attacks
    # IP-based limit prevents rotating employee_ids to bypass per-employee limit
    await check_chat_ip_rate_limit(request)
    await check_chat_rate_limit(str(emp_id))

    cleaned_message = validate_chat_message(req.message)

    # Find employee -- enforce tenant isolation + active/onboarding status
    result = await db.execute(
        select(Employee).where(
            Employee.id == emp_id,
            Employee.tenant_id == chat_emp.tenant_id,
            Employee.status.in_([EmployeeStatus.active, EmployeeStatus.onboarding]),
        )
    )
    employee = result.scalar_one_or_none()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    # Derive employee role for access control
    from app.utils.employee_role import derive_employee_role
    from app.utils.agent_access import get_accessible_agents

    employee_role = await derive_employee_role(db, chat_emp.tenant_id, emp_id)
    employee_dept_id = employee.department_id

    # Find or create web conversation -- enforce tenant isolation
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

    # Check if conversation is escalated -- block agent response
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

    # Load conversation history -- newest 20 messages, then reverse to chronological
    # Exclude system messages (escalation notices etc.) -- Claude only expects user/assistant
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
    # "pending" means new conversation -- let the router decide based on message content
    current_agent = req.agent if req.agent else (stored_agent if stored_agent != "pending" else None)

    # Load last_mentioned_agent from conversation for sticky @mention routing
    last_mentioned = getattr(conversation, 'last_mentioned_agent', None)

    orchestrator = AgentOrchestrator(db, employee.tenant_id)
    agent_name, response, new_last_mentioned = await orchestrator.handle_message(
        message=cleaned_message,
        employee_name=employee.first_name,
        employee_id=str(employee.id),
        conversation_history=history,
        current_agent=current_agent,
        language=employee.preferred_language,
        conversation_id=conversation.id,
        # @mention routing parameters
        last_mentioned_agent=last_mentioned,
        employee_role=employee_role,
        employee_dept_id=employee_dept_id,
    )

    # Update conversation state
    conversation.agent_name = agent_name
    conversation.last_mentioned_agent = new_last_mentioned

    # Generate topic on first exchange (when topic is still empty)
    if not conversation.topic:
        conversation.topic = _generate_quick_title(cleaned_message)

    # Save messages -- add agent_name for per-agent context filtering (UC-04)
    db.add(Message(
        conversation_id=conversation.id,
        role="employee",
        content=cleaned_message,
        channel="web",
        language=employee.preferred_language,
        agent_name=agent_name,
    ))
    db.add(Message(
        conversation_id=conversation.id,
        role="agent",
        content=response,
        channel="web",
        language=employee.preferred_language,
        agent_name=agent_name,
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

    # Build access-filtered available agents list for autocomplete
    accessible = await get_accessible_agents(
        db, chat_emp.tenant_id, emp_id, employee_role, employee_dept_id,
    )
    available_agents = []
    for a_name in accessible:
        info = AGENT_DISPLAY.get(a_name)
        if info:
            available_agents.append({
                "name": a_name,
                "display_name": info["name"],
                "name_ar": info["name_ar"],
                "role": info["role"],
                "role_ar": info["role_ar"],
                "color": info["color"],
                "letter": info["letter"],
            })
        elif a_name.startswith("dept:"):
            # Dynamic agent -- fetch display info from DB
            da = await orchestrator.get_dynamic_agent(a_name)
            if da:
                config = da._config  # DeployedAgent row
                available_agents.append({
                    "name": a_name,
                    "display_name": config.name,
                    "name_ar": config.name_ar or config.name,
                    "role": config.role_title,
                    "role_ar": config.role_title_ar or config.role_title,
                    "color": "#DB2777",  # Default pink for deployed agents
                    "letter": config.name[0].upper(),
                })

    # Determine routing method for UI indicator
    from app.utils.mention_parser import parse_mention
    mentioned, _ = parse_mention(req.message)
    if agent_name == "system":
        routed_by = "error"
    elif mentioned is not None:
        routed_by = "mention"
    elif last_mentioned and agent_name == last_mentioned:
        routed_by = "sticky"
    elif any(any(p in cleaned_message.lower() for p in phrases) for phrases in orchestrator.SWITCH_PHRASES.values()):
        routed_by = "switch"
    else:
        routed_by = "keyword"

    agent_info = AGENT_DISPLAY.get(agent_name, {})

    return ChatResponse(
        agent=agent_name,
        agent_display_name=agent_info.get("name", agent_name.capitalize()),
        agent_name_ar=agent_info.get("name_ar", ""),
        agent_color=agent_info.get("color", "#6B7280"),
        response=response,
        conversation_id=str(conversation.id),
        topic=conversation.topic or "",
        suggestions=suggestions,
        available_agents=available_agents,
        routed_by=routed_by,
    )


def _generate_quick_title(message: str) -> str:
    """Instant title from the first message -- truncated at word boundary."""
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


@router.get("/agent-access/me")
async def get_my_accessible_agents(
    db: AsyncSession = Depends(get_db),
    chat_emp: ChatEmployee = Depends(get_chat_employee),
):
    """Get agents accessible to the currently authenticated employee."""
    from app.utils.employee_role import derive_employee_role
    from app.utils.agent_access import get_accessible_agents
    from app.models.employee import Employee

    emp_result = await db.execute(
        select(Employee).where(
            Employee.id == chat_emp.employee_id,
            Employee.tenant_id == chat_emp.tenant_id,
        )
    )
    emp = emp_result.scalar_one_or_none()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    role = await derive_employee_role(db, chat_emp.tenant_id, chat_emp.employee_id)
    accessible = await get_accessible_agents(
        db, chat_emp.tenant_id, chat_emp.employee_id, role, emp.department_id,
    )

    result = []
    for a_name in accessible:
        info = AGENT_DISPLAY.get(a_name)
        if info:
            result.append({
                "name": a_name,
                "display_name": info["name"],
                "name_ar": info["name_ar"],
                "role": info["role"],
                "role_ar": info["role_ar"],
                "color": info["color"],
                "letter": info["letter"],
            })
    return {"agents": result, "employee_role": role}


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
    """List tenants for the chat UI login form -- rate-limited, no auth required."""
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

    # Enforce ownership -- token employee must match path employee
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
                "agent_name": getattr(m, 'agent_name', None),
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in messages
        ],
    }
