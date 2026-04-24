"""Leave management service — business logic for Saudi labor law compliant leave."""
import uuid
import logging
from datetime import date, datetime, timedelta, timezone
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee
from app.models.leave import (
    LeaveRequest,
    LeaveBalance,
    LeaveType,
    LeaveStatus,
)
from app.saudi_holidays import get_saudi_holidays
from app.models.leave_policy import LeavePolicy
from app.services.labor_law import SaudiLaborLawEngine
from app.services.approval import ApprovalService, ApprovalDecision

logger = logging.getLogger(__name__)

LEAVE_TYPE_AR = {
    "annual": "سنوية",
    "sick": "مرضية",
    "emergency": "طوارئ",
    "maternity": "أمومة",
    "paternity": "أبوة",
    "hajj": "حج",
    "bereavement": "وفاة",
    "unpaid": "بدون راتب",
}


def _ar(leave_type) -> str:
    """Return Arabic name for a leave type (enum or string)."""
    val = leave_type.value if hasattr(leave_type, "value") else leave_type
    return LEAVE_TYPE_AR.get(val, val)


def calculate_business_days(start: date, end: date) -> int:
    """Calculate business days between two dates using Saudi weekend (Fri/Sat).

    Saudi Arabia's official weekend is Friday and Saturday.
    This counts all days from start to end (inclusive) that are
    Sunday through Thursday.

    Args:
        start: Start date (inclusive).
        end: End date (inclusive).

    Returns:
        Number of business days.

    Raises:
        ValueError: If end date is before start date.
    """
    if end < start:
        raise ValueError(
            f"End date ({end}) cannot be before start date ({start})"
        )

    # Collect public holidays for all years in the range
    holiday_set = set(get_saudi_holidays(start.year))
    if end.year != start.year:
        holiday_set.update(get_saudi_holidays(end.year))

    business_days = 0
    current = start
    while current <= end:
        weekday = current.weekday()  # Monday=0, ..., Friday=4, Saturday=5, Sunday=6
        if weekday not in (4, 5) and current not in holiday_set:
            business_days += 1
        current += timedelta(days=1)

    return business_days


