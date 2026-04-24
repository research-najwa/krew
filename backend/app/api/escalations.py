"""Escalation management API — for HR operators to handle escalated conversations."""
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.escalation import (
    EscalationTicket,
    EscalationStatus,
)
from app.models.conversation import Conversation, Message, ConversationStatus
from app.models.admin_user import AdminUser, AdminRole
from app.auth.dependencies import require_role, require_tenant

router = APIRouter(prefix="/escalations", tags=["escalations"])


# ── Response schemas ────────────────────────────────────────────────


class EscalationTicketOut(BaseModel):
    id: str
    tenant_id: str
    conversation_id: str | None
    employee_id: str
    agent_name: str
    category: str
    urgency: str
    reason: str
    summary: str | None
    status: str
    assigned_to: str | None
    resolved_at: str | None
    created_at: str


class EscalationDetailOut(BaseModel):
    ticket: EscalationTicketOut
    messages: list[dict]


class RespondBody(BaseModel):
    message: str
    assigned_to: str | None = None


class ResolveBody(BaseModel):
    resolution_note: str | None = None


# ── Endpoints ───────────────────────────────────────────────────────


@router.get("", response_model=list[EscalationTicketOut])
async def list_escalations(
    status: Optional[str] = Query(None),
    current_user: AdminUser = Depends(require_role(AdminRole.hr_specialist)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """List open escalation tickets by tenant."""
    query = select(EscalationTicket).where(
        EscalationTicket.tenant_id == tenant_id,
    ).order_by(EscalationTicket.created_at.desc())

    if status:
        try:
            esc_status = EscalationStatus(status)
            query = query.where(EscalationTicket.status == esc_status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
    else:
        # Default: show open and assigned tickets
        query = query.where(
            EscalationTicket.status.in_([EscalationStatus.open, EscalationStatus.assigned])
        )

    result = await db.execute(query)
    tickets = result.scalars().all()

    return [_ticket_to_out(t) for t in tickets]


@router.get("/{ticket_id}", response_model=EscalationDetailOut)
async def get_escalation(
    ticket_id: str,
    current_user: AdminUser = Depends(require_role(AdminRole.hr_specialist)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Get an escalation ticket with its conversation history."""
    try:
        t_uuid = UUID(ticket_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid ticket_id")

    result = await db.execute(
        select(EscalationTicket).where(
            EscalationTicket.id == t_uuid,
            EscalationTicket.tenant_id == tenant_id,
        )
    )
    ticket = result.scalar_one_or_none()

    if not ticket:
        raise HTTPException(status_code=404, detail="Escalation ticket not found")

    # Fetch conversation messages if conversation_id exists
    messages = []
    if ticket.conversation_id:
        msg_result = await db.execute(
            select(Message)
            .where(Message.conversation_id == ticket.conversation_id)
            .order_by(Message.created_at.asc())
        )
        messages = [
            {
                "id": str(m.id),
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at.isoformat(),
            }
            for m in msg_result.scalars().all()
        ]

    return EscalationDetailOut(
        ticket=_ticket_to_out(ticket),
        messages=messages,
    )


@router.post("/{ticket_id}/respond")
async def respond_to_escalation(
    ticket_id: str,
    body: RespondBody,
    current_user: AdminUser = Depends(require_role(AdminRole.hr_specialist)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """HR operator sends a response to an escalated conversation."""
    if not body.message or not body.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    try:
        t_uuid = UUID(ticket_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid ticket_id")

    result = await db.execute(
        select(EscalationTicket).where(
            EscalationTicket.id == t_uuid,
            EscalationTicket.tenant_id == tenant_id,
        )
    )
    ticket = result.scalar_one_or_none()

    if not ticket:
        raise HTTPException(status_code=404, detail="Escalation ticket not found")

    if ticket.status == EscalationStatus.resolved:
        raise HTTPException(status_code=400, detail="Ticket is already resolved")

    # Update ticket status and assignment
    ticket.status = EscalationStatus.assigned
    if body.assigned_to:
        ticket.assigned_to = body.assigned_to

    # Add HR response as a message in the conversation
    if ticket.conversation_id:
        db.add(Message(
            conversation_id=ticket.conversation_id,
            role="system",
            content=body.message,
            channel="web",
            language="ar",
        ))

    await db.commit()

    return {
        "status": "responded",
        "ticket_id": str(ticket.id),
        "message": "Response sent to employee. | تم إرسال الرد للموظف.",
    }


@router.patch("/{ticket_id}/resolve")
async def resolve_escalation(
    ticket_id: str,
    body: ResolveBody = ResolveBody(),
    current_user: AdminUser = Depends(require_role(AdminRole.hr_specialist)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Mark an escalation ticket as resolved."""
    try:
        t_uuid = UUID(ticket_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid ticket_id")

    result = await db.execute(
        select(EscalationTicket).where(
            EscalationTicket.id == t_uuid,
            EscalationTicket.tenant_id == tenant_id,
        )
    )
    ticket = result.scalar_one_or_none()

    if not ticket:
        raise HTTPException(status_code=404, detail="Escalation ticket not found")

    if ticket.status == EscalationStatus.resolved:
        raise HTTPException(status_code=400, detail="Ticket is already resolved")

    ticket.status = EscalationStatus.resolved
    ticket.resolved_at = datetime.now(timezone.utc)

    # Re-activate the conversation so the employee can continue chatting
    if ticket.conversation_id:
        conv_result = await db.execute(
            select(Conversation).where(Conversation.id == ticket.conversation_id)
        )
        conv = conv_result.scalar_one_or_none()
        if conv:
            conv.status = ConversationStatus.active

    await db.commit()

    return {
        "status": "resolved",
        "ticket_id": str(ticket.id),
        "resolved_at": ticket.resolved_at.isoformat(),
        "message": "Ticket resolved. Conversation re-activated. | تم حل التذكرة. تم إعادة تفعيل المحادثة.",
    }


# ── Helpers ──────────────────────────────────────────────────────────


def _ticket_to_out(ticket: EscalationTicket) -> EscalationTicketOut:
    return EscalationTicketOut(
        id=str(ticket.id),
        tenant_id=str(ticket.tenant_id),
        conversation_id=str(ticket.conversation_id) if ticket.conversation_id else None,
        employee_id=str(ticket.employee_id),
        agent_name=ticket.agent_name,
        category=ticket.category.value,
        urgency=ticket.urgency.value,
        reason=ticket.reason,
        summary=ticket.summary,
        status=ticket.status.value,
        assigned_to=ticket.assigned_to,
        resolved_at=ticket.resolved_at.isoformat() if ticket.resolved_at else None,
        created_at=ticket.created_at.isoformat(),
    )
