"""CUX-01: Context-Aware Smart Suggestions + CUX-03: Quick Actions Bar."""
import logging
from datetime import date, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.chat_dependencies import get_chat_employee, ChatEmployee
from app.models.employee import Employee, EmployeeStatus
from app.models.leave import LeaveRequest, LeaveStatus
from app.models.onboarding import (
    OnboardingAssignment, OnboardingAssignmentStatus,
    OnboardingStepAssignment, OnboardingStepStatus,
)
from app.saudi_holidays import _EID_DATES

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/suggestions", tags=["suggestions"])

RIYADH_TZ = ZoneInfo("Asia/Riyadh")


# ─── CUX-01: Suggestions API ────────────────────────────────────────────────

class Suggestion(BaseModel):
    text: str           # Display text in detected/requested language
    text_ar: str
    text_en: str
    agent_target: str   # Which agent handles this
    action_type: str    # "query" | "action" | "status_check"
    priority: int       # 1=high, 2=medium, 3=low
    icon: str           # Emoji for frontend rendering


class SuggestionsResponse(BaseModel):
    suggestions: list[Suggestion]
    generated_at: str


# ─── Rule functions ──────────────────────────────────────────────────────────

async def _rule_pending_leaves(
    employee_id: UUID, language: str, db: AsyncSession
) -> list[Suggestion]:
    """If employee has pending leave requests, suggest checking status."""
    count = await db.scalar(
        select(func.count(LeaveRequest.id)).where(
            LeaveRequest.employee_id == employee_id,
            LeaveRequest.status == LeaveStatus.pending,
        )
    )
    if count and count > 0:
        return [Suggestion(
            text=f"تحقق من {count} طلب(ات) إجازة معلقة" if language == "ar"
                else f"Check {count} pending leave request(s)",
            text_ar=f"تحقق من {count} طلب(ات) إجازة معلقة",
            text_en=f"Check {count} pending leave request(s)",
            agent_target="deema",
            action_type="status_check",
            priority=1,
            icon="📋",
        )]
    return []


async def _rule_incomplete_onboarding(
    employee_id: UUID, language: str, db: AsyncSession
) -> list[Suggestion]:
    """If employee has in-progress onboarding, suggest continuing."""
    count = await db.scalar(
        select(func.count(OnboardingStepAssignment.id))
        .join(
            OnboardingAssignment,
            OnboardingStepAssignment.assignment_id == OnboardingAssignment.id,
        )
        .where(
            OnboardingAssignment.employee_id == employee_id,
            OnboardingAssignment.status == OnboardingAssignmentStatus.in_progress,
            OnboardingStepAssignment.status.in_([
                OnboardingStepStatus.pending,
                OnboardingStepStatus.in_progress,
            ]),
        )
    )
    if count and count > 0:
        return [Suggestion(
            text=f"أكمل التأهيل ({count} خطوات متبقية)" if language == "ar"
                else f"Continue onboarding ({count} steps remaining)",
            text_ar=f"أكمل التأهيل ({count} خطوات متبقية)",
            text_en=f"Continue onboarding ({count} steps remaining)",
            agent_target="waleed",
            action_type="action",
            priority=1,
            icon="🚀",
        )]
    return []


async def _rule_upcoming_leave(
    employee_id: UUID, language: str, db: AsyncSession, today: date | None = None
) -> list[Suggestion]:
    """If employee has approved leave starting within 7 days."""
    if today is None:
        today = datetime.now(RIYADH_TZ).date()
    week_ahead = today + timedelta(days=7)
    count = await db.scalar(
        select(func.count(LeaveRequest.id)).where(
            LeaveRequest.employee_id == employee_id,
            LeaveRequest.status == LeaveStatus.approved,
            LeaveRequest.start_date >= today,
            LeaveRequest.start_date <= week_ahead,
        )
    )
    if count and count > 0:
        return [Suggestion(
            text="عرض تفاصيل الإجازة القادمة" if language == "ar"
                else "View upcoming leave details",
            text_ar="عرض تفاصيل الإجازة القادمة",
            text_en="View upcoming leave details",
            agent_target="deema",
            action_type="query",
            priority=1,
            icon="✈️",
        )]
    return []


