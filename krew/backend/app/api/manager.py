"""Manager dashboard API — endpoints scoped to a manager's direct reports."""
import re
from datetime import date, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.employee import Employee, EmployeeStatus
from app.models.admin_user import AdminUser, AdminRole
from app.auth.dependencies import require_role, require_tenant
from app.services.manager import ManagerService

router = APIRouter(prefix="/manager", tags=["manager"])


# ── Request / Response schemas ─────────────────────────────────────

def _strip_html_tags(text: str) -> str:
    """Remove HTML tags to prevent stored XSS."""
    return re.sub(r"<[^>]+>", "", text)


class RejectBody(BaseModel):
    reason: str = Field(..., max_length=1000)


# ── Manager verification dependency ───────────────────────────────

async def require_manager(
    current_user: AdminUser = Depends(require_role(AdminRole.hr_specialist)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
) -> tuple[UUID, UUID]:
    """Verify the current admin user is linked to an employee who is a manager.

    Returns (manager_employee_id, tenant_id).
    """
    # Resolve admin user to employee record
    emp_result = await db.execute(
        select(Employee).where(
            Employee.tenant_id == tenant_id,
            Employee.email == current_user.email,
        )
    )
    manager_emp = emp_result.scalar_one_or_none()
    if manager_emp is None:
        raise HTTPException(
            status_code=400,
            detail="Your admin account is not linked to an employee record.",
        )

    # Check that this employee has direct reports
    report_result = await db.execute(
        select(Employee.id).where(
            Employee.tenant_id == tenant_id,
            Employee.manager_id == manager_emp.id,
            Employee.status == EmployeeStatus.active,
        ).limit(1)
    )
    if report_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=403,
            detail="You are not a manager. No direct reports found.",
        )

    return (manager_emp.id, tenant_id)


# ── Endpoints ──────────────────────────────────────────────────────

@router.get("/team")
async def get_team(
    manager_info: tuple[UUID, UUID] = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
):
    """List direct reports for the current manager."""
    manager_id, tenant_id = manager_info
    svc = ManagerService(db, tenant_id, manager_id)
    return await svc.get_team()


@router.get("/leave-calendar")
async def get_leave_calendar(
    start_date: date | None = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: date | None = Query(None, description="End date (YYYY-MM-DD)"),
    manager_info: tuple[UUID, UUID] = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
):
    """Team leave calendar showing approved and pending leaves."""
    manager_id, tenant_id = manager_info

    # Default to current month
    if not start_date:
        today = date.today()
        start_date = today.replace(day=1)
    if not end_date:
        # Last day of month
        if start_date.month == 12:
            end_date = start_date.replace(year=start_date.year + 1, month=1, day=1)
        else:
            end_date = start_date.replace(month=start_date.month + 1, day=1)
        end_date = end_date - timedelta(days=1)

    svc = ManagerService(db, tenant_id, manager_id)
    return await svc.get_leave_calendar(start_date, end_date)


@router.get("/pending-approvals")
async def get_pending_approvals(
    manager_info: tuple[UUID, UUID] = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
):
    """Pending leave requests from direct reports."""
    manager_id, tenant_id = manager_info
    svc = ManagerService(db, tenant_id, manager_id)
    return await svc.get_pending_approvals()


@router.post("/approve-leave/{request_id}")
async def approve_leave(
    request_id: UUID,
    manager_info: tuple[UUID, UUID] = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
):
    """Approve a pending leave request from a direct report."""
    manager_id, tenant_id = manager_info
    svc = ManagerService(db, tenant_id, manager_id)
    result = await svc.approve_leave(request_id)

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])

    return result


@router.post("/reject-leave/{request_id}")
async def reject_leave(
    request_id: UUID,
    body: RejectBody,
    manager_info: tuple[UUID, UUID] = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
):
    """Reject a pending leave request from a direct report."""
    sanitized_reason = _strip_html_tags(body.reason).strip()

    manager_id, tenant_id = manager_info
    svc = ManagerService(db, tenant_id, manager_id)
    result = await svc.reject_leave(request_id, sanitized_reason)

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])

    return result


@router.get("/headcount")
async def get_headcount(
    manager_info: tuple[UUID, UUID] = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
):
    """Team headcount summary for the current manager's direct reports."""
    manager_id, tenant_id = manager_info
    svc = ManagerService(db, tenant_id, manager_id)
    return await svc.get_headcount()
