"""Saudi Labor Law compliance engine — validates leave requests against KSA labor regulations."""
import logging
from dataclasses import dataclass, field
from datetime import date
from uuid import UUID

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee
from app.models.leave import LeaveType, LeaveRequest, LeaveStatus
from app.models.leave_policy import LeavePolicy

logger = logging.getLogger(__name__)


@dataclass
class LaborLawValidation:
    """Result of a labor law validation check."""
    is_valid: bool
    article: str | None = None
    message: str = ""
    message_ar: str = ""
    warnings: list[str] = field(default_factory=list)


class SaudiLaborLawEngine:
    """Validates leave requests against Saudi Labor Law articles."""

    async def validate_leave_request(
        self,
        db: AsyncSession,
        employee: Employee,
        leave_type: LeaveType,
        start_date: date,
        end_date: date,
        business_days: int,
        tenant_id: UUID,
    ) -> LaborLawValidation:
        """Orchestrate all labor law checks. Returns first failure or success with warnings."""
        all_warnings: list[str] = []

        # Fetch tenant leave policy
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

        # 1. Probation check
        probation_result = self.validate_probation_leave(employee, leave_type)
        if probation_result is not None:
            if not probation_result.is_valid:
                return probation_result
            all_warnings.extend(probation_result.warnings)

        # Also check policy-level probation block
        if policy and policy.blocked_during_probation and employee.is_on_probation:
            return LaborLawValidation(
                is_valid=False,
                article="109",
                message=f"{leave_type.value.title()} leave is not available during probation period.",
                message_ar=f"إجازة {leave_type.value} غير متاحة خلال فترة التجربة.",
            )

        # 2. Type-specific validations
        if leave_type == LeaveType.sick:
            # Calculate used sick days this year
            used_sick = await self._get_used_days(db, employee.id, LeaveType.sick, start_date.year)
            sick_result = self.validate_sick_leave_tiers(used_sick, business_days)
            if not sick_result.is_valid:
                return sick_result
            all_warnings.extend(sick_result.warnings)

        elif leave_type == LeaveType.maternity:
            mat_result = self.validate_maternity(employee, business_days)
            if not mat_result.is_valid:
                return mat_result
            all_warnings.extend(mat_result.warnings)

        elif leave_type == LeaveType.hajj:
            has_used_hajj = await self._has_used_hajj(db, employee.id)
            hajj_result = self.validate_hajj(employee, has_used_hajj, business_days)
            if not hajj_result.is_valid:
                return hajj_result
            all_warnings.extend(hajj_result.warnings)

        # 3. Advance notice check
        if policy and policy.advance_notice_days > 0:
            notice_result = self.validate_advance_notice(start_date, policy.advance_notice_days)
            if not notice_result.is_valid:
                return notice_result
            all_warnings.extend(notice_result.warnings)

        # 4. Blackout period check
        if policy and policy.blackout_periods:
            blackout_result = self.validate_blackout_period(start_date, end_date, policy.blackout_periods)
            if not blackout_result.is_valid:
                return blackout_result
            all_warnings.extend(blackout_result.warnings)

        # 5. Max days per request check
        if policy and policy.max_days_per_request and business_days > policy.max_days_per_request:
            return LaborLawValidation(
                is_valid=False,
                article=None,
                message=f"Maximum {policy.max_days_per_request} days allowed per {leave_type.value} leave request.",
                message_ar=f"الحد الأقصى {policy.max_days_per_request} يوم لكل طلب إجازة {leave_type.value}.",
            )

        return LaborLawValidation(
            is_valid=True,
            article=None,
            message="Leave request complies with Saudi Labor Law.",
            message_ar="طلب الإجازة متوافق مع نظام العمل السعودي.",
            warnings=all_warnings,
        )

    def get_annual_entitlement(self, tenure_years: float) -> int:
        """Article 109: 21 days if < 5 years, 30 days if >= 5 years."""
        if tenure_years >= 5:
            return 30
        return 21

    def validate_probation_leave(
        self, employee: Employee, leave_type: LeaveType
    ) -> LaborLawValidation | None:
        """Article 109: Block annual leave during probation. Sick/emergency always allowed."""
        if not employee.is_on_probation:
            return None

        # Sick and emergency are always allowed during probation
        always_allowed = {LeaveType.sick, LeaveType.emergency, LeaveType.bereavement}
        if leave_type in always_allowed:
            return LaborLawValidation(
                is_valid=True,
                article="109",
                message=f"{leave_type.value.title()} leave is permitted during probation.",
                message_ar=f"إجازة {leave_type.value} مسموح بها خلال فترة التجربة.",
            )

        if leave_type == LeaveType.annual:
            return LaborLawValidation(
                is_valid=False,
                article="109",
                message=(
                    "Annual leave is not available during your probation period. "
                    f"Your probation ends on {employee.probation_end_date.isoformat() if employee.probation_end_date else 'N/A'}."
                ),
                message_ar=(
                    "الإجازة السنوية غير متاحة خلال فترة التجربة. "
                    f"تنتهي فترة التجربة في {employee.probation_end_date.isoformat() if employee.probation_end_date else 'غير محدد'}."
                ),
            )

        # Other types during probation — allow with warning
        return LaborLawValidation(
            is_valid=True,
            article="109",
            message=f"{leave_type.value.title()} leave during probation is subject to approval.",
            message_ar=f"إجازة {leave_type.value} خلال فترة التجربة تخضع للموافقة.",
            warnings=[f"Employee is on probation (ends {employee.probation_end_date})"],
        )

    def validate_sick_leave_tiers(
        self, used_sick_days: int, requested_days: int
    ) -> LaborLawValidation:
        """Article 116: First 30 days full pay, next 60 at 75%, next 30 unpaid."""
        total_after = used_sick_days + requested_days
        warnings: list[str] = []

        if total_after > 120:
            return LaborLawValidation(
                is_valid=False,
                article="116",
                message=(
                    f"Sick leave limit exceeded. Maximum 120 days per year. "
                    f"Used: {used_sick_days}, Requested: {requested_days}."
                ),
                message_ar=(
                    f"تم تجاوز حد الإجازة المرضية. الحد الأقصى 120 يوم في السنة. "
                    f"المستخدم: {used_sick_days}، المطلوب: {requested_days}."
                ),
            )

        # Determine salary impact warnings
        if used_sick_days < 30 and total_after > 30:
            days_at_75 = min(total_after, 90) - 30
            warnings.append(
                f"Warning: {days_at_75} day(s) of this request will be at 75% salary (Article 116)."
            )
        elif total_after > 30 and used_sick_days >= 30 and total_after <= 90:
            warnings.append(
                "Warning: All requested days are at 75% salary (Article 116)."
            )

        if used_sick_days < 90 and total_after > 90:
            days_unpaid = min(total_after, 120) - 90
            warnings.append(
                f"Warning: {days_unpaid} day(s) of this request will be unpaid (Article 116)."
            )
        elif total_after > 90 and used_sick_days >= 90:
            warnings.append(
                "Warning: All requested days are unpaid sick leave (Article 116)."
            )

        return LaborLawValidation(
            is_valid=True,
            article="116",
            message="Sick leave request is within legal limits.",
            message_ar="طلب الإجازة المرضية ضمن الحدود القانونية.",
            warnings=warnings,
        )

    def validate_maternity(
        self, employee: Employee, business_days: int
    ) -> LaborLawValidation:
        """Article 151: Must be female. Max 70 days (10 weeks)."""
        # Fix 13: Handle gender=None explicitly
        if employee.gender is None:
            return LaborLawValidation(
                is_valid=False,
                article="151",
                message="Gender is not set on your profile. Please contact HR to update your information.",
                message_ar="لم يتم تحديد الجنس في ملفك الشخصي. يرجى التواصل مع الموارد البشرية لتحديث بياناتك.",
            )

        gender_val = employee.gender.value if hasattr(employee.gender, 'value') else employee.gender
        if gender_val != "female":
            return LaborLawValidation(
                is_valid=False,
                article="151",
                message="Maternity leave is only available to female employees.",
                message_ar="إجازة الأمومة متاحة فقط للموظفات.",
            )

        if business_days > 70:
            return LaborLawValidation(
                is_valid=False,
                article="151",
                message=f"Maternity leave cannot exceed 70 days (10 weeks). Requested: {business_days} days.",
                message_ar=f"إجازة الأمومة لا يمكن أن تتجاوز 70 يوم (10 أسابيع). المطلوب: {business_days} يوم.",
            )

        return LaborLawValidation(
            is_valid=True,
            article="151",
            message="Maternity leave request is valid.",
            message_ar="طلب إجازة الأمومة صالح.",
        )

    def validate_hajj(
        self, employee: Employee, has_used_hajj_before: bool, business_days: int
    ) -> LaborLawValidation:
        """Article 113: Once per employment, 10-15 days, requires 2 years tenure."""
        # Fix 10: Hajj requires at least 2 years of service
        if employee.tenure_years < 2:
            return LaborLawValidation(
                is_valid=False,
                article="113",
                message="Hajj leave requires at least 2 years of service.",
                message_ar="إجازة الحج تتطلب سنتين على الأقل من الخدمة.",
            )

        if has_used_hajj_before:
            return LaborLawValidation(
                is_valid=False,
                article="113",
                message="Hajj leave can only be used once during your employment.",
                message_ar="إجازة الحج يمكن استخدامها مرة واحدة فقط خلال فترة العمل.",
            )

        if business_days > 15:
            return LaborLawValidation(
                is_valid=False,
                article="113",
                message=f"Hajj leave cannot exceed 15 days. Requested: {business_days} days.",
                message_ar=f"إجازة الحج لا يمكن أن تتجاوز 15 يوم. المطلوب: {business_days} يوم.",
            )

        # Fix 18: Hajj leave must be at least 10 days
        if business_days < 10:
            return LaborLawValidation(
                is_valid=False,
                article="113",
                message=f"Hajj leave must be at least 10 days. Requested: {business_days} days.",
                message_ar=f"إجازة الحج يجب أن تكون 10 أيام على الأقل. المطلوب: {business_days} يوم.",
            )

        return LaborLawValidation(
            is_valid=True,
            article="113",
            message="Hajj leave request is valid.",
            message_ar="طلب إجازة الحج صالح.",
        )

    def validate_advance_notice(
        self, start_date: date, advance_notice_days: int
    ) -> LaborLawValidation:
        """Check if request is submitted with enough advance notice per policy."""
        today = date.today()
        days_until_start = (start_date - today).days

        if days_until_start < advance_notice_days:
            return LaborLawValidation(
                is_valid=False,
                article=None,
                message=(
                    f"This leave type requires {advance_notice_days} days advance notice. "
                    f"Your leave starts in {days_until_start} days."
                ),
                message_ar=(
                    f"هذا النوع من الإجازة يتطلب إشعار مسبق بـ {advance_notice_days} يوم. "
                    f"إجازتك تبدأ خلال {days_until_start} يوم."
                ),
            )

        return LaborLawValidation(
            is_valid=True,
            message="Advance notice requirement met.",
            message_ar="تم استيفاء شرط الإشعار المسبق.",
        )

    def validate_blackout_period(
        self, start_date: date, end_date: date, blackout_periods: list | dict | None
    ) -> LaborLawValidation:
        """Check if dates fall within tenant blackout periods."""
        if not blackout_periods:
            return LaborLawValidation(is_valid=True)

        periods = blackout_periods if isinstance(blackout_periods, list) else []

        for period in periods:
            try:
                bp_start = date.fromisoformat(period.get("start_date", "9999-12-31"))
                bp_end = date.fromisoformat(period.get("end_date", "9999-12-31"))
            except (ValueError, TypeError):
                logger.warning("Skipping malformed blackout period entry: %s", period)
                continue
            reason = period.get("reason", "blackout period")

            # Check overlap
            if start_date <= bp_end and end_date >= bp_start:
                return LaborLawValidation(
                    is_valid=False,
                    article=None,
                    message=(
                        f"Leave cannot be taken during blackout period: "
                        f"{bp_start.isoformat()} to {bp_end.isoformat()} ({reason})."
                    ),
                    message_ar=(
                        f"لا يمكن أخذ إجازة خلال فترة الحظر: "
                        f"{bp_start.isoformat()} إلى {bp_end.isoformat()} ({reason})."
                    ),
                )

        return LaborLawValidation(
            is_valid=True,
            message="No blackout period conflict.",
            message_ar="لا يوجد تعارض مع فترات الحظر.",
        )

    async def _get_used_days(
        self, db: AsyncSession, employee_id, leave_type: LeaveType, year: int
    ) -> int:
        """Get total used days of a leave type for an employee in a given year.

        Uses overlapping date range logic to catch requests that span year boundaries
        (e.g., Dec 20 to Jan 15 should count in both years).
        """
        year_start = date(year, 1, 1)
        year_end = date(year, 12, 31)
        result = await db.execute(
            select(LeaveRequest).where(
                and_(
                    LeaveRequest.employee_id == employee_id,
                    LeaveRequest.leave_type == leave_type,
                    LeaveRequest.status.in_([LeaveStatus.approved, LeaveStatus.pending]),
                    LeaveRequest.start_date <= year_end,
                    LeaveRequest.end_date >= year_start,
                )
            )
        )
        requests = result.scalars().all()
        return sum(r.business_days for r in requests)

    async def _has_used_hajj(self, db: AsyncSession, employee_id) -> bool:
        """Check if the employee has ever taken hajj leave (approved, pending, or cancelled).

        Cancelled hajj leave still counts as "used" to prevent the once-per-employment
        rule from being bypassed by cancelling and re-requesting.
        """
        result = await db.execute(
            select(LeaveRequest).where(
                and_(
                    LeaveRequest.employee_id == employee_id,
                    LeaveRequest.leave_type == LeaveType.hajj,
                    LeaveRequest.status.in_([
                        LeaveStatus.approved,
                        LeaveStatus.pending,
                        LeaveStatus.cancelled,
                    ]),
                )
            )
        )
        return result.scalar_one_or_none() is not None
