"""Leave approvals API — approval workflow endpoints for HR."""
import re
from datetime import date, datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, and_, func, cast, String
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.employee import Employee
from app.models.leave import LeaveRequest, LeaveStatus, LeaveType
from app.models.leave_policy import LeavePolicy
from app.models.admin_user import AdminUser, AdminRole
from app.auth.dependencies import require_role, require_tenant
from app.services.approval import ApprovalService
from app.security.audit import emit_audit_event

router = APIRouter(prefix="/approvals", tags=["approvals"])


# ── Request / Response schemas ─────────────────────────────────────

def _strip_html_tags(text: str) -> str:
    """Remove HTML tags to prevent stored XSS."""
    return re.sub(r"<[^>]+>", "", text)


class RejectBody(BaseModel):
    reason: str = Field(..., max_length=1000)


class LeavePolicyUpdate(BaseModel):
    default_days_per_year: int | None = None
    extended_days_per_year: int | None = None
    tenure_threshold_years: int | None = None
    min_days_per_request: int | None = None
    max_days_per_request: int | None = None
    advance_notice_days: int | None = None
    requires_attachment: bool | None = None
    attachment_after_days: int | None = None
    auto_approve: bool | None = None
    auto_approve_max_days: int | None = None
    requires_manager_approval: bool | None = None
    requires_hr_approval: bool | None = None
    blocked_during_probation: bool | None = None
    blackout_periods: list | None = None
    max_carry_over_days: int | None = None
    is_active: bool | None = None


class LeavePolicyOut(BaseModel):
    id: str
    leave_type: str
    default_days_per_year: int
    extended_days_per_year: int | None
    tenure_threshold_years: int | None
    min_days_per_request: int
    max_days_per_request: int | None
    advance_notice_days: int
    requires_attachment: bool
    attachment_after_days: int | None
    auto_approve: bool
    auto_approve_max_days: int | None
    requires_manager_approval: bool
    requires_hr_approval: bool
    blocked_during_probation: bool
    blackout_periods: list | None
    max_carry_over_days: int | None
    is_active: bool


# ── Endpoints ──────────────────────────────────────────────────────