def _rule_time_based(now_riyadh: datetime, today: date, language: str) -> list[Suggestion]:
    """Time-of-day and day-of-week based suggestions."""
    suggestions: list[Suggestion] = []
    day_of_week = today.weekday()  # 0=Mon, 4=Fri, 5=Sat, 6=Sun

    # Saudi weekend = Friday (4) + Saturday (5)
    is_weekend = day_of_week in (4, 5)

    # Sunday morning (first working day) -> attendance
    if day_of_week == 6 and now_riyadh.hour < 10:
        suggestions.append(Suggestion(
            text="تسجيل حضور" if language == "ar" else "Check attendance",
            text_ar="تسجيل حضور",
            text_en="Check attendance",
            agent_target="deema",
            action_type="action",
            priority=2,
            icon="📅",
        ))

    # Morning (not weekend) -> leave balance
    if now_riyadh.hour < 10 and not is_weekend:
        suggestions.append(Suggestion(
            text="رصيد إجازاتي" if language == "ar" else "Check my leave balance",
            text_ar="رصيد إجازاتي",
            text_en="Check my leave balance",
            agent_target="deema",
            action_type="query",
            priority=2,
            icon="📅",
        ))

    # End of month (day 25+) -> payslip
    if today.day >= 25:
        suggestions.append(Suggestion(
            text="كشف راتبي" if language == "ar" else "View my latest payslip",
            text_ar="كشف راتبي",
            text_en="View my latest payslip",
            agent_target="deema",
            action_type="query",
            priority=2,
            icon="💰",
        ))

    # Thursday -> leave request
    if day_of_week == 3:
        suggestions.append(Suggestion(
            text="طلب إجازة" if language == "ar" else "Request leave",
            text_ar="طلب إجازة",
            text_en="Request leave",
            agent_target="deema",
            action_type="action",
            priority=2,
            icon="🏖️",
        ))

    return suggestions


def _rule_seasonal(today: date, language: str) -> list[Suggestion]:
    """Ramadan, Hajj, Eid proximity suggestions."""
    suggestions: list[Suggestion] = []
    year_eids = _EID_DATES.get(today.year, {})

    eid_fitr_dates = year_eids.get("eid_fitr", [])
    eid_adha_dates = year_eids.get("eid_adha", [])

    # Check if in Ramadan (~30 days before Eid Al-Fitr)
    if eid_fitr_dates:
        ramadan_start_approx = eid_fitr_dates[0] - timedelta(days=30)
        if ramadan_start_approx <= today < eid_fitr_dates[0]:
            suggestions.append(Suggestion(
                text="ما هي ساعات العمل في رمضان؟" if language == "ar"
                    else "What are Ramadan working hours?",
                text_ar="ما هي ساعات العمل في رمضان؟",
                text_en="What are Ramadan working hours?",
                agent_target="deema",
                action_type="query",
                priority=2,
                icon="🌙",
            ))

    # Near Eid Al-Fitr (within 7 days)
    if eid_fitr_dates and today not in eid_fitr_dates:
        days_until = (eid_fitr_dates[0] - today).days
        if 0 < days_until <= 7:
            suggestions.append(Suggestion(
                text="إجازة عيد الفطر" if language == "ar" else "Eid Al-Fitr holiday info",
                text_ar="إجازة عيد الفطر",
                text_en="Eid Al-Fitr holiday info",
                agent_target="deema",
                action_type="query",
                priority=2,
                icon="🎉",
            ))

    # Near Eid Al-Adha (within 7 days)
    if eid_adha_dates and today not in eid_adha_dates:
        days_until = (eid_adha_dates[0] - today).days
        if 0 < days_until <= 7:
            suggestions.append(Suggestion(
                text="إجازة عيد الأضحى" if language == "ar" else "Eid Al-Adha holiday info",
                text_ar="إجازة عيد الأضحى",
                text_en="Eid Al-Adha holiday info",
                agent_target="deema",
                action_type="query",
                priority=2,
                icon="🎉",
            ))

    # Hajj season (within 45 days of Eid Al-Adha)
    if eid_adha_dates:
        days_until_adha = (eid_adha_dates[0] - today).days
        if 0 < days_until_adha <= 45:
            suggestions.append(Suggestion(
                text="معلومات إجازة الحج" if language == "ar" else "Hajj leave information",
                text_ar="معلومات إجازة الحج",
                text_en="Hajj leave information",
                agent_target="deema",
                action_type="query",
                priority=2,
                icon="🕋",
            ))

    return suggestions


