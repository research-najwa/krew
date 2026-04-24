"""Reporting API — HR manager dashboard reports."""
from typing import Any
from uuid import UUID
from datetime import date

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.admin_user import AdminUser, AdminRole
from app.auth.dependencies import require_role, require_tenant
from app.services.reporting import ReportingService

router = APIRouter(prefix="/reports", tags=["reports"])


class ReportResponse(BaseModel):
    """Generic report response — allows extra fields from service layer."""
    class Config:
        extra = "allow"


@router.get("/leave-utilization", response_model=ReportResponse)
async def leave_utilization_report(
    start_date: date | None = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: date | None = Query(None, description="End date (YYYY-MM-DD)"),
    department_id: UUID | None = Query(None),
    current_user: AdminUser = Depends(require_role(AdminRole.hr_manager)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Leave usage by type, department, and month. Top leave takers. Balance summary."""
    svc = ReportingService(db, tenant_id)
    return await svc.leave_utilization(start_date, end_date, department_id)


@router.get("/agent-performance", response_model=ReportResponse)
async def agent_performance_report(
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    current_user: AdminUser = Depends(require_role(AdminRole.hr_manager)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Agent messages, resolution rate, escalation rate, satisfaction scores."""
    svc = ReportingService(db, tenant_id)
    return await svc.agent_performance(start_date, end_date)


@router.get("/escalations", response_model=ReportResponse)
async def escalation_report(
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    current_user: AdminUser = Depends(require_role(AdminRole.hr_manager)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Escalation counts by status, category, urgency. Avg resolution time."""
    svc = ReportingService(db, tenant_id)
    return await svc.escalation_report(start_date, end_date)


@router.get("/headcount", response_model=ReportResponse)
async def headcount_report(
    department_id: UUID | None = Query(None),
    current_user: AdminUser = Depends(require_role(AdminRole.hr_manager)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Headcount by status, nationality, department, gender. Hire/termination trends."""
    svc = ReportingService(db, tenant_id)
    return await svc.headcount_report(department_id)


@router.get("/attendance", response_model=ReportResponse)
async def attendance_summary(
    department_id: UUID | None = Query(None),
    current_user: AdminUser = Depends(require_role(AdminRole.hr_manager)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Who is on leave today, this week, and upcoming."""
    svc = ReportingService(db, tenant_id)
    return await svc.attendance_summary(department_id)
