"""Approval workflow service — determines routing and handles approve/reject actions."""
import enum
import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee
from app.models.leave import LeaveRequest, LeaveBalance, LeaveStatus, LeaveType
from app.models.leave_policy import LeavePolicy

logger = logging.getLogger(__name__)


class ApprovalDecision(str, enum.Enum):
    auto_approved = "auto_approved"
    pending_manager = "pending_manager"
    pending_hr = "pending_hr"


@dataclass
class ApprovalResult:
    """Result of an approval routing decision."""
    decision: ApprovalDecision
    approver_id: UUID | None = None
    message: str = ""
    message_ar: str = ""


class ApprovalService:
    """Handles leave request approval routing, approve, and reject actions."""

    async def determine_approval_route(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        employee: Employee,
        leave_type: LeaveType,
        business_days: int,
    ) -> ApprovalResult:
        """Determine whether a leave request should be auto-approved or routed for approval."""
        # Fetch leave policy for this tenant + leave type
        policy_result = await db.execute(
            select(LeavePolicy).where(
                and_(
                    LeavePolicy.tenant_id == tenant_id,
                    LeavePolicy.leave_type == leave_type,
                    LeavePolicy.is_active == True,
                )
            )
        )
        policy = policy_result.scalar_one_or_none()

        # If no policy configured, default to pending_manager
        if not policy:
            return ApprovalResult(
                decision=ApprovalDecision.pending_manager,
                approver_id=employee.manager_id,
                message="Leave request sent to manager for approval.",
                message_ar="تم إرسال طلب الإجازة للمدير للموافقة.",
            )

        # Check auto-approve
        if policy.auto_approve:
            max_auto = policy.auto_approve_max_days
            if max_auto is None or business_days <= max_auto:
                return ApprovalResult(
                    decision=ApprovalDecision.auto_approved,
                    approver_id=None,
                    message="Your leave has been submitted and auto-approved.",
                    message_ar="تم تقديم طلب إجازتك والموافقة عليه تلقائياً.",
                )

        # Check if HR approval is required
        if policy.requires_hr_approval:
            return ApprovalResult(
                decision=ApprovalDecision.pending_hr,
                approver_id=None,
                message="Your leave request has been submitted and sent to HR for approval.",
                message_ar="تم تقديم طلب إجازتك وإرساله للموارد البشرية للموافقة.",
            )

        # Default: manager approval
        return ApprovalResult(
            decision=ApprovalDecision.pending_manager,
            approver_id=employee.manager_id,
            message="Your leave request has been submitted and sent to your manager for approval.",
            message_ar="تم تقديم طلب إجازتك وإرساله لمديرك للموافقة.",
        )

    async def approve(
        self,
        db: AsyncSession,
        request_id: UUID,
        approver_id: UUID,
        tenant_id: UUID,
    ) -> dict:
        """Approve a pending leave request."""
        # Fetch the leave request with tenant isolation
        result = await db.execute(
            select(LeaveRequest)
            .join(Employee, LeaveRequest.employee_id == Employee.id)
            .where(
                LeaveRequest.id == request_id,
                Employee.tenant_id == tenant_id,
            )
            .with_for_update()
        )
        leave_req = result.scalar_one_or_none()

        if not leave_req:
            return {
                "success": False,
                "message": "Leave request not found.",
                "message_ar": "لم يتم العثور على طلب الإجازة.",
            }

        if leave_req.status != LeaveStatus.pending:
            return {
                "success": False,
                "message": f"Cannot approve a {leave_req.status.value} request.",
                "message_ar": f"لا يمكن الموافقة على طلب بحالة {leave_req.status.value}.",
            }

        # Self-approval prevention: approver cannot approve their own leave
        if approver_id == leave_req.employee_id:
            return {
                "success": False,
                "message": "You cannot approve your own leave request.",
                "message_ar": "لا يمكنك الموافقة على طلب إجازتك الخاص.",
            }

        # Deduct balance on approval (balance was not deducted at submission for pending requests)
        balance_result = await db.execute(
            select(LeaveBalance).where(
                and_(
                    LeaveBalance.employee_id == leave_req.employee_id,
                    LeaveBalance.leave_type == leave_req.leave_type,
                    LeaveBalance.year == leave_req.start_date.year,
                )
            ).with_for_update()
        )
        balance = balance_result.scalar_one_or_none()

        if balance:
            # Account for other pending requests (exclude current) to prevent over-commitment
            other_pending_result = await db.execute(
                select(func.coalesce(func.sum(LeaveRequest.business_days), 0)).where(
                    and_(
                        LeaveRequest.employee_id == leave_req.employee_id,
                        LeaveRequest.leave_type == leave_req.leave_type,
                        LeaveRequest.status == LeaveStatus.pending,
                        LeaveRequest.id != leave_req.id,
                        LeaveRequest.start_date <= date(leave_req.start_date.year, 12, 31),
                        LeaveRequest.end_date >= date(leave_req.start_date.year, 1, 1),
                    )
                )
            )
            other_pending_days = other_pending_result.scalar_one()
            effective_remaining = balance.remaining_days - other_pending_days

            if leave_req.business_days > effective_remaining:
                return {
                    "success": False,
                    "message": (
                        f"Insufficient balance. Requested: {leave_req.business_days} days, "
                        f"Remaining: {balance.remaining_days} days"
                        f"{f', Reserved by other pending requests: {other_pending_days} days' if other_pending_days > 0 else ''}."
                    ),
                    "message_ar": (
                        f"رصيد غير كافٍ. المطلوب: {leave_req.business_days} يوم، "
                        f"المتبقي: {balance.remaining_days} يوم"
                        f"{f'، محجوز بطلبات معلقة أخرى: {other_pending_days} يوم' if other_pending_days > 0 else ''}."
                    ),
                }
            balance.used_days += leave_req.business_days

        # Update request
        leave_req.status = LeaveStatus.approved
        leave_req.approved_by = approver_id
        leave_req.approved_at = datetime.now(timezone.utc)

        # Finding 3: Send notification before commit so it's part of the same transaction.
        # If notification fails, the try/except catches it and the main commit still proceeds.
        try:
            from app.services.notification import NotificationService
            emp_result = await db.execute(
                select(Employee).where(Employee.id == leave_req.employee_id)
            )
            emp = emp_result.scalar_one_or_none()
            if emp:
                notif_svc = NotificationService(db, emp.tenant_id)
                await notif_svc.send(
                    employee_id=leave_req.employee_id,
                    title="Leave Request Approved",
                    title_ar="تمت الموافقة على طلب الإجازة",
                    body=f"Your {leave_req.leave_type.value} leave request from {leave_req.start_date.isoformat()} to {leave_req.end_date.isoformat()} has been approved.",
                    body_ar=f"تمت الموافقة على طلب إجازتك من {leave_req.start_date.isoformat()} إلى {leave_req.end_date.isoformat()}.",
                    category="leave",
                    resource_type="leave_request",
                    resource_id=leave_req.id,
                )
        except Exception as e:
            logger.warning("Failed to send approval notification: %s", e)

        await db.commit()

        return {
            "success": True,
            "message": "Leave request approved.",
            "message_ar": "تمت الموافقة على طلب الإجازة.",
            "request_id": str(leave_req.id),
            "employee_id": str(leave_req.employee_id),
        }

    async def reject(
        self,
        db: AsyncSession,
        request_id: UUID,
        rejector_id: UUID,
        tenant_id: UUID,
        reason: str | None = None,
    ) -> dict:
        """Reject a pending leave request and restore balance if needed."""
        result = await db.execute(
            select(LeaveRequest)
            .join(Employee, LeaveRequest.employee_id == Employee.id)
            .where(
                LeaveRequest.id == request_id,
                Employee.tenant_id == tenant_id,
            )
            .with_for_update()
        )
        leave_req = result.scalar_one_or_none()

        if not leave_req:
            return {
                "success": False,
                "message": "Leave request not found.",
                "message_ar": "لم يتم العثور على طلب الإجازة.",
            }

        if leave_req.status != LeaveStatus.pending:
            return {
                "success": False,
                "message": f"Cannot reject a {leave_req.status.value} request.",
                "message_ar": f"لا يمكن رفض طلب بحالة {leave_req.status.value}.",
            }

        # If balance was deducted at submission (auto-approved then somehow pending — edge case),
        # restore it. For normal pending requests, balance was not deducted.
        if leave_req.auto_approved:
            balance_result = await db.execute(
                select(LeaveBalance).where(
                    and_(
                        LeaveBalance.employee_id == leave_req.employee_id,
                        LeaveBalance.leave_type == leave_req.leave_type,
                        LeaveBalance.year == leave_req.start_date.year,
                    )
                ).with_for_update()
            )
            balance = balance_result.scalar_one_or_none()
            if balance:
                balance.used_days = max(0, balance.used_days - leave_req.business_days)

        leave_req.status = LeaveStatus.rejected
        leave_req.rejected_by = rejector_id
        leave_req.rejected_at = datetime.now(timezone.utc)
        leave_req.rejection_reason = reason

        # Finding 3: Send notification before commit — single transaction
        try:
            from app.services.notification import NotificationService
            emp_result = await db.execute(
                select(Employee).where(Employee.id == leave_req.employee_id)
            )
            emp = emp_result.scalar_one_or_none()
            if emp:
                reason_text = f" Reason: {reason}" if reason else ""
                reason_text_ar = f" السبب: {reason}" if reason else ""
                notif_svc = NotificationService(db, emp.tenant_id)
                await notif_svc.send(
                    employee_id=leave_req.employee_id,
                    title="Leave Request Rejected",
                    title_ar="تم رفض طلب الإجازة",
                    body=f"Your {leave_req.leave_type.value} leave request from {leave_req.start_date.isoformat()} to {leave_req.end_date.isoformat()} has been rejected.{reason_text}",
                    body_ar=f"تم رفض طلب إجازتك من {leave_req.start_date.isoformat()} إلى {leave_req.end_date.isoformat()}.{reason_text_ar}",
                    category="leave",
                    priority="high",
                    resource_type="leave_request",
                    resource_id=leave_req.id,
                )
        except Exception as e:
            logger.warning("Failed to send rejection notification: %s", e)

        await db.commit()

        return {
            "success": True,
            "message": "Leave request rejected.",
            "message_ar": "تم رفض طلب الإجازة.",
            "request_id": str(leave_req.id),
            "employee_id": str(leave_req.employee_id),
            "reason": reason,
        }

    async def get_pending_approvals(
        self,
        db: AsyncSession,
        approver_id: UUID,
        tenant_id: UUID,
    ) -> list[dict]:
        """Get all pending requests where employee.manager_id == approver_id or same department."""
        # First try direct manager relationship
        query = (
            select(LeaveRequest, Employee)
            .join(Employee, LeaveRequest.employee_id == Employee.id)
            .where(
                Employee.tenant_id == tenant_id,
                LeaveRequest.status == LeaveStatus.pending,
                Employee.manager_id == approver_id,
            )
            .order_by(LeaveRequest.created_at.desc())
        )

        result = await db.execute(query)
        rows = result.all()

        return [
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