async def _rule_manager(
    employee_id: UUID, tenant_id: UUID, language: str, db: AsyncSession
) -> list[Suggestion]:
    """Managers get team-related suggestions."""
    mgr_count = await db.scalar(
        select(func.count(Employee.id)).where(
            Employee.manager_id == employee_id,
            Employee.tenant_id == tenant_id,
            Employee.status.in_([EmployeeStatus.active, EmployeeStatus.onboarding]),
        )
    )
    if mgr_count and mgr_count > 0:
        return [
            Suggestion(
                text="الموافقات المعلقة" if language == "ar" else "Pending approvals",
                text_ar="الموافقات المعلقة",
                text_en="Pending approvals",
                agent_target="waleed",
                action_type="query",
                priority=3,
                icon="✅",
            ),
            Suggestion(
                text="نظرة على الفريق" if language == "ar" else "Team overview",
                text_ar="نظرة على الفريق",
                text_en="Team overview",
                agent_target="waleed",
                action_type="query",
                priority=3,
                icon="👥",
            ),
        ]
    return []


def _rule_defaults(language: str) -> list[Suggestion]:
    """Default suggestions — always available."""
    return [
        Suggestion(
            text="سياسة الإجازات" if language == "ar" else "Company leave policy",
            text_ar="سياسة الإجازات",
            text_en="Company leave policy",
            agent_target="deema",
            action_type="query",
            priority=3,
            icon="📋",
        ),
        Suggestion(
            text="رصيد إجازتي" if language == "ar" else "My leave balance",
            text_ar="رصيد إجازتي",
            text_en="My leave balance",
            agent_target="deema",
            action_type="query",
            priority=3,
            icon="📅",
        ),
    ]


@router.get("", response_model=SuggestionsResponse)
async def get_suggestions(
    db: AsyncSession = Depends(get_db),
    chat_emp: ChatEmployee = Depends(get_chat_employee),
    language: str = Query(default=""),
) -> SuggestionsResponse:
    """Get context-aware suggestions for an employee."""
    emp_id = chat_emp.employee_id
    tenant_id = chat_emp.tenant_id

    # Resolve employee and language
    result = await db.execute(
        select(Employee).where(
            Employee.id == emp_id,
            Employee.tenant_id == tenant_id,
            Employee.status.in_([EmployeeStatus.active, EmployeeStatus.onboarding]),
        )
    )
    employee = result.scalar_one_or_none()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    lang = language if language else employee.preferred_language

    now_riyadh = datetime.now(RIYADH_TZ)
    today = now_riyadh.date()

    # Run DB-dependent rules sequentially (AsyncSession is not safe for concurrent use)
    pending_leaves = await _rule_pending_leaves(emp_id, lang, db)
    onboarding = await _rule_incomplete_onboarding(emp_id, lang, db)
    upcoming = await _rule_upcoming_leave(emp_id, lang, db, today=today)
    manager_sugs = await _rule_manager(emp_id, tenant_id, lang, db)

    # Collect all suggestions in priority order
    all_suggestions: list[Suggestion] = []

    # Priority 1: Pending items
    all_suggestions.extend(pending_leaves)
    all_suggestions.extend(onboarding)
    all_suggestions.extend(upcoming)

    # Priority 2: Time-based and seasonal
    all_suggestions.extend(_rule_time_based(now_riyadh, today, lang))
    all_suggestions.extend(_rule_seasonal(today, lang))

    # Priority 3: Role-based (manager)
    all_suggestions.extend(manager_sugs)

    # Priority 3: Fallback defaults
    all_suggestions.extend(_rule_defaults(lang))

    # Deduplicate by text_en, keep first occurrence (highest priority)
    seen_texts: set[str] = set()
    deduped: list[Suggestion] = []
    for s in all_suggestions:
        if s.text_en not in seen_texts:
            seen_texts.add(s.text_en)
            deduped.append(s)

    # Return max 6 suggestions, sorted by priority
    final = sorted(deduped, key=lambda s: s.priority)[:6]

    return SuggestionsResponse(
        suggestions=final,
        generated_at=now_riyadh.isoformat(),
    )