async def check_and_submit_leave(
    db: AsyncSession,
    employee_id: uuid.UUID,
    leave_type: str | LeaveType,
    start_date: date,
    end_date: date,
    reason: str | None = None,
    channel: str = "whatsapp",
    agent: str = "deema",
    tenant_id: uuid.UUID | None = None,
) -> dict:
    """Validate and submit a leave request.

    Business rules:
    1. End date must be on or after start date.
    2. Start date must not be in the past.
    3. Employee must have a leave balance for the type and current year.
    4. Remaining balance must be sufficient for the requested business days.
    5. On success, create the request and deduct from balance.

    Args:
        db: Async database session.
        employee_id: The employee submitting the request.
        leave_type: Type of leave (annual, sick, etc.).
        start_date: Requested start date.
        end_date: Requested end date.
        reason: Optional reason for the leave.
        channel: Channel the request came through.
        agent: Agent that processed the request.

    Returns:
        Status dict with keys:
            - success: bool
            - message: str (human-readable status, suitable for agent response)
            - message_ar: str (Arabic translation of the message)
            - request_id: UUID (only if success=True)
            - business_days: int (only if success=True)
    """
    # Normalize leave_type to enum
    if isinstance(leave_type, str):
        try:
            leave_type = LeaveType(leave_type)
        except ValueError:
            valid_types = ", ".join(t.value for t in LeaveType)
            return {
                "success": False,
                "message": f"Invalid leave type '{leave_type}'. Valid types: {valid_types}",
                "message_ar": f"نوع الإجازة '{leave_type}' غير صالح. الأنواع المتاحة: {valid_types}",
            }

    # Validate dates
    if end_date < start_date:
        return {
            "success": False,
            "message": "End date cannot be before start date.",
            "message_ar": "تاريخ النهاية لا يمكن أن يكون قبل تاريخ البداية.",
        }

    today = date.today()
    if start_date < today:
        return {
            "success": False,
            "message": "Cannot request leave for past dates.",
            "message_ar": "لا يمكن طلب إجازة لتواريخ سابقة.",
        }

    # Calculate business days (Saudi weekend: Fri/Sat)
    business_days = calculate_business_days(start_date, end_date)

    if business_days == 0:
        return {
            "success": False,
            "message": "The selected dates fall entirely on weekends or public holidays.",
            "message_ar": "التواريخ المحددة تقع بالكامل في عطلة نهاية الأسبوع أو إجازات رسمية.",
        }

    # Check for overlapping leave requests
    overlap = await check_overlap(db, employee_id, start_date, end_date)
    if overlap:
        return overlap

    # ── Policy-level pre-checks (min days, attachment warnings) ──
    attachment_warning = None
    # We need tenant_id to look up policy; fetch employee early if tenant_id provided
    _policy_tenant_id = tenant_id
    if _policy_tenant_id is None:
        _emp_peek = await db.execute(select(Employee.tenant_id).where(Employee.id == employee_id))
        _row = _emp_peek.scalar_one_or_none()
        if _row:
            _policy_tenant_id = _row

    if _policy_tenant_id:
        _policy_result = await db.execute(
            select(LeavePolicy).where(
                and_(
                    LeavePolicy.tenant_id == _policy_tenant_id,
                    LeavePolicy.leave_type == leave_type,
                    LeavePolicy.is_active == True,
                )
            )
        )
        _policy = _policy_result.scalar_one_or_none()

        # Finding 5: Enforce min_days_per_request
        if _policy and _policy.min_days_per_request and business_days < _policy.min_days_per_request:
            return {
                "success": False,
                "message": (
                    f"Minimum {_policy.min_days_per_request} business day(s) required per "
                    f"{leave_type.value} leave request. Requested: {business_days} day(s)."
                ),
                "message_ar": (
                    f"الحد الأدنى {_policy.min_days_per_request} يوم عمل لكل طلب إجازة "
                    f"{leave_type.value}. المطلوب: {business_days} يوم."
                ),
            }

        # Finding 7: Soft warning when attachment is required
        if _policy and _policy.requires_attachment:
            if _policy.attachment_after_days and business_days > _policy.attachment_after_days:
                attachment_warning = (
                    f"Note: {leave_type.value} leave over {_policy.attachment_after_days} days "
                    f"requires a supporting document. Please submit it to HR."
                )
            elif not _policy.attachment_after_days:
                attachment_warning = (
                    f"Note: {leave_type.value} leave requires a supporting document. "
                    f"Please submit it to HR."
                )

    # Fetch employee for labor law checks (with tenant isolation)
    emp_query = select(Employee).where(Employee.id == employee_id)
    if tenant_id is not None:
        emp_query = emp_query.where(Employee.tenant_id == tenant_id)
    emp_result = await db.execute(emp_query)
    employee = emp_result.scalar_one_or_none()
    if employee is None:
        return {
            "success": False,
            "message": "Employee not found.",
            "message_ar": "لم يتم العثور على الموظف.",
        }
    tenant_id = employee.tenant_id

    # ── Labor Law Validation ──
    law_result = None
    if employee and tenant_id:
        labor_law = SaudiLaborLawEngine()
        law_result = await labor_law.validate_leave_request(
            db=db,
            employee=employee,
            leave_type=leave_type,
            start_date=start_date,
            end_date=end_date,
            business_days=business_days,
            tenant_id=tenant_id,
        )
        if not law_result.is_valid:
            return {
                "success": False,
                "message": law_result.message,
                "message_ar": law_result.message_ar,
                "labor_law_article": law_result.article,
            }

    # Fetch leave balance for the leave year (with row-level lock to prevent race conditions)
    leave_year = start_date.year
    balance_query = select(LeaveBalance).where(
        and_(
            LeaveBalance.employee_id == employee_id,
            LeaveBalance.leave_type == leave_type,
            LeaveBalance.year == leave_year,
        )
    ).with_for_update()
    result = await db.execute(balance_query)
    balance = result.scalar_one_or_none()

    if balance is None:
        return {
            "success": False,
            "message": (
                f"No {leave_type.value} leave balance found for {leave_year}. "
                "Please contact HR to set up your leave entitlements."
            ),
            "message_ar": (
                f"لم يتم العثور على رصيد إجازة {_ar(leave_type)} لعام {leave_year}. "
                "يرجى التواصل مع الموارد البشرية لإعداد استحقاقات الإجازة."
            ),
        }

    # Fix 6: Account for days reserved by pending requests (locked to prevent race conditions)
    pending_reserved_result = await db.execute(
        select(func.coalesce(func.sum(LeaveRequest.business_days), 0)).where(
            and_(
                LeaveRequest.employee_id == employee_id,
                LeaveRequest.leave_type == leave_type,
                LeaveRequest.status == LeaveStatus.pending,
                LeaveRequest.start_date <= date(leave_year, 12, 31),
                LeaveRequest.end_date >= date(leave_year, 1, 1),
            )
        ).with_for_update()
    )
    pending_reserved_days = pending_reserved_result.scalar_one()

    remaining = balance.remaining_days
    effective_remaining = remaining - pending_reserved_days

    if business_days > effective_remaining:
        return {
            "success": False,
            "message": (
                f"Insufficient {leave_type.value} leave balance. "
                f"Requested: {business_days} days, Remaining: {remaining} days"
                f"{f', Reserved by pending requests: {pending_reserved_days} days' if pending_reserved_days > 0 else ''}."
            ),
            "message_ar": (
                f"رصيد إجازة {_ar(leave_type)} غير كافٍ. "
                f"المطلوب: {business_days} يوم، المتبقي: {remaining} يوم"
                f"{f'، محجوز بطلبات معلقة: {pending_reserved_days} يوم' if pending_reserved_days > 0 else ''}."
            ),
        }

    # ── Approval Routing ──
    approval_svc = ApprovalService()
    approval_result = None
    if employee and tenant_id:
        approval_result = await approval_svc.determine_approval_route(
            db=db,
            tenant_id=tenant_id,
            employee=employee,
            leave_type=leave_type,
            business_days=business_days,
        )

    is_auto_approved = (
        approval_result is not None
        and approval_result.decision == ApprovalDecision.auto_approved
    )
    request_status = LeaveStatus.approved if is_auto_approved else LeaveStatus.pending

    # Compute advance notice days
    advance_notice = (start_date - today).days

    # Create the leave request
    leave_request = LeaveRequest(
        employee_id=employee_id,
        leave_type=leave_type,
        start_date=start_date,
        end_date=end_date,
        business_days=business_days,
        reason=reason,
        status=request_status,
        auto_approved=is_auto_approved,
        advance_notice_days=advance_notice,
        labor_law_article=law_result.article if law_result is not None else None,
        created_by_agent=agent,
        created_via_channel=channel,
    )

    if is_auto_approved:
        leave_request.approved_at = datetime.now(timezone.utc)

    db.add(leave_request)

    # Deduct from balance only if auto-approved; pending requests deduct on approval
    if is_auto_approved:
        balance.used_days += business_days

    # Flush to get the leave_request.id before sending notification
    await db.flush()

    # Finding 3: Best-effort notification to the manager if not auto-approved.
    # Sent before commit so everything is in one transaction — no double commit.
    if not is_auto_approved and employee and employee.manager_id:
        try:
            from app.services.notification import NotificationService
            notif_svc = NotificationService(db, tenant_id)
            await notif_svc.send(
                employee_id=employee.manager_id,
                title="New Leave Request Pending Approval",
                title_ar="طلب إجازة جديد بانتظار الموافقة",
                body=f"{employee.full_name} requested {leave_type.value} leave from {start_date.isoformat()} to {end_date.isoformat()} ({business_days} days).",
                body_ar=f"{employee.full_name} طلب إجازة {_ar(leave_type)} من {start_date.isoformat()} إلى {end_date.isoformat()} ({business_days} يوم).",
                category="leave",
                resource_type="leave_request",
                resource_id=leave_request.id,
            )
        except Exception as e:
            logger.warning("Failed to send leave submission notification to manager: %s", e)

    await db.commit()
    await db.refresh(leave_request)

    logger.info(
        "Leave request created: id=%s, employee=%s, type=%s, days=%d, status=%s",
        leave_request.id,
        employee_id,
        leave_type.value,
        business_days,
        request_status.value,
    )

    # Build response based on approval routing
    if is_auto_approved:
        status_msg = "auto-approved"
        status_msg_ar = "تمت الموافقة تلقائياً"
        balance_note = f"Remaining balance: {remaining - business_days} days."
        balance_note_ar = f"الرصيد المتبقي: {remaining - business_days} يوم."
    else:
        status_msg = "pending approval"
        status_msg_ar = "بانتظار الموافقة"
        balance_note = f"Balance will be deducted upon approval. Current balance: {remaining} days."
        balance_note_ar = f"سيتم خصم الرصيد عند الموافقة. الرصيد الحالي: {remaining} يوم."

    approval_decision = approval_result.decision.value if approval_result else "pending_manager"

    # Collect labor law warnings and attachment warnings
    law_warnings = law_result.warnings if law_result is not None else []
    if attachment_warning:
        law_warnings.append(attachment_warning)

    return {
        "success": True,
        "message": (
            f"Leave request submitted successfully! "
            f"Type: {leave_type.value}, "
            f"From: {start_date.isoformat()}, "
            f"To: {end_date.isoformat()}, "
            f"Business days: {business_days}. "
            f"{balance_note} "
            f"Status: {status_msg}."
        ),
        "message_ar": (
            f"تم تقديم طلب الإجازة بنجاح! "
            f"النوع: {_ar(leave_type)}، "
            f"من: {start_date.isoformat()}، "
            f"إلى: {end_date.isoformat()}، "
            f"أيام العمل: {business_days}. "
            f"{balance_note_ar} "
            f"الحالة: {status_msg_ar}."
        ),
        "request_id": leave_request.id,
        "business_days": business_days,
        "approval_decision": approval_decision,
        "auto_approved": is_auto_approved,
        "warnings": law_warnings,
    }


