"""Dashboard API — powers the CHRO view and admin panel."""
from uuid import UUID
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.database import get_db
from app.models.conversation import Conversation, ConversationStatus
from app.models.employee import Employee, EmployeeStatus
from app.models.leave import LeaveRequest, LeaveStatus
from app.models.compliance import ComplianceAlert
from app.models.admin_user import AdminUser, AdminRole
from app.auth.dependencies import require_role, require_tenant

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


class DashboardStats(BaseModel):
    total_employees: int
    active_conversations: int
    auto_resolution_rate: float
    avg_response_time_seconds: float
    pending_leave_requests: int
    open_compliance_alerts: int
    saudization_percentage: float


@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    current_user: AdminUser = Depends(require_role(AdminRole.hr_specialist)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Get overview stats for the CHRO dashboard."""
    # Total employees
    total = (await db.execute(
        select(func.count(Employee.id)).where(
            Employee.tenant_id == tenant_id,
            Employee.status == EmployeeStatus.active,
        )
    )).scalar_one()

    # Active conversations
    active_convos = (await db.execute(
        select(func.count(Conversation.id)).where(
            Conversation.tenant_id == tenant_id,
            Conversation.status == ConversationStatus.active,
        )
    )).scalar_one()

    # Auto-resolution rate (last 30 days)
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    total_resolved = (await db.execute(
        select(func.count(Conversation.id)).where(
            Conversation.tenant_id == tenant_id,
            Conversation.status == ConversationStatus.resolved,
            Conversation.started_at >= thirty_days_ago,
        )
    )).scalar_one()

    auto_resolved = (await db.execute(
        select(func.count(Conversation.id)).where(
            Conversation.tenant_id == tenant_id,
            Conversation.status == ConversationStatus.resolved,
            Conversation.resolved_automatically == True,
            Conversation.started_at >= thirty_days_ago,
        )
    )).scalar_one()

    resolution_rate = (auto_resolved / total_resolved * 100) if total_resolved > 0 else 0

    # Pending leave requests
    pending_leaves = (await db.execute(
        select(func.count(LeaveRequest.id))
        .join(Employee, LeaveRequest.employee_id == Employee.id)
        .where(
            Employee.tenant_id == tenant_id,
            LeaveRequest.status == LeaveStatus.pending,
        )
    )).scalar_one()

    # Open compliance alerts
    open_alerts = (await db.execute(
        select(func.count(ComplianceAlert.id)).where(
            ComplianceAlert.tenant_id == tenant_id,
            ComplianceAlert.is_resolved == False,
        )
    )).scalar_one()

    # Saudization percentage
    saudi_count = (await db.execute(
        select(func.count(Employee.id)).where(
            Employee.tenant_id == tenant_id,
            Employee.status == EmployeeStatus.active,
            Employee.is_saudi == True,
        )
    )).scalar_one()

    saudization = (saudi_count / total * 100) if total > 0 else 0

    return DashboardStats(
        total_employees=total,
        active_conversations=active_convos,
        auto_resolution_rate=round(resolution_rate, 1),
        avg_response_time_seconds=12.0,  # TODO: compute from message timestamps
        pending_leave_requests=pending_leaves,
        open_compliance_alerts=open_alerts,
        saudization_percentage=round(saudization, 1),
    )


@router.get("/conversations")
async def get_recent_conversations(
    limit: int = 20,
    current_user: AdminUser = Depends(require_role(AdminRole.hr_specialist)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Get recent conversations for the admin view."""
    result = await db.execute(
        select(Conversation)
        .where(Conversation.tenant_id == tenant_id)
        .order_by(Conversation.started_at.desc())
        .limit(limit)
    )
    conversations = result.scalars().all()

    return [
        {
            "id": str(c.id),
            "employee_id": str(c.employee_id),
            "agent": c.agent_name,
            "channel": c.channel,
            "status": c.status.value,
            "topic": c.topic,
            "started_at": c.started_at.isoformat(),
        }
        for c in conversations
    ]