# ─── CUX-03: Quick Actions Bar ──────────────────────────────────────────────

class QuickAction(BaseModel):
    label: str = ""     # Display label (set based on language)
    label_ar: str
    label_en: str
    message: str        # Pre-formed chat message
    agent: str          # Target agent hint
    icon: str           # Emoji
    category: str       # "self_service" | "team" | "analytics"


class QuickActionsResponse(BaseModel):
    actions: list[QuickAction]


# Role-based quick action configs (hardcoded)
_QUICK_ACTIONS_EMPLOYEE: list[dict] = [
    dict(label_en="Leave Balance", label_ar="رصيد الإجازات",
         message="What is my leave balance?", agent="deema", icon="📅", category="self_service"),
    dict(label_en="Request Leave", label_ar="طلب إجازة",
         message="I want to request a vacation", agent="deema", icon="🏖️", category="self_service"),
    dict(label_en="My Info", label_ar="معلوماتي",
         message="Show me my employee information", agent="deema", icon="👤", category="self_service"),
    dict(label_en="Company Policy", label_ar="سياسة الشركة",
         message="What is the company leave policy?", agent="deema", icon="📋", category="self_service"),
    dict(label_en="My Payslip", label_ar="كشف الراتب",
         message="Show my latest payslip", agent="deema", icon="💰", category="self_service"),
]

_QUICK_ACTIONS_MANAGER: list[dict] = _QUICK_ACTIONS_EMPLOYEE + [
    dict(label_en="Team Overview", label_ar="نظرة على الفريق",
         message="Show my team overview", agent="waleed", icon="👥", category="team"),
    dict(label_en="Pending Approvals", label_ar="الموافقات المعلقة",
         message="Show pending leave requests for my team", agent="waleed", icon="✅", category="team"),
    dict(label_en="HR Dashboard", label_ar="لوحة الموارد البشرية",
         message="Give me a workforce overview", agent="ahmad", icon="📊", category="analytics"),
]

_QUICK_ACTIONS_HR_ADMIN: list[dict] = [
    dict(label_en="Workforce Overview", label_ar="نظرة عامة على القوى العاملة",
         message="Give me a workforce overview", agent="ahmad", icon="📊", category="analytics"),
    dict(label_en="Compliance Status", label_ar="وضع الامتثال",
         message="Show compliance status", agent="ahmad", icon="✅", category="analytics"),
    dict(label_en="Open Positions", label_ar="الشواغر المفتوحة",
         message="Show open positions", agent="mohammad", icon="💼", category="analytics"),
    dict(label_en="Pending Requests", label_ar="الطلبات المعلقة",
         message="Show pending leave requests", agent="deema", icon="📋", category="self_service"),
    dict(label_en="Onboarding Status", label_ar="حالة التأهيل",
         message="Show onboarding analytics", agent="ahmad", icon="🚀", category="analytics"),
]