async def check_overlap(
    db: AsyncSession,
    employee_id: uuid.UUID,
    start_date: date,
    end_date: date,
) -> dict | None:
    """Check if the employee has an existing leave request that overlaps the given dates.

    Only checks pending or approved requests. Returns a conflict dict if overlap
    is found, or None if no overlap.

    Args:
        db: Async database session.
        employee_id: The employee to check.
        start_date: Proposed start date.
        end_date: Proposed end date.

    Returns:
        A failure dict if overlap found, None otherwise.
    """
    overlap_query = select(LeaveRequest).where(
        and_(
            LeaveRequest.employee_id == employee_id,
            LeaveRequest.status.in_([LeaveStatus.pending, LeaveStatus.approved]),
            LeaveRequest.start_date <= end_date,
            LeaveRequest.end_date >= start_date,
        )
    )
    result = await db.execute(overlap_query)
    existing = result.scalars().first()

    if existing:
        return {
            "success": False,
            "message": (
                f"This request overlaps with an existing {existing.leave_type.value} leave "
                f"from {existing.start_date.isoformat()} to {existing.end_date.isoformat()} "
                f"(status: {existing.status.value})."
            ),
            "message_ar": (
                f"هذا الطلب يتعارض مع إجازة {_ar(existing.leave_type)} موجودة "
                f"من {existing.start_date.isoformat()} إلى {existing.end_date.isoformat()} "
                f"(الحالة: {existing.status.value})."
            ),
            "conflict_request_id": str(existing.id),
        }

    return None


