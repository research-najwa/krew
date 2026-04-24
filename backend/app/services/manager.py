"""Manager service — business logic for manager dashboard operations."""
import logging
from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee, EmployeeStatus, Department
from app.models.leave import LeaveRequest, LeaveBalance, LeaveStatus

logger = logging.getLogger(__name__)


class ManagerService:
    """Handles all manager-scoped operations for direct reports."""

    def __init__(self, db: AsyncSession, tenant_id: UUID, manager_id: UUID):
        self.db = db
        self.tenant_id = tenant_id
        self.manager_id = manager_id

    async def get_direct_report_ids(self) -> list[UUID]:
        """Return IDs of active direct reports for this manager."""
        result = await self.db.execute(
            select(Employee.id).where(
                Employee.tenant_id == self.tenant_id,
                Employee.manager_id == self.manager_id,
                Employee.status == EmployeeStatus.active,
            )
        )
        return list(result.scalars().all())

    async def get_team(self) -> list[dict]:
        """List direct reports with basic profile info."""
        result = await self.db.execute(
            select(Employee).where(
                Employee.tenant_id == self.tenant_id,
                Employee.manager_id == self.manager_id,
                Employee.status == EmployeeStatus.active,
            ).order_by(Employee.first_name)
        )
        employees = result.scalars().all()

        return [
            {
                "id": str(emp.id),
                "employee_number": emp.employee_number,
                "first_name": emp.first_name,
                "last_name": emp.last_name,
                "first_name_ar": emp.first_name_ar,
                "last_name_ar": emp.last_name_ar,
                "job_title": emp.job_title,
                "department_id": str(emp.department_id) if emp.department_id else None,
                "status": emp.status.value,
            }
            for emp in employees
        ]

    async def get_leave_calendar(
        self, start_date: date, end_date: date
    ) -> list[dict]:
        """Team leave calendar — approved and pending leaves overlapping date range."""
        report_ids = await self.get_direct_report_ids()
        if not report_ids:
            return []

        result = await self.db.execute(
            select(LeaveRequest, Employee)
            .join(Employee, LeaveRequest.employee_id == Employee.id)
            .where(
                LeaveRequest.employee_id.in_(report_ids),
                LeaveRequest.status.in_([LeaveStatus.approved, LeaveStatus.pending]),
                LeaveRequest.start_date <= end_date,
                LeaveRequest.end_date >= start_date,
            )
            .order_by(LeaveRequest.start_date)
        )
        rows = result.all()

        return [
            {
                "employee_name": emp.full_name,
                "leave_type": req.leave_type.value,
                "start_date": req.start_date.isoformat(),
                "end_date": req.end_date.isoformat(),
                "status": req.status.value,
            }
            for req, emp in rows
        ]

    async def get_pending_approvals(self) -> list[dict]:
        """Pending leave requests from direct reports."""
        report_ids = await self.get_direct_report_ids()
        if not report_ids:
            return []

        result = await self.db.execute(
            select(LeaveRequest, Employee)
            .join(Employee, LeaveRequest.employee_id == Employee.id)
            .where(
                LeaveRequest.employee_id.in_(report_ids),
                LeaveRequest.status == LeaveStatus.pending,
            )
            .order_by(LeaveRequest.created_at.desc())
        )
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

    async def approve_leave(self, request_id: UUID) -> dict:
        """Approve a leave request from a direct report. Deducts balance atomically."""
        report_ids = await self.get_direct_report_ids()

        # Fetch leave request with lock
        result = await self.db.execute(
            select(LeaveRequest)
            .join(Employee, LeaveRequest.employee_id == Employee.id)
            .where(
                LeaveRequest.id == request_id,
                Employee.tenant_id == self.tenant_id,
            )
            .with_for_update()
        )
        leave_req = result.scalar_one_or_none()

        if not leave_req:
            return {"success": False, "message": "Leave request not found."}

        if leave_req.employee_id not in report_ids:
            return {"success": False, "message": "This leave request does not belong to one of your direct reports."}

        if leave_req.status != LeaveStatus.pending:
            return {"success": False, "message": f"Cannot approve a {leave_req.status.value} request."}

        # Self-approval prevention
        if self.manager_id == leave_req.employee_id:
            return {"success": False, "message": "You cannot approve your own leave request."}

        # Deduct balance
        balance_result = await self.db.execute(
            select(LeaveBalance).where(
                and_(
                    LeaveBalance.employee_id == leave_req.employee_id,
                    LeaveBalance.leave_type == leave_req.leave_type,
                    LeaveBalance.year == leave_req.start_date.year,
                )
            ).with_for_update()
        )
        balance = balance_result.scalar_one_or_none()

        if not balance:
            return {"success": False, "message": "No leave balance record found for this type/year.", "message_ar": "لا يوجد سجل رصيد إجازات لهذا النوع/السنة."}

        if balance:
            if leave_req.business_days > balance.remaining_days:
                return {
                    "success": False,
                    "message": f"Insufficient balance. Requested: {leave_req.business_days} days, Remaining: {balance.remaining_days} days.",
                }
            balance.used_days += leave_req.business_days

        leave_req.status = LeaveStatus.approved
        leave_req.approved_by = self.manager_id
        leave_req.approved_at = datetime.now(timezone.utc)

        # Send notification
        try:
            from app.services.notification import NotificationService
            emp_result = await self.db.execute(
                select(Employee).where(Employee.id == leave_req.employee_id)
            )
            emp = emp_result.scalar_one_or_none()
            if emp:
                notif_svc = NotificationService(self.db, self.tenant_id)
                await notif_svc.send(
                    employee_id=leave_req.employee_id,
                    title="Leave Request Approved",
                    title_ar="تمت الموافقة على طلب الإجازة",
                    body=f"Your {leave_req.leave_type.value} leave from {leave_req.start_date.isoformat()} to {leave_req.end_date.isoformat()} has been approved by your manager.",
                    body_ar=f"تمت الموافقة على إجازتك من {leave_req.start_date.isoformat()} إلى {leave_req.end_date.isoformat()} من قبل مديرك.",
                    category="leave",
                    resource_type="leave_request",
                    resource_id=leave_req.id,
                )
        except Exception as e:
            logger.warning("Failed to send approval notification: %s", e)

        await self.db.commit()

        return {
            "success": True,
            "message": "Leave request approved.",
            "request_id": str(leave_req.id),
            "employee_id": str(leave_req.employee_id),
        }

    async def reject_leave(self, request_id: UUID, reason: str) -> dict:
        """Reject a leave request from a direct report."""
        report_ids = await self.get_direct_report_ids()

        result = await self.db.execute(
            select(LeaveRequest)
            .join(Employee, LeaveRequest.employee_id == Employee.id)
            .where(
                LeaveRequest.id == request_id,
                Employee.tenant_id == self.tenant_id,
            )
            .with_for_update()
        )
        leave_req = result.scalar_one_or_none()

        if not leave_req:
            return {"success": False, "message": "Leave request not found."}

        if leave_req.employee_id not in report_ids:
            return {"success": False, "message": "This leave request does not belong to one of your direct reports."}

        if leave_req.status != LeaveStatus.pending:
            return {"success": False, "message": f"Cannot reject a {leave_req.status.value} request."}

        leave_req.status = LeaveStatus.rejected
        leave_req.rejected_by = self.manager_id
        leave_req.rejected_at = datetime.now(timezone.utc)
        leave_req.rejection_reason = reason

        # Send notification
        try:
            from app.services.notification import NotificationService
            emp_result = await self.db.execute(
                select(Employee).where(Employee.id == leave_req.employee_id)
            )
            emp = emp_result.scalar_one_or_none()
            if emp:
                reason_text = f" Reason: {reason}" if reason else ""
                reason_text_ar = f" السبب: {reason}" if reason else ""
                notif_svc = NotificationService(self.db, self.tenant_id)
                await notif_svc.send(
                    employee_id=leave_req.employee_id,
                    title="Leave Request Rejected",
                    title_ar="تم رفض طلب الإجازة",
                    body=f"Your {leave_req.leave_type.value} leave from {leave_req.start_date.isoformat()} to {leave_req.end_date.isoformat()} has been rejected.{reason_text}",
                    body_ar=f"تم رفض إجازتك من {leave_req.start_date.isoformat()} إلى {leave_req.end_date.isoformat()}.{reason_text_ar}",
                    category="leave",
                    priority="high",
                    resource_type="leave_request",
                    resource_id=leave_req.id,
                )
        except Exception as e:
            logger.warning("Failed to send rejection notification: %s", e)

        await self.db.commit()

        return {
            "success": True,
            "message": "Leave request rejected.",
            "request_id": str(leave_req.id),
            "employee_id": str(leave_req.employee_id),
            "reason": reason,
        }

    async def get_headcount(self) -> dict:
        """Team headcount summary grouped by department, nationality, status."""
        # All direct reports (not just active — headcount includes all statuses)
        result = await self.db.execute(
            select(Employee).where(
                Employee.tenant_id == self.tenant_id,
                Employee.manager_id == self.manager_id,
            )
        )
        employees = result.scalars().all()

        total = len(employees)
        saudi_count = sum(1 for e in employees if e.is_saudi)
        non_saudi_count = total - saudi_count

        # Group by department
        dept_ids = set(e.department_id for e in employees if e.department_id)
        dept_names: dict[UUID, str] = {}
        if dept_ids:
            dept_result = await self.db.execute(
                select(Department.id, Department.name).where(Department.id.in_(dept_ids))
            )
            for row in dept_result:
                dept_names[row.id] = row.name

        by_department: dict[str, int] = {}
        for emp in employees:
            dept_name = dept_names.get(emp.department_id, "Unassigned") if emp.department_id else "Unassigned"
            by_department[dept_name] = by_department.get(dept_name, 0) + 1

        return {
            "total": total,
            "saudi_count": saudi_count,
            "non_saudi_count": non_saudi_count,
            "by_department": [
                {"department": dept, "count": count}
                for dept, count in sorted(by_department.items())
            ],
        }