_QUICK_ACTIONS_EXECUTIVE: list[dict] = [
    dict(label_en="Executive Summary", label_ar="ملخص تنفيذي",
         message="Give me an executive HR summary", agent="ahmad", icon="📊", category="analytics"),
    dict(label_en="Saudization Status", label_ar="وضع السعودة",
         message="Show Saudization status", agent="ahmad", icon="🇸🇦", category="analytics"),
    dict(label_en="Budget Overview", label_ar="نظرة على الميزانية",
         message="Show department budget overview", agent="ahmad", icon="💰", category="analytics"),
    dict(label_en="Turnover Report", label_ar="تقرير الدوران الوظيفي",
         message="Show turnover metrics", agent="ahmad", icon="📈", category="analytics"),
    dict(label_en="Recruitment Pipeline", label_ar="خط التوظيف",
         message="Show recruitment analytics", agent="ahmad", icon="💼", category="analytics"),
]


def _determine_role(employee: Employee, is_manager: bool) -> str:
    """Determine employee role category from job title and manager status."""
    title_lower = (employee.job_title or "").lower()
    title_ar = (employee.job_title_ar or "")

    # Executive detection
    executive_keywords = ["ceo", "cto", "cfo", "coo", "chro", "vp", "vice president",
                          "director", "chief", "president", "رئيس", "مدير تنفيذي", "نائب"]
    if any(kw in title_lower for kw in executive_keywords) or any(kw in title_ar for kw in executive_keywords):
        return "executive"

    # HR admin detection
    hr_keywords = ["hr manager", "hr director", "hr admin", "human resources",
                   "موارد بشرية", "شؤون الموظفين"]
    if any(kw in title_lower for kw in hr_keywords) or any(kw in title_ar for kw in hr_keywords):
        return "hr_admin"

    # Manager detection
    if is_manager:
        return "manager"

    return "employee"


@router.get("/quick-actions", response_model=QuickActionsResponse)
async def get_quick_actions(
    db: AsyncSession = Depends(get_db),
    chat_emp: ChatEmployee = Depends(get_chat_employee),
) -> QuickActionsResponse:
    """Get role-based quick actions for the employee."""
    emp_id = chat_emp.employee_id
    tenant_id = chat_emp.tenant_id

    # Fetch employee
    result = await db.execute(
        select(Employee).where(
            Employee.id == emp_id,
            Employee.tenant_id == tenant_id,
        )
    )
    employee = result.scalar_one_or_none()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    # Check if this employee manages anyone
    mgr_result = await db.execute(
        select(func.count(Employee.id)).where(
            Employee.manager_id == employee.id,
            Employee.tenant_id == tenant_id,
            Employee.status.in_([EmployeeStatus.active, EmployeeStatus.onboarding]),
        )
    )
    is_manager = (mgr_result.scalar() or 0) > 0

    # Determine role and select actions
    role = _determine_role(employee, is_manager)
    role_actions = {
        "employee": _QUICK_ACTIONS_EMPLOYEE,
        "manager": _QUICK_ACTIONS_MANAGER,
        "hr_admin": _QUICK_ACTIONS_HR_ADMIN,
        "executive": _QUICK_ACTIONS_EXECUTIVE,
    }
    action_dicts = role_actions.get(role, _QUICK_ACTIONS_EMPLOYEE)

    # Check for in-progress onboarding — prepend onboarding action
    onboarding_result = await db.scalar(
        select(func.count(OnboardingAssignment.id)).where(
            OnboardingAssignment.employee_id == emp_id,
            OnboardingAssignment.tenant_id == tenant_id,
            OnboardingAssignment.status == OnboardingAssignmentStatus.in_progress,
        )
    )
    actions_list = list(action_dicts)
    if onboarding_result and onboarding_result > 0:
        actions_list.insert(0, dict(
            label_en="Onboarding Progress", label_ar="تقدم التأهيل",
            message="Show my onboarding progress", agent="waleed",
            icon="🚀", category="self_service",
        ))

    # Build response with language-appropriate labels
    lang = employee.preferred_language
    actions = []
    for a in actions_list:
        actions.append(QuickAction(
            label=a["label_ar"] if lang == "ar" else a["label_en"],
            label_ar=a["label_ar"],
            label_en=a["label_en"],
            message=a["message"],
            agent=a["agent"],
            icon=a["icon"],
            category=a["category"],
        ))

    return QuickActionsResponse(actions=actions)