async def cancel_leave_request(
    db: AsyncSession,
    employee_id: uuid.UUID,
    request_id: uuid.UUID,
    tenant_id: uuid.UUID | None = None,
) -> dict:
    """Cancel a pending leave request and restore the balance.

    Args:
        db: Async database session.
        employee_id: The employee who owns the request.
        request_id: The leave request to cancel.
        tenant_id: Tenant UUID for cross-tenant isolation.

    Returns:
        Status dict with success/failure info.
    """
    # Build query with tenant isolation when tenant_id is provided
    query = select(LeaveRequest).where(LeaveRequest.id == request_id).with_for_update()
    if tenant_id is not None:
        query = query.join(Employee, LeaveRequest.employee_id == Employee.id).where(
            Employee.tenant_id == tenant_id
        )

    result = await db.execute(query)
    request = result.scalar_one_or_none()

    if not request:
        return {
            "success": False,
            "message": "Leave request not found.",
            "message_ar": "لم يتم العثور على طلب الإجازة.",
        }

    if request.employee_id != employee_id:
        return {
            "success": False,
            "message": "This leave request does not belong to you.",
            "message_ar": "طلب الإجازة هذا لا يخصك.",
        }

    if request.status not in (LeaveStatus.pending, LeaveStatus.approved):
        return {
            "success": False,
            "message": f"Cannot cancel a request with status '{request.status.value}'. Only pending or approved requests can be cancelled.",
            "message_ar": f"لا يمكن إلغاء طلب بحالة '{request.status.value}'. فقط الطلبات المعلقة أو الموافق عليها يمكن إلغاؤها.",
        }

    # Only restore balance if it was actually deducted (approved or auto-approved requests)
    balance_was_deducted = (
        request.status == LeaveStatus.approved or request.auto_approved is True
    )
    days_restored = 0
    balance = None

    if balance_was_deducted:
        balance_result = await db.execute(
            select(LeaveBalance).where(
                and_(
                    LeaveBalance.employee_id == employee_id,
                    LeaveBalance.leave_type == request.leave_type,
                    LeaveBalance.year == request.start_date.year,
                )
            ).with_for_update()
        )
        balance = balance_result.scalar_one_or_none()

        if balance is None:
            return {
                "success": False,
                "message": (
                    f"Cannot cancel: no {request.leave_type.value} leave balance record found "
                    f"for {request.start_date.year}. Please contact HR."
                ),
                "message_ar": (
                    f"لا يمكن الإلغاء: لم يتم العثور على سجل رصيد إجازة {_ar(request.leave_type)} "
                    f"لعام {request.start_date.year}. يرجى التواصل مع الموارد البشرية."
                ),
            }

        balance.used_days = max(0, balance.used_days - request.business_days)
        days_restored = request.business_days

    request.status = LeaveStatus.cancelled

    await db.commit()

    if balance is not None:
        remaining_msg = f"Remaining balance: {balance.remaining_days} days."
        remaining_msg_ar = f"الرصيد المتبقي: {balance.remaining_days} يوم."
        remaining_balance = balance.remaining_days
    else:
        remaining_msg = ""
        remaining_msg_ar = ""
        remaining_balance = None

    restored_msg = (
        f"{days_restored} {request.leave_type.value} days restored. "
        if days_restored > 0
        else ""
    )
    restored_msg_ar = (
        f"تم استعادة {days_restored} يوم {_ar(request.leave_type)}. "
        if days_restored > 0
        else ""
    )

    return {
        "success": True,
        "message": (
            f"Leave request cancelled successfully. "
            f"{restored_msg}"
            f"{remaining_msg}"
        ),
        "message_ar": (
            f"تم إلغاء طلب الإجازة بنجاح. "
            f"{restored_msg_ar}"
            f"{remaining_msg_ar}"
        ),
        "request_id": str(request_id),
        "leave_type": request.leave_type.value,
        "business_days_restored": days_restored,
        "remaining_balance": remaining_balance,
    }
