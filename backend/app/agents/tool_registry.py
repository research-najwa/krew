"""Static registry of agent tools.

Maps every concrete agent tool function to a stable tool_id, a domain bucket,
and human-friendly bilingual display names (present continuous, plain language)
suitable for showing in an activity feed or chat status pill.

tool_id format: "<agent>.<domain>.<function>"
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ToolDescriptor:
    tool_id: str
    agent: str
    domain: str
    function: str
    display_name_en: str
    display_name_ar: str


def _td(agent: str, domain: str, function: str, en: str, ar: str) -> tuple[str, ToolDescriptor]:
    tool_id = f"{agent}.{domain}.{function}"
    return tool_id, ToolDescriptor(
        tool_id=tool_id,
        agent=agent,
        domain=domain,
        function=function,
        display_name_en=en,
        display_name_ar=ar,
    )


# ── Ahmad (CHRO) — 17 tools ───────────────────────────────────────
_AHMAD: list[tuple[str, ToolDescriptor]] = [
    _td("ahmad", "analytics", "get_headcount_summary",
        "Pulling headcount summary", "جاري سحب ملخص أعداد الموظفين"),
    _td("ahmad", "compliance", "get_saudization_status",
        "Checking Saudization status", "جاري فحص حالة السعودة"),
    _td("ahmad", "analytics", "get_turnover_metrics",
        "Calculating turnover metrics", "جاري حساب معدلات الدوران"),
    _td("ahmad", "analytics", "get_department_budget",
        "Looking up department budget", "جاري الاطلاع على ميزانية القسم"),
    _td("ahmad", "analytics", "get_salary_distribution",
        "Analyzing salary distribution", "جاري تحليل توزيع الرواتب"),
    _td("ahmad", "analytics", "get_workforce_overview",
        "Building workforce overview", "جاري إعداد نظرة عامة على القوى العاملة"),
    _td("ahmad", "compliance", "get_compliance_status",
        "Reviewing compliance status", "جاري مراجعة حالة الامتثال"),
    _td("ahmad", "recruitment", "get_recruitment_analytics",
        "Pulling recruitment analytics", "جاري سحب تحليلات التوظيف"),
    _td("ahmad", "operations", "get_leave_analytics",
        "Pulling leave analytics", "جاري سحب تحليلات الإجازات"),
    _td("ahmad", "operations", "get_attendance_analytics",
        "Pulling attendance analytics", "جاري سحب تحليلات الحضور"),
    _td("ahmad", "operations", "get_onboarding_analytics",
        "Pulling onboarding analytics", "جاري سحب تحليلات التأهيل"),
    _td("ahmad", "operations", "get_payroll_summary",
        "Summarizing payroll", "جاري تلخيص كشوف الرواتب"),
    _td("ahmad", "intelligence", "predict_attrition_risk",
        "Predicting attrition risk", "جاري التنبؤ بمخاطر الاستنزاف"),
    _td("ahmad", "intelligence", "forecast_budget",
        "Forecasting budget", "جاري التنبؤ بالميزانية"),
    _td("ahmad", "compliance", "audit_gosi_compliance",
        "Auditing GOSI compliance", "جاري تدقيق امتثال التأمينات"),
    _td("ahmad", "compliance", "get_policy_acknowledgments",
        "Checking policy acknowledgments", "جاري فحص إقرارات السياسات"),
    _td("ahmad", "intelligence", "generate_custom_report",
        "Generating custom report", "جاري إنشاء تقرير مخصص"),
]


# ── Deema (Employee Relations) — 19 tools ─────────────────────────
_DEEMA: list[tuple[str, ToolDescriptor]] = [
    _td("deema", "leave", "get_leave_balance",
        "Calculating your leave balance", "جاري حساب رصيد إجازتك"),
    _td("deema", "leave", "preview_leave_request",
        "Preparing your leave request", "جاري تجهيز طلب إجازتك"),
    _td("deema", "leave", "submit_leave_request",
        "Submitting your leave request", "جاري تقديم طلب إجازتك"),
    _td("deema", "profile", "get_employee_info",
        "Looking up employee info", "جاري الاطلاع على بيانات الموظف"),
    _td("deema", "leave", "get_leave_requests",
        "Fetching leave requests", "جاري جلب طلبات الإجازة"),
    _td("deema", "leave", "cancel_leave_request",
        "Cancelling your leave request", "جاري إلغاء طلب إجازتك"),
    _td("deema", "policy", "search_policy",
        "Searching company policies", "جاري البحث في سياسات الشركة"),
    _td("deema", "profile", "update_employee_info",
        "Updating your information", "جاري تحديث بياناتك"),
    _td("deema", "team", "get_team_calendar",
        "Checking your team calendar", "جاري فحص تقويم فريقك"),
    _td("deema", "escalation", "get_escalation_status",
        "Checking ticket status", "جاري فحص حالة التذكرة"),
    _td("deema", "escalation", "escalate_to_human",
        "Escalating to a human teammate", "جاري التصعيد إلى زميل بشري"),
    _td("deema", "escalation", "list_my_escalations",
        "Listing your tickets", "جاري عرض تذاكرك"),
    _td("deema", "leave", "list_my_leave_requests",
        "Listing your leave requests", "جاري عرض طلبات إجازتك"),
    _td("deema", "profile", "view_my_profile",
        "Opening your profile", "جاري فتح ملفك الشخصي"),
    _td("deema", "profile", "view_salary_info",
        "Looking up your salary info", "جاري الاطلاع على بيانات راتبك"),
    _td("deema", "leave", "view_vacation_balance",
        "Showing your vacation balance", "جاري عرض رصيد إجازتك"),
    _td("deema", "profile", "view_contract_info",
        "Looking up your contract", "جاري الاطلاع على بيانات عقدك"),
    _td("deema", "payslip", "view_payslip",
        "Pulling your payslip", "جاري سحب كشف راتبك"),
    _td("deema", "documents", "list_my_documents",
        "Listing your documents", "جاري عرض مستنداتك"),
    _td("deema", "documents", "check_expiring_documents",
        "Checking expiring documents", "جاري فحص المستندات منتهية الصلاحية"),
    _td("deema", "onboarding", "get_onboarding_checklist",
        "Loading onboarding checklist", "جاري تحميل قائمة التأهيل"),
    _td("deema", "onboarding", "get_onboarding_dashboard",
        "Loading onboarding dashboard", "جاري تحميل لوحة التأهيل"),
    _td("deema", "onboarding", "get_overdue_onboarding_steps",
        "Checking overdue steps", "جاري فحص الخطوات المتأخرة"),
    _td("deema", "onboarding", "complete_onboarding_step",
        "Completing onboarding step", "جاري إكمال خطوة التأهيل"),
    _td("deema", "onboarding", "assign_onboarding",
        "Assigning onboarding plan", "جاري تعيين خطة التأهيل"),
    _td("deema", "onboarding", "send_checkin",
        "Sending check-in", "جاري إرسال متابعة"),
    _td("deema", "onboarding", "get_new_hire_info",
        "Looking up new hire info", "جاري الاطلاع على بيانات الموظف الجديد"),
]


# ── Mohammad (Recruitment) — 20 tools ─────────────────────────────
_MOHAMMAD: list[tuple[str, ToolDescriptor]] = [
    _td("mohammad", "recruitment", "get_job_postings",
        "Loading job postings", "جاري تحميل الوظائف المعلنة"),
    _td("mohammad", "recruitment", "get_job_posting",
        "Opening job posting details", "جاري فتح تفاصيل الوظيفة"),
    _td("mohammad", "recruitment", "create_job_posting",
        "Creating job posting", "جاري إنشاء إعلان وظيفي"),
    _td("mohammad", "recruitment", "generate_job_description",
        "Generating job description", "جاري إنشاء وصف وظيفي"),
    _td("mohammad", "recruitment", "extract_job_keywords",
        "Extracting job keywords", "جاري استخراج كلمات مفتاحية"),
    _td("mohammad", "recruitment", "search_candidates_web",
        "Searching for candidates", "جاري البحث عن مرشحين"),
    _td("mohammad", "recruitment", "view_candidates",
        "Loading candidate list", "جاري تحميل قائمة المرشحين"),
    _td("mohammad", "recruitment", "screen_candidate",
        "Screening candidate", "جاري فحص المرشح"),
    _td("mohammad", "recruitment", "update_candidate_stage",
        "Updating candidate stage", "جاري تحديث مرحلة المرشح"),
    _td("mohammad", "recruitment", "schedule_interview",
        "Scheduling interview", "جاري جدولة المقابلة"),
    _td("mohammad", "recruitment", "get_pipeline_summary",
        "Loading recruitment pipeline", "جاري تحميل خط التوظيف"),
    _td("mohammad", "recruitment", "add_candidate",
        "Adding new candidate", "جاري إضافة مرشح جديد"),
    _td("mohammad", "recruitment", "search_employee",
        "Searching employees", "جاري البحث عن موظفين"),
    _td("mohammad", "recruitment", "start_screening_interview",
        "Starting screening interview", "جاري بدء مقابلة الفرز"),
    _td("mohammad", "recruitment", "submit_interview_answer",
        "Recording interview answer", "جاري تسجيل إجابة المقابلة"),
    _td("mohammad", "recruitment", "end_interview",
        "Ending interview", "جاري إنهاء المقابلة"),
    _td("mohammad", "recruitment", "generate_assessment",
        "Generating candidate assessment", "جاري إنشاء تقييم المرشح"),
    _td("mohammad", "recruitment", "score_interview",
        "Scoring interview", "جاري تقييم المقابلة"),
    _td("mohammad", "recruitment", "compare_candidates",
        "Comparing candidates", "جاري مقارنة المرشحين"),
    _td("mohammad", "recruitment", "generate_offer_recommendation",
        "Generating offer recommendation", "جاري إنشاء توصية العرض"),
]


# ── Waleed (HRBP) — 17 tools ─────────────────────────────────────
_WALEED: list[tuple[str, ToolDescriptor]] = [
    _td("waleed", "profile", "search_employee",
        "Searching employees", "جاري البحث عن موظفين"),
    _td("waleed", "team", "view_team",
        "Loading team members", "جاري تحميل أعضاء الفريق"),
    _td("waleed", "team", "get_team_headcount",
        "Checking team headcount", "جاري فحص عدد أعضاء الفريق"),
    _td("waleed", "team", "view_pending_approvals",
        "Checking pending approvals", "جاري فحص الموافقات المعلقة"),
    _td("waleed", "team", "approve_leave",
        "Approving leave request", "جاري الموافقة على طلب الإجازة"),
    _td("waleed", "team", "reject_leave",
        "Rejecting leave request", "جاري رفض طلب الإجازة"),
    _td("waleed", "team", "get_team_leave_calendar",
        "Loading team leave calendar", "جاري تحميل تقويم إجازات الفريق"),
    _td("waleed", "insights", "get_team_dashboard",
        "Loading team dashboard", "جاري تحميل لوحة الفريق"),
    _td("waleed", "insights", "get_probation_tracker",
        "Checking probation status", "جاري فحص حالة فترة التجربة"),
    _td("waleed", "insights", "get_team_attendance",
        "Loading attendance data", "جاري تحميل بيانات الحضور"),
    _td("waleed", "insights", "get_compensation_overview",
        "Analyzing compensation", "جاري تحليل التعويضات"),
    _td("waleed", "insights", "get_flight_risk",
        "Analyzing flight risk", "جاري تحليل مخاطر الاستقالة"),
    _td("waleed", "insights", "prepare_one_on_one",
        "Preparing 1:1 meeting", "جاري تحضير اجتماع فردي"),
    _td("waleed", "compliance", "get_team_compliance",
        "Checking team compliance", "جاري فحص امتثال الفريق"),
    _td("waleed", "actions", "request_headcount",
        "Submitting headcount request", "جاري تقديم طلب توظيف"),
    _td("waleed", "actions", "get_manager_action_items",
        "Loading action items", "جاري تحميل المهام المطلوبة"),
    _td("waleed", "actions", "generate_pip",
        "Generating PIP", "جاري إنشاء خطة تحسين الأداء"),
]


# ── Yara (AI Workforce Architect) — 16 tools ─────────────────────
_YARA: list[tuple[str, ToolDescriptor]] = [
    _td("yara", "workforce", "get_department_overview",
        "Loading department overview", "جاري تحميل نظرة عامة على القسم"),
    _td("yara", "workforce", "analyze_department",
        "Analyzing department", "جاري تحليل القسم"),
    _td("yara", "workforce", "recommend_workforce_mix",
        "Recommending workforce mix", "جاري اقتراح مزيج القوى العاملة"),
    _td("yara", "workforce", "simulate_scenario",
        "Simulating workforce scenario", "جاري محاكاة سيناريو القوى العاملة"),
    _td("yara", "workforce", "estimate_agent_roi",
        "Estimating agent ROI", "جاري تقدير عائد الاستثمار"),
    _td("yara", "factory", "design_agent",
        "Designing AI agent", "جاري تصميم وكيل ذكاء اصطناعي"),
    _td("yara", "factory", "create_agent",
        "Creating AI agent", "جاري إنشاء وكيل ذكاء اصطناعي"),
    _td("yara", "factory", "activate_agent",
        "Activating agent", "جاري تفعيل الوكيل"),
    _td("yara", "factory", "configure_agent_tools",
        "Configuring agent tools", "جاري إعداد أدوات الوكيل"),
    _td("yara", "factory", "set_escalation_rules",
        "Setting escalation rules", "جاري تعيين قواعد التصعيد"),
    _td("yara", "governance", "list_deployed_agents",
        "Listing deployed agents", "جاري عرض الوكلاء المنشورين"),
    _td("yara", "governance", "get_agent_performance",
        "Checking agent performance", "جاري فحص أداء الوكيل"),
    _td("yara", "governance", "detect_drift",
        "Detecting agent drift", "جاري كشف انحراف الوكيل"),
    _td("yara", "governance", "update_agent_prompt",
        "Updating agent prompt", "جاري تحديث موجه الوكيل"),
    _td("yara", "governance", "deactivate_agent",
        "Deactivating agent", "جاري إيقاف الوكيل"),
    _td("yara", "governance", "generate_governance_report",
        "Generating governance report", "جاري إنشاء تقرير الحوكمة"),
]


TOOL_REGISTRY: dict[str, ToolDescriptor] = dict(_AHMAD + _DEEMA + _MOHAMMAD + _WALEED + _YARA)


def get_tool_descriptor(tool_id: str) -> ToolDescriptor | None:
    """Look up a descriptor by full tool_id, e.g. 'ahmad.compliance.saudization_status'."""
    return TOOL_REGISTRY.get(tool_id)


def get_display_name(tool_id: str, locale: str) -> str:
    """Return the bilingual display name. Falls back to tool_id if unknown."""
    desc = TOOL_REGISTRY.get(tool_id)
    if desc is None:
        return tool_id
    if (locale or "en").lower().startswith("ar"):
        return desc.display_name_ar
    return desc.display_name_en


def find_by_function(agent: str, function: str) -> ToolDescriptor | None:
    """Look up a descriptor by (agent, function) pair — convenient when only the
    raw tool name from the LLM tool-use loop is known."""
    for desc in TOOL_REGISTRY.values():
        if desc.agent == agent and desc.function == function:
            return desc
    return None