@router.get("/pending")
async def get_pending_approvals(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: AdminUser = Depends(require_role(AdminRole.hr_specialist)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """List pending leave requests for the current approver."""
    # HR specialists and above see all pending requests in the tenant via SQL pagination
    base_query = (
        select(LeaveRequest, Employee)
        .join(Employee, LeaveRequest.employee_id == Employee.id)
        .where(
            Employee.tenant_id == tenant_id,
            LeaveRequest.status == LeaveStatus.pending,
        )
        .order_by(LeaveRequest.created_at.desc())
    )

    # Count total
    count_query = (
        select(func.count(LeaveRequest.id))
        .join(Employee, LeaveRequest.employee_id == Employee.id)
        .where(
            Employee.tenant_id == tenant_id,
            LeaveRequest.status == LeaveStatus.pending,
        )
    )
    total = (await db.execute(count_query)).scalar_one()

    # SQL pagination
    paginated_query = base_query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(paginated_query)
    rows = result.all()

    items = [
        {
            "request_id": str(req.id),
            "employee_id": str(emp.id),
            "employee_name": emp.full_name,
            "employee_number": emp.employee_number,
            "leave_type": req.leave_type.value,
            "start_date": req.start_date.isoformat(),
            "end_date": req.end_date.isoformat(),
            "business_days": req.business_days,
            "reason": req.reason,
            "created_at": req.created_at.isoformat(),
        }
        for req, emp in rows
    ]

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": items,
    }


@router.patch("/{request_id}/approve")
async def approve_request(
    request_id: str,
    http_request: Request,
    current_user: AdminUser = Depends(require_role(AdminRole.hr_specialist)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Approve a pending leave request."""
    try:
        req_uuid = UUID(request_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid request_id")

    # Resolve approver employee ID from admin user
    emp_result = await db.execute(
        select(Employee).where(
            Employee.tenant_id == tenant_id,
            Employee.email == current_user.email,
        )
    )
    approver_emp = emp_result.scalar_one_or_none()
    if approver_emp is None:
        raise HTTPException(
            status_code=400,
            detail="Your admin account is not linked to an employee record.",
        )
    approver_id = approver_emp.id

    approval_svc = ApprovalService()
    result = await approval_svc.approve(
        db=db,
        request_id=req_uuid,
        approver_id=approver_id,
        tenant_id=tenant_id,
    )

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])

    await emit_audit_event(
        db, action="leave.approve", actor_id=str(current_user.id),
        actor_email=current_user.email, tenant_id=str(tenant_id),
        resource_type="leave_request", resource_id=request_id,
        detail={"employee_id": result.get("employee_id")},
        request=http_request,
    )

    return result


@router.patch("/{request_id}/reject")
async def reject_request(
    request_id: str,
    http_request: Request,
    body: RejectBody,
    current_user: AdminUser = Depends(require_role(AdminRole.hr_specialist)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Reject a pending leave request."""
    try:
        req_uuid = UUID(request_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid request_id")

    emp_result = await db.execute(
        select(Employee).where(
            Employee.tenant_id == tenant_id,
            Employee.email == current_user.email,
        )
    )
    rejector_emp = emp_result.scalar_one_or_none()
    if rejector_emp is None:
        raise HTTPException(
            status_code=400,
            detail="Your admin account is not linked to an employee record.",
        )
    rejector_id = rejector_emp.id

    sanitized_reason = _strip_html_tags(body.reason).strip()

    approval_svc = ApprovalService()
    result = await approval_svc.reject(
        db=db,
        request_id=req_uuid,
        rejector_id=rejector_id,
        tenant_id=tenant_id,
        reason=sanitized_reason,
    )

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])

    await emit_audit_event(
        db, action="leave.reject", actor_id=str(current_user.id),
        actor_email=current_user.email, tenant_id=str(tenant_id),
        resource_type="leave_request", resource_id=request_id,
        detail={"employee_id": result.get("employee_id"), "reason": sanitized_reason},
        request=http_request,
    )

    return result


@router.get("/history")
async def approval_history(
    status: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: AdminUser = Depends(require_role(AdminRole.hr_specialist)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Past approval/rejection actions by this user."""
    # Find the employee record for this admin user
    emp_result = await db.execute(
        select(Employee).where(
            Employee.tenant_id == tenant_id,
            Employee.email == current_user.email,
        )
    )
    approver_emp = emp_result.scalar_one_or_none()

    if not approver_emp:
        return {"total": 0, "page": page, "page_size": page_size, "items": []}

    query = (
        select(LeaveRequest, Employee)
        .join(Employee, LeaveRequest.employee_id == Employee.id)
        .where(
            Employee.tenant_id == tenant_id,
            (LeaveRequest.approved_by == approver_emp.id) | (LeaveRequest.rejected_by == approver_emp.id),
        )
        .order_by(LeaveRequest.created_at.desc())
    )

    if status:
        try:
            leave_status = LeaveStatus(status)
            query = query.where(LeaveRequest.status == leave_status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    if date_from:
        try:
            df = date.fromisoformat(date_from)
            query = query.where(LeaveRequest.created_at >= datetime(df.year, df.month, df.day, tzinfo=timezone.utc))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date_from format")

    if date_to:
        try:
            dt_val = date.fromisoformat(date_to)
            query = query.where(LeaveRequest.created_at <= datetime(dt_val.year, dt_val.month, dt_val.day, 23, 59, 59, tzinfo=timezone.utc))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date_to format")

    # Count total matching rows
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar_one()

    # SQL pagination
    paginated_query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(paginated_query)
    page_rows = result.all()

    items = []
    for req, emp in page_rows:
        items.append({
            "request_id": str(req.id),
            "employee_id": str(emp.id),
            "employee_name": emp.full_name,
            "leave_type": req.leave_type.value,
            "start_date": req.start_date.isoformat(),
            "end_date": req.end_date.isoformat(),
            "business_days": req.business_days,
            "status": req.status.value,
            "reason": req.reason,
            "rejection_reason": req.rejection_reason,
            "approved_at": req.approved_at.isoformat() if req.approved_at else None,
            "rejected_at": req.rejected_at.isoformat() if req.rejected_at else None,
            "created_at": req.created_at.isoformat(),
        })

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": items,
    }


@router.get("/leave-policies", response_model=list[LeavePolicyOut])
async def list_leave_policies(
    current_user: AdminUser = Depends(require_role(AdminRole.hr_manager)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """List all leave policies for the tenant."""
    result = await db.execute(
        select(LeavePolicy)
        .where(LeavePolicy.tenant_id == tenant_id)
        .order_by(LeavePolicy.leave_type)
    )
    policies = result.scalars().all()

    return [
        LeavePolicyOut(
            id=str(p.id),
            leave_type=p.leave_type.value,
            default_days_per_year=p.default_days_per_year,
            extended_days_per_year=p.extended_days_per_year,
            tenure_threshold_years=p.tenure_threshold_years,
            min_days_per_request=p.min_days_per_request,
            max_days_per_request=p.max_days_per_request,
            advance_notice_days=p.advance_notice_days,
            requires_attachment=p.requires_attachment,
            attachment_after_days=p.attachment_after_days,
            auto_approve=p.auto_approve,
            auto_approve_max_days=p.auto_approve_max_days,
            requires_manager_approval=p.requires_manager_approval,
            requires_hr_approval=p.requires_hr_approval,
            blocked_during_probation=p.blocked_during_probation,
            blackout_periods=p.blackout_periods,
            max_carry_over_days=p.max_carry_over_days,
            is_active=p.is_active,
        )
        for p in policies
    ]


@router.put("/leave-policies/{leave_type}")
async def update_leave_policy(
    leave_type: str,
    body: LeavePolicyUpdate,
    http_request: Request,
    current_user: AdminUser = Depends(require_role(AdminRole.hr_manager)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Update a leave policy for the tenant."""
    try:
        lt = LeaveType(leave_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid leave type: {leave_type}")

    # Note: leave_policies.leave_type is a varchar column, so we cast to String
    # to avoid "character varying = leavetype" operator mismatches.
    result = await db.execute(
        select(LeavePolicy).where(
            LeavePolicy.tenant_id == tenant_id,
            cast(LeavePolicy.leave_type, String) == lt.value,
        )
    )
    policy = result.scalar_one_or_none()

    if not policy:
        raise HTTPException(status_code=404, detail=f"No policy found for leave type: {leave_type}")

    # Update only provided fields (including None to clear nullable fields)
    update_data = body.model_dump(exclude_unset=True)

    # Finding 13: Cap auto_approve_max_days at 30 to prevent approval bypass
    if "auto_approve_max_days" in update_data and update_data["auto_approve_max_days"] is not None:
        if update_data["auto_approve_max_days"] > 30:
            raise HTTPException(
                status_code=400,
                detail="auto_approve_max_days cannot exceed 30 days.",
            )

    # Capture old values before applying changes for audit trail
    old_values = {}
    for field_name in update_data:
        old_values[field_name] = getattr(policy, field_name, None)
        # Serialize enums for JSON compatibility
        if hasattr(old_values[field_name], "value"):
            old_values[field_name] = old_values[field_name].value

    for field_name, value in update_data.items():
        setattr(policy, field_name, value)

    # Log warning if auto_approve is being changed
    if "auto_approve" in update_data:
        import logging as _logging
        _logger = _logging.getLogger(__name__)
        _logger.warning(
            "auto_approve changed for %s policy by %s: %s -> %s",
            leave_type, current_user.email,
            old_values.get("auto_approve"), update_data["auto_approve"],
        )

    await emit_audit_event(
        db, action="leave_policy.update", actor_id=str(current_user.id),
        actor_email=current_user.email, tenant_id=str(tenant_id),
        resource_type="leave_policy", resource_id=str(policy.id),
        detail={
            "leave_type": leave_type,
            "updates": update_data,
            "previous_values": old_values,
        },
        request=http_request,
    )

    await db.commit()

    return {"status": "updated", "leave_type": leave_type, "updated_fields": list(update_data.keys())}
