"""Ahmad — CHRO Intelligence Agent.

Provides executive-level HR analytics, workforce metrics, compliance status,
and strategic insights. Read-only: Ahmad never modifies data.

Phase A1: Core HR Metrics + Compliance
Phase A2: Cross-Domain Analytics
Phase A3: Predictive & Advanced Analytics
"""
import json
import logging
from datetime import date, datetime, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

_RIYADH_TZ = ZoneInfo("Asia/Riyadh")

from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import (
    BaseAgent,
    ROLE_HR_MANAGER, ROLE_HR_ADMIN, ROLE_C_SUITE, ROLE_DEPT_HEAD,
    ROLES_HR_MANAGER_UP,
)
from app.models.employee import Employee, Department, EmployeeStatus, Gender
from app.models.nitaqat import NitaqatConfig
from app.models.compliance import ComplianceRecord
from app.models.deployed_agent import DeployedAgent, AgentStatus
from app.models.candidate import JobPosting, Candidate, PostingStatus, CandidateStage
from app.models.leave import LeaveRequest, LeaveBalance, LeaveType, LeaveStatus
from app.models.attendance import AttendanceRecord, AttendanceStatus
from app.models.onboarding import (
    OnboardingAssignment, OnboardingAssignmentStatus,
    OnboardingStepAssignment, OnboardingStepStatus,
    OnboardingTemplateStep,
)
from app.models.payslip import Payslip
from app.models.hr_policy import HRPolicy, PolicyAcknowledgment, PolicyStatus, PolicyCategory

logger = logging.getLogger(__name__)


_AHMAD_BROAD = {ROLE_HR_MANAGER, ROLE_HR_ADMIN, ROLE_DEPT_HEAD, ROLE_C_SUITE}


class AhmadAgent(BaseAgent):
    name = "Ahmad"
    name_ar = "أحمد"
    role = "CHRO"
    division = "Executive Leadership"
    MIN_GROUP_SIZE = 5  # k-anonymity threshold for all analytics tools

    # RBAC: sensitive tools require HR/management roles
    _SENSITIVE_TOOLS: set[str] = {
        "get_salary_distribution",
        "get_department_budget",
        "predict_attrition_risk",
        "get_payroll_summary",
        "forecast_budget",
        "get_turnover_metrics",
        "generate_custom_report",
    }
    _SENSITIVE_ALLOWED_ROLES: set[str] = {
        "hr_manager", "hr_specialist", "executive", "admin", "manager",
    }

    # -- Persona-based tool visibility --
    TOOL_VISIBILITY: dict[str, set[str]] = {
        # Broad analytics — dept_head + HR + c_suite
        "get_headcount_summary":     _AHMAD_BROAD,
        "get_saudization_status":    _AHMAD_BROAD,
        "get_workforce_overview":    _AHMAD_BROAD,
        "get_compliance_status":     _AHMAD_BROAD,
        "get_turnover_metrics":      _AHMAD_BROAD,
        "get_recruitment_analytics": _AHMAD_BROAD,
        "get_leave_analytics":       _AHMAD_BROAD,
        "get_attendance_analytics":  _AHMAD_BROAD,
        "get_onboarding_analytics":  _AHMAD_BROAD,
        # Sensitive financial — HR manager+ only (no dept_head)
        "get_salary_distribution":   ROLES_HR_MANAGER_UP,
        "get_department_budget":     ROLES_HR_MANAGER_UP,
        "get_payroll_summary":       ROLES_HR_MANAGER_UP,
        "predict_attrition_risk":    ROLES_HR_MANAGER_UP,
        "forecast_budget":           ROLES_HR_MANAGER_UP,
        "audit_gosi_compliance":     ROLES_HR_MANAGER_UP,
        "get_policy_acknowledgments": ROLES_HR_MANAGER_UP,
        "generate_custom_report":    ROLES_HR_MANAGER_UP,
    }

    # GOSI contribution rates (Saudi Labor Law, current as of 2026)
    GOSI_EMPLOYER_SAUDI_PCT = 0.12       # 9.75% annuity + 1% SANED + 1.25% occupational
    GOSI_EMPLOYEE_SAUDI_PCT = 0.10       # 9.75% annuity + 0.25% SANED
    GOSI_EMPLOYER_NON_SAUDI_PCT = 0.02   # 2% occupational hazards only
    GOSI_EMPLOYEE_NON_SAUDI_PCT = 0.0    # Non-Saudis pay nothing
    GOSI_SALARY_CEILING_SAR = 45_000     # Monthly ceiling for GOSI contributions
    personality = (
        "Strategic, data-driven, and executive-oriented. You lead with headline numbers "
        "and tie every metric to business impact. You present insights clearly, using "
        "structured summaries with key takeaways. You understand Saudi labor law, Nitaqat, "
        "and GOSI deeply. You always respond in English for consistency in executive reporting. "
        "You understand Arabic queries fluently."
    )

    def _get_scope_rules(self) -> str:
        return (
            "LANGUAGE RULE: You MUST always respond in English, regardless of the language the user writes in. "
            "If the user writes in Arabic, understand their request but respond entirely in English. "
            "Do not mix Arabic and English in your responses. "
            "Exception: When quoting Arabic terms of art (e.g., نطاقات for Nitaqat, التأمينات الاجتماعية for GOSI), "
            "include the Arabic term in parentheses after the English term for clarity.\n\n"
            "You are Ahmad, the CHRO Intelligence Agent. Your responsibilities:\n"
            "1. Provide HR analytics and workforce metrics at org and department level\n"
            "2. Monitor Saudization (Nitaqat) compliance and band status\n"
            "3. Track turnover rates and workforce trends\n"
            "4. Analyze salary distributions and budget utilization\n"
            "5. Deliver executive dashboards and workforce overviews\n"
            "6. Report on compliance status across categories (GOSI, Labor Law, WPS)\n"
            "7. Always present data with context — compare to targets, flag risks, highlight wins\n"
            "8. When presenting numbers, lead with the headline, then drill into details\n"
            "9. Recruitment pipeline analytics (funnel, time-to-fill, AI match scores)\n"
            "10. Leave analytics (usage by type, department comparison, seasonal patterns)\n"
            "11. Attendance analytics (rates, overtime, day-of-week patterns)\n"
            "12. Onboarding health (completion rates, bottleneck steps, overdue tasks)\n"
            "13. Payroll summaries (cost trends, GOSI breakdown, department comparison)\n"
            "\nYou do NOT handle:\n"
            "- Leave requests, balances, or policy questions → redirect to Deema (ديمة)\n"
            "- Recruitment, candidates, interviews, or job postings → redirect to Mohammad (محمد)\n"
            "- Onboarding, team management, or leave approvals → redirect to Waleed (وليد)\n"
            "- AI agent factory, workforce planning, or agent deployment → redirect to Yara (يارا)\n"
            "\nSaudi-specific context:\n"
            "- Nitaqat (نطاقات): Saudization compliance program with bands (Platinum, Green High, Green Low, Yellow, Red)\n"
            "- GOSI (التأمينات الاجتماعية): Social insurance — 12% employer + 10% employee for Saudis\n"
            "- WPS (نظام حماية الأجور): Wage Protection System — mandatory salary transfer tracking\n"
            "- Labor Law (نظام العمل): Saudi labor regulations covering contracts, termination, working hours\n"
            "\nArabic glossary:\n"
            "- تحليلات (analytics), مقاييس (metrics), ميزانية (budget), دوران وظيفي (turnover)\n"
            "- عدد الموظفين (headcount), سعودة (Saudization), امتثال (compliance)\n"
            "- نسبة التوطين (Saudization ratio), توزيع الرواتب (salary distribution)\n"
            "- لوحة المعلومات (dashboard), نظرة عامة (overview)\n"
            "\nNote: Use these Arabic terms to understand Arabic queries. Always respond in English.\n"
        "\nNorah/Sarah alias handling:\n"
        "Users who ask for 'Norah' (نورة) or 'Sarah' (سارة) are redirected to you. "
        "If the user seems to be looking for payroll/EOS calculations (Norah's former domain) "
        "or compliance checks (Sarah's former domain), acknowledge that you now handle these areas "
        "and assist them directly.\n"
        )

    # ──────────────────────────────────────────────────────────────
    # CUX-02: Follow-up suggestions per tool
    # ──────────────────────────────────────────────────────────────

    def _generate_suggestions(
        self, tool_name: str, tool_result: dict, language: str = "ar"
    ) -> list[str]:
        ar = language == "ar"
        suggestions_map: dict[str, list[str]] = {
            "get_headcount_summary": [
                "عرض وضع السعودة" if ar else "Show Saudization status",
                "ميزانية القسم" if ar else "Department budget",
                "عرض توزيع الرواتب" if ar else "Salary distribution",
            ],
            "get_saudization_status": [
                "ملخص القوى العاملة" if ar else "Workforce overview",
                "عرض معدل الدوران" if ar else "Show turnover metrics",
                "وضع الامتثال" if ar else "Compliance status",
            ],
            "get_turnover_metrics": [
                "ملخص عدد الموظفين" if ar else "Headcount summary",
                "تحليل الحضور" if ar else "Attendance analytics",
                "ملخص الرواتب" if ar else "Payroll summary",
            ],
            "get_salary_distribution": [
                "ميزانية القسم" if ar else "Department budget",
                "ملخص الرواتب" if ar else "Payroll summary",
                "وضع السعودة" if ar else "Saudization status",
            ],
            "get_department_budget": [
                "ملخص عدد الموظفين" if ar else "Headcount summary",
                "توزيع الرواتب" if ar else "Salary distribution",
                "ملخص الرواتب" if ar else "Payroll summary",
            ],
            "get_workforce_overview": [
                "عرض وضع السعودة" if ar else "Show Saudization status",
                "عرض معدل الدوران" if ar else "Turnover metrics",
                "ميزانية القسم" if ar else "Department budget",
            ],
            "get_compliance_status": [
                "ملخص عدد الموظفين" if ar else "Headcount summary",
                "وضع السعودة" if ar else "Saudization status",
                "عرض معدل الدوران" if ar else "Turnover metrics",
            ],
            # A2 cross-domain analytics tools
            "get_recruitment_analytics": [
                "ملخص عدد الموظفين" if ar else "Headcount summary",
                "تحليل التأهيل" if ar else "Onboarding analytics",
                "معدل الدوران" if ar else "Turnover metrics",
            ],
            "get_leave_analytics": [
                "تحليل الحضور" if ar else "Attendance analytics",
                "ملخص القوى العاملة" if ar else "Workforce overview",
                "ملخص عدد الموظفين" if ar else "Headcount summary",
            ],
            "get_attendance_analytics": [
                "تحليل الإجازات" if ar else "Leave analytics",
                "ملخص عدد الموظفين" if ar else "Headcount summary",
                "تحليل التأهيل" if ar else "Onboarding analytics",
            ],
            "get_onboarding_analytics": [
                "تحليل التوظيف" if ar else "Recruitment analytics",
                "ملخص عدد الموظفين" if ar else "Headcount summary",
                "معدل الدوران" if ar else "Turnover metrics",
            ],
            "get_payroll_summary": [
                "ميزانية القسم" if ar else "Department budget",
                "توزيع الرواتب" if ar else "Salary distribution",
                "وضع الامتثال" if ar else "Compliance status",
            ],
            # A3 Predictive & Advanced Analytics tools
            "predict_attrition_risk": [
                "معدل الدوران" if ar else "Turnover metrics",
                "توزيع الرواتب" if ar else "Salary distribution",
                "نظرة عامة على القوى العاملة" if ar else "Workforce overview",
            ],
            "forecast_budget": [
                "ميزانية القسم" if ar else "Department budget",
                "ملخص عدد الموظفين" if ar else "Headcount summary",
                "توزيع الرواتب" if ar else "Salary distribution",
            ],
            "audit_gosi_compliance": [
                "ملخص الرواتب" if ar else "Payroll summary",
                "وضع الامتثال" if ar else "Compliance status",
                "نظرة عامة على القوى العاملة" if ar else "Workforce overview",
            ],
            "get_policy_acknowledgments": [
                "وضع الامتثال" if ar else "Compliance status",
                "نظرة عامة على القوى العاملة" if ar else "Workforce overview",
                "ملخص عدد الموظفين" if ar else "Headcount summary",
            ],
            "generate_custom_report": [
                "نظرة عامة على القوى العاملة" if ar else "Workforce overview",
                "ملخص عدد الموظفين" if ar else "Headcount summary",
                "وضع الامتثال" if ar else "Compliance status",
            ],
        }
        return suggestions_map.get(tool_name, [])[:3]

    # ──────────────────────────────────────────────────────────────
    # Tool definitions — A1 (Core HR Metrics + Compliance)
    # ──────────────────────────────────────────────────────────────

    def get_tools(self) -> list[dict]:
        return [
            {
                "name": "get_headcount_summary",
                "description": (
                    "Get headcount summary: total employees, breakdown by department, "
                    "Saudi/non-Saudi split, gender split, and Nitaqat band per department."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "department_id": {
                            "type": "string",
                            "description": "Optional department UUID to filter by",
                        },
                        "period": {
                            "type": "string",
                            "description": "Optional period filter (e.g. 'last_quarter', 'last_year')",
                        },
                    },
                    "required": [],
                },
            },
            {
                "name": "get_saudization_status",
                "description": (
                    "Get Saudization (Nitaqat) status: org-wide and per-department Saudi ratio, "
                    "Nitaqat band, gap to target, and departments at risk."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "department_id": {
                            "type": "string",
                            "description": "Optional department UUID to filter by",
                        },
                    },
                    "required": [],
                },
            },
            {
                "name": "get_turnover_metrics",
                "description": (
                    "Get turnover metrics: overall and per-department turnover rate "
                    "over a given period, voluntary vs involuntary breakdown."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "department_id": {
                            "type": "string",
                            "description": "Optional department UUID to filter by",
                        },
                        "months": {
                            "type": "integer",
                            "description": "Lookback period in months (default 12)",
                        },
                    },
                    "required": [],
                },
            },
            {
                "name": "get_department_budget",
                "description": (
                    "Get department budget analysis: budget vs actual spend, utilization %, "
                    "projected year-end, over/under flag."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "department_id": {
                            "type": "string",
                            "description": "Department UUID (required)",
                        },
                    },
                    "required": ["department_id"],
                },
            },
            {
                "name": "get_salary_distribution",
                "description": (
                    "Get salary distribution stats: min/max/median/avg per department, "
                    "Saudi vs non-Saudi comparison, gender comparison. "
                    "PRIVACY: Only aggregated stats, never individual names or salaries."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "department_id": {
                            "type": "string",
                            "description": "Optional department UUID to filter by",
                        },
                    },
                    "required": [],
                },
            },
            {
                "name": "get_workforce_overview",
                "description": (
                    "Get comprehensive executive workforce overview: headcount, Saudization, "
                    "gender split, department breakdown, AI agent count, key highlights."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
            {
                "name": "get_compliance_status",
                "description": (
                    "Get compliance status: items by category, overdue count, "
                    "at-risk count, overall compliance health."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "category": {
                            "type": "string",
                            "description": "Optional category filter (e.g. 'gosi', 'nitaqat', 'labor_law', 'wps')",
                        },
                    },
                    "required": [],
                },
            },
            # ── A2 Cross-Domain Analytics Tools ──────────────────────
            {
                "name": "get_recruitment_analytics",
                "description": (
                    "Get recruitment pipeline analytics: funnel stages "
                    "(applied → screened → interviewed → offered → hired), open positions count, "
                    "time-to-fill, average AI match score. Filters by department and time period. "
                    "PRIVACY: No candidate names or personal data."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "department_id": {
                            "type": "string",
                            "description": "Optional department UUID to filter job postings by",
                        },
                        "months": {
                            "type": "integer",
                            "description": "Lookback period in months (default 12, max 60)",
                        },
                    },
                    "required": [],
                },
            },
            {
                "name": "get_leave_analytics",
                "description": (
                    "Get leave analytics: usage by leave type (annual, sick, hajj, maternity, etc.), "
                    "department comparison, approval/rejection rates, seasonal patterns, and balance "
                    "utilization. Saudi-specific: tracks Hajj leave, Ramadan patterns. "
                    "PRIVACY: Aggregated only."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "department_id": {
                            "type": "string",
                            "description": "Optional department UUID to filter by",
                        },
                        "months": {
                            "type": "integer",
                            "description": "Lookback period in months (default 12, max 60)",
                        },
                    },
                    "required": [],
                },
            },
            {
                "name": "get_attendance_analytics",
                "description": (
                    "Get attendance analytics: attendance rate, late arrival rate, absence rate, "
                    "overtime hours, department comparison, day-of-week patterns. "
                    "Saudi context: Fri/Sat weekend, prayer time considerations. "
                    "PRIVACY: Aggregated rates only."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "department_id": {
                            "type": "string",
                            "description": "Optional department UUID to filter by",
                        },
                        "months": {
                            "type": "integer",
                            "description": "Lookback period in months (default 3, max 12)",
                        },
                    },
                    "required": [],
                },
            },
            {
                "name": "get_onboarding_analytics",
                "description": (
                    "Get onboarding analytics: completion rate, average completion time (days), "
                    "bottleneck steps (lowest completion rate), overdue step count, department "
                    "breakdown. Tracks new hire onboarding health."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "department_id": {
                            "type": "string",
                            "description": "Optional department UUID to filter by",
                        },
                        "months": {
                            "type": "integer",
                            "description": "Lookback period in months for started assignments (default 6, max 24)",
                        },
                    },
                    "required": [],
                },
            },
            {
                "name": "get_payroll_summary",
                "description": (
                    "Get payroll summary: monthly cost trends, gross/net/deductions totals, "
                    "GOSI breakdown (employer 12% + employee 10%), department cost comparison, "
                    "headcount vs cost. PRIVACY: k-anonymity enforced for small departments."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "department_id": {
                            "type": "string",
                            "description": "Optional department UUID to filter by",
                        },
                        "months": {
                            "type": "integer",
                            "description": "Lookback period in months (default 6, max 24)",
                        },
                    },
                    "required": [],
                },
            },
            # ── A3 Predictive & Advanced Analytics Tools ──────────────
            {
                "name": "predict_attrition_risk",
                "description": (
                    "Score employees or departments on attrition (flight) risk using tenure, "
                    "salary position relative to department median, leave patterns, attendance "
                    "trends, and time-since-last-promotion. Returns risk tiers (high/medium/low) "
                    "with contributing factors. PRIVACY: Individual-level results require "
                    "manager/HR role; department-level is always aggregated."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "department_id": {
                            "type": "string",
                            "description": "Optional department UUID. If omitted, returns org-wide department risk ranking.",
                        },
                        "include_individuals": {
                            "type": "boolean",
                            "description": "If true and requester has manager/HR role, include individual employee risk scores. Default false.",
                        },
                        "risk_threshold": {
                            "type": "string",
                            "enum": ["high", "medium", "low"],
                            "description": "Only return employees/departments at or above this risk level. Default: all.",
                        },
                    },
                    "required": [],
                },
            },
            {
                "name": "forecast_budget",
                "description": (
                    "Project payroll costs forward 3/6/12 months. Includes base payroll from "
                    "current headcount, GOSI contributions (12% employer for Saudis, 2% for "
                    "non-Saudis), and growth scenarios (flat, moderate +5%, aggressive +10% "
                    "headcount growth). Optionally filter by department."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "department_id": {
                            "type": "string",
                            "description": "Optional department UUID. If omitted, forecasts org-wide.",
                        },
                        "horizon_months": {
                            "type": "integer",
                            "description": "Forecast horizon: 3, 6, or 12 months. Default 6.",
                            "enum": [3, 6, 12],
                        },
                        "growth_scenario": {
                            "type": "string",
                            "enum": ["flat", "moderate", "aggressive", "custom"],
                            "description": "Headcount growth scenario. 'flat' = 0% growth, 'moderate' = 5% annual, 'aggressive' = 10% annual. Default: returns all three.",
                        },
                        "custom_growth_pct": {
                            "type": "number",
                            "description": "Annual headcount growth percentage when growth_scenario is 'custom'. e.g. 7.5 for 7.5%.",
                        },
                    },
                    "required": [],
                },
            },
            {
                "name": "audit_gosi_compliance",
                "description": (
                    "Cross-check GOSI contributions in payslips against employee salary records. "
                    "Flags discrepancies where the recorded GOSI employer/employee deduction does "
                    "not match the expected rate (12%/10% for Saudis, 2%/0% for non-Saudis). "
                    "Returns flagged employees with discrepancy details."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "department_id": {
                            "type": "string",
                            "description": "Optional department UUID to scope the audit.",
                        },
                        "month": {
                            "type": "string",
                            "description": "Month to audit in YYYY-MM format. Default: most recent payslip month.",
                        },
                        "tolerance_pct": {
                            "type": "number",
                            "description": "Acceptable deviation percentage (default 1.0). Discrepancies within tolerance are marked as 'minor'.",
                        },
                    },
                    "required": [],
                },
            },
            {
                "name": "get_policy_acknowledgments",
                "description": (
                    "Track policy acknowledgment compliance. Shows which published policies "
                    "employees have/haven't acknowledged, compliance rates by department, and "
                    "overdue acknowledgments. Uses the hr_policies and policy_acknowledgments tables."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "policy_id": {
                            "type": "string",
                            "description": "Optional specific policy UUID to check acknowledgments for.",
                        },
                        "department_id": {
                            "type": "string",
                            "description": "Optional department UUID to filter employees.",
                        },
                        "category": {
                            "type": "string",
                            "description": "Optional policy category filter (leave, attendance, conduct, compensation, benefits, safety, general).",
                        },
                    },
                    "required": [],
                },
            },
            {
                "name": "generate_custom_report",
                "description": (
                    "Generate a custom HR report from a natural language query. Ahmad interprets "
                    "the request, determines which data sources and existing tools to combine, "
                    "executes the queries, and returns a formatted result. Supports cross-referencing "
                    "headcount, saudization, turnover, salary, leave, attendance, onboarding, "
                    "recruitment, payroll, and compliance data. PRIVACY: k-anonymity enforced, "
                    "no individual data unless requester has HR role."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Natural language report request. e.g. 'Departments with high turnover and low Saudization', 'Monthly headcount trend for Engineering', 'Compare leave usage across departments this quarter'.",
                        },
                        "format": {
                            "type": "string",
                            "enum": ["summary", "table", "detailed"],
                            "description": "Output format preference. 'summary' = narrative with key numbers, 'table' = structured rows/columns, 'detailed' = full breakdown. Default: summary.",
                        },
                        "export": {
                            "type": "boolean",
                            "description": "If true, format output as CSV-compatible text. Default false.",
                        },
                    },
                    "required": ["query"],
                },
            },
        ]

    # ──────────────────────────────────────────────────────────────
    # Tool dispatch
    # ──────────────────────────────────────────────────────────────

    async def handle_tool_call(self, tool_name: str, tool_input: dict) -> str:
        try:
            # RBAC: block sensitive tools for unauthorized roles
            if tool_name in self._SENSITIVE_TOOLS and self._employee_role not in self._SENSITIVE_ALLOWED_ROLES:
                return json.dumps({
                    "error": True,
                    "message": "This report requires HR or management access.",
                    "message_ar": "هذا التقرير يتطلب صلاحيات الموارد البشرية أو الإدارة",
                })

            # Validate department_id if provided
            dept_id_raw = tool_input.get("department_id")
            if dept_id_raw is not None:
                try:
                    UUID(dept_id_raw)
                except (ValueError, AttributeError):
                    return json.dumps({"error": "Invalid department_id — must be a valid UUID."})

            if tool_name == "get_headcount_summary":
                return await self._get_headcount_summary(tool_input)
            elif tool_name == "get_saudization_status":
                return await self._get_saudization_status(tool_input)
            elif tool_name == "get_turnover_metrics":
                return await self._get_turnover_metrics(tool_input)
            elif tool_name == "get_department_budget":
                return await self._get_department_budget(tool_input)
            elif tool_name == "get_salary_distribution":
                return await self._get_salary_distribution(tool_input)
            elif tool_name == "get_workforce_overview":
                return await self._get_workforce_overview(tool_input)
            elif tool_name == "get_compliance_status":
                return await self._get_compliance_status(tool_input)
            elif tool_name == "get_recruitment_analytics":
                return await self._get_recruitment_analytics(tool_input)
            elif tool_name == "get_leave_analytics":
                return await self._get_leave_analytics(tool_input)
            elif tool_name == "get_attendance_analytics":
                return await self._get_attendance_analytics(tool_input)
            elif tool_name == "get_onboarding_analytics":
                return await self._get_onboarding_analytics(tool_input)
            elif tool_name == "get_payroll_summary":
                return await self._get_payroll_summary(tool_input)
            # A3 Predictive & Advanced Analytics
            elif tool_name == "predict_attrition_risk":
                return await self._predict_attrition_risk(tool_input)
            elif tool_name == "forecast_budget":
                return await self._forecast_budget(tool_input)
            elif tool_name == "audit_gosi_compliance":
                return await self._audit_gosi_compliance(tool_input)
            elif tool_name == "get_policy_acknowledgments":
                return await self._get_policy_acknowledgments(tool_input)
            elif tool_name == "generate_custom_report":
                return await self._generate_custom_report(tool_input)
            else:
                return json.dumps({"error": f"Unknown tool: {tool_name}"})
        except Exception:
            logger.error(f"Ahmad tool error in {tool_name}", exc_info=True)
            return json.dumps({"error": "Failed to retrieve data. Please try again."})

    # ──────────────────────────────────────────────────────────────
    # Helper: Nitaqat band calculation
    # ──────────────────────────────────────────────────────────────

    def _calculate_nitaqat_band(
        self,
        saudi_pct: float,
        config: NitaqatConfig | None,
    ) -> str:
        """Determine Nitaqat band from Saudi percentage and config thresholds."""
        if config is None:
            # Default thresholds
            if saudi_pct >= 40.0:
                return "platinum"
            elif saudi_pct >= 26.0:
                return "green_high"
            elif saudi_pct >= 17.0:
                return "green_low"
            elif saudi_pct >= 6.0:
                return "yellow"
            else:
                return "red"

        if saudi_pct >= config.platinum_threshold:
            return "platinum"
        elif saudi_pct >= config.green_high_threshold:
            return "green_high"
        elif saudi_pct >= config.green_low_threshold:
            return "green_low"
        elif saudi_pct >= config.yellow_threshold:
            return "yellow"
        else:
            return "red"

    # ──────────────────────────────────────────────────────────────
    # Tool 1: Headcount Summary
    # ──────────────────────────────────────────────────────────────

    async def _get_headcount_summary(self, tool_input: dict) -> str:
        department_id = tool_input.get("department_id")

        # Build base query for active/onboarding/on_leave employees
        active_statuses = [EmployeeStatus.active, EmployeeStatus.onboarding, EmployeeStatus.on_leave]

        # Get departments
        dept_q = select(Department).where(Department.tenant_id == self.tenant_id)
        if department_id:
            dept_q = dept_q.where(Department.id == department_id)
        dept_result = await self.db.execute(dept_q)
        departments = dept_result.scalars().all()

        if not departments:
            return json.dumps({"message": "No departments found.", "departments": []})

        # Load Nitaqat config
        nc_result = await self.db.execute(
            select(NitaqatConfig).where(NitaqatConfig.tenant_id == self.tenant_id)
        )
        nitaqat_config = nc_result.scalar_one_or_none()

        # Single grouped query for all departments — avoids N+1
        emp_q = (
            select(
                Employee.department_id,
                func.count(Employee.id).label("total"),
                func.coalesce(func.sum(case((Employee.is_saudi == True, 1), else_=0)), 0).label("saudi"),
                func.coalesce(func.sum(case((Employee.is_saudi == False, 1), else_=0)), 0).label("non_saudi"),
                func.coalesce(func.sum(case((Employee.gender == Gender.male, 1), else_=0)), 0).label("male"),
                func.coalesce(func.sum(case((Employee.gender == Gender.female, 1), else_=0)), 0).label("female"),
            )
            .where(
                Employee.tenant_id == self.tenant_id,
                Employee.status.in_(active_statuses),
            )
            .group_by(Employee.department_id)
        )
        if department_id:
            emp_q = emp_q.where(Employee.department_id == department_id)
        emp_result = await self.db.execute(emp_q)
        stats_by_dept = {row.department_id: row for row in emp_result.all()}

        dept_data = []
        org_total = 0
        org_saudi = 0
        org_non_saudi = 0
        org_male = 0
        org_female = 0

        for dept in departments:
            row = stats_by_dept.get(dept.id)
            total = int(row.total) if row else 0
            saudi = int(row.saudi) if row else 0
            non_saudi = int(row.non_saudi) if row else 0
            male = int(row.male) if row else 0
            female = int(row.female) if row else 0

            saudi_pct = round((saudi / total * 100), 1) if total > 0 else 0.0
            band = self._calculate_nitaqat_band(saudi_pct, nitaqat_config) if total > 0 else "n/a"

            dept_data.append({
                "department": dept.name,
                "department_ar": dept.name_ar,
                "department_id": str(dept.id),
                "total": total,
                "saudi": saudi,
                "non_saudi": non_saudi,
                "saudi_pct": saudi_pct,
                "male": male,
                "female": female,
                "nitaqat_band": band,
            })

            org_total += total
            org_saudi += saudi
            org_non_saudi += non_saudi
            org_male += male
            org_female += female

        org_saudi_pct = round((org_saudi / org_total * 100), 1) if org_total > 0 else 0.0
        org_band = self._calculate_nitaqat_band(org_saudi_pct, nitaqat_config) if org_total > 0 else "n/a"

        return json.dumps({
            "org_summary": {
                "total_headcount": org_total,
                "saudi": org_saudi,
                "non_saudi": org_non_saudi,
                "saudi_pct": org_saudi_pct,
                "male": org_male,
                "female": org_female,
                "nitaqat_band": org_band,
            },
            "departments": dept_data,
        })

    # ──────────────────────────────────────────────────────────────
    # Tool 2: Saudization Status
    # ──────────────────────────────────────────────────────────────

    async def _get_saudization_status(self, tool_input: dict) -> str:
        department_id = tool_input.get("department_id")
        active_statuses = [EmployeeStatus.active, EmployeeStatus.onboarding, EmployeeStatus.on_leave]

        # Load Nitaqat config
        nc_result = await self.db.execute(
            select(NitaqatConfig).where(NitaqatConfig.tenant_id == self.tenant_id)
        )
        nitaqat_config = nc_result.scalar_one_or_none()
        target_pct = nitaqat_config.target_saudization_pct if nitaqat_config else 26.0

        # Get departments
        dept_q = select(Department).where(Department.tenant_id == self.tenant_id)
        if department_id:
            dept_q = dept_q.where(Department.id == department_id)
        dept_result = await self.db.execute(dept_q)
        departments = dept_result.scalars().all()

        # Single grouped query for all departments — avoids N+1
        emp_q = (
            select(
                Employee.department_id,
                func.count(Employee.id).label("total"),
                func.coalesce(func.sum(case((Employee.is_saudi == True, 1), else_=0)), 0).label("saudi"),
            )
            .where(
                Employee.tenant_id == self.tenant_id,
                Employee.status.in_(active_statuses),
            )
            .group_by(Employee.department_id)
        )
        if department_id:
            emp_q = emp_q.where(Employee.department_id == department_id)
        emp_result = await self.db.execute(emp_q)
        stats_by_dept = {row.department_id: row for row in emp_result.all()}

        dept_data = []
        org_total = 0
        org_saudi = 0
        at_risk_depts = []

        for dept in departments:
            row = stats_by_dept.get(dept.id)
            total = int(row.total) if row else 0
            saudi = int(row.saudi) if row else 0
            saudi_pct = round((saudi / total * 100), 1) if total > 0 else 0.0
            band = self._calculate_nitaqat_band(saudi_pct, nitaqat_config) if total > 0 else "n/a"
            gap = round(target_pct - saudi_pct, 1) if total > 0 else 0.0

            entry = {
                "department": dept.name,
                "department_id": str(dept.id),
                "total": total,
                "saudi": saudi,
                "non_saudi": total - saudi,
                "saudi_pct": saudi_pct,
                "nitaqat_band": band,
                "gap_to_target": gap if gap > 0 else 0.0,
            }
            dept_data.append(entry)

            if band in ("yellow", "red"):
                at_risk_depts.append(dept.name)

            org_total += total
            org_saudi += saudi

        org_saudi_pct = round((org_saudi / org_total * 100), 1) if org_total > 0 else 0.0
        org_band = self._calculate_nitaqat_band(org_saudi_pct, nitaqat_config) if org_total > 0 else "n/a"
        org_gap = round(target_pct - org_saudi_pct, 1) if org_saudi_pct < target_pct else 0.0

        return json.dumps({
            "org_summary": {
                "total": org_total,
                "saudi": org_saudi,
                "saudi_pct": org_saudi_pct,
                "nitaqat_band": org_band,
                "target_pct": target_pct,
                "gap_to_target": org_gap,
            },
            "departments": dept_data,
            "at_risk_departments": at_risk_depts,
        })

    # ──────────────────────────────────────────────────────────────
    # Tool 3: Turnover Metrics
    # ──────────────────────────────────────────────────────────────

    async def _get_turnover_metrics(self, tool_input: dict) -> str:
        department_id = tool_input.get("department_id")
        months = max(1, min(60, tool_input.get("months", 12)))
        cutoff_date = datetime.now(_RIYADH_TZ).date() - timedelta(days=months * 30)

        # Count terminated employees in the period
        term_q = (
            select(
                Department.name.label("dept_name"),
                Department.id.label("dept_id"),
                func.count(Employee.id).label("terminated"),
            )
            .join(Department, Employee.department_id == Department.id)
            .where(
                Employee.tenant_id == self.tenant_id,
                Employee.status == EmployeeStatus.terminated,
                Employee.end_date >= cutoff_date,
            )
            .group_by(Department.id, Department.name)
        )
        if department_id:
            term_q = term_q.where(Employee.department_id == department_id)
        term_result = await self.db.execute(term_q)
        term_rows = term_result.all()

        # Count active employees per department (for rate calculation)
        active_statuses = [EmployeeStatus.active, EmployeeStatus.onboarding, EmployeeStatus.on_leave]
        active_q = (
            select(
                Department.name.label("dept_name"),
                Department.id.label("dept_id"),
                func.count(Employee.id).label("active"),
            )
            .join(Department, Employee.department_id == Department.id)
            .where(
                Employee.tenant_id == self.tenant_id,
                Employee.status.in_(active_statuses),
            )
            .group_by(Department.id, Department.name)
        )
        if department_id:
            active_q = active_q.where(Employee.department_id == department_id)
        active_result = await self.db.execute(active_q)
        active_rows = active_result.all()

        active_map = {str(r.dept_id): {"name": r.dept_name, "active": int(r.active)} for r in active_rows}
        term_map = {str(r.dept_id): int(r.terminated) for r in term_rows}

        total_terminated = 0
        total_active = 0
        dept_data = []

        for dept_id_str, info in active_map.items():
            terminated = term_map.get(dept_id_str, 0)
            active = info["active"]
            # Turnover rate = terminated / (active + terminated) * 100
            pool = active + terminated
            rate = round((terminated / pool * 100), 1) if pool > 0 else 0.0
            entry = {
                "department": info["name"],
                "department_id": dept_id_str,
                "active_employees": active,
            }
            if pool >= self.MIN_GROUP_SIZE:
                entry["terminated_in_period"] = terminated
                entry["turnover_rate_pct"] = rate
            else:
                entry["note"] = "Turnover details suppressed — fewer than 5 employees (privacy threshold)."
            dept_data.append(entry)
            total_terminated += terminated
            total_active += active

        # Also count departments with only terminated (no active left)
        for dept_id_str, terminated in term_map.items():
            if dept_id_str not in active_map:
                total_terminated += terminated

        total_pool = total_active + total_terminated
        overall_rate = round((total_terminated / total_pool * 100), 1) if total_pool > 0 else 0.0

        if total_terminated == 0:
            return json.dumps({
                "message": f"No turnover recorded in the last {months} months.",
                "period_months": months,
                "overall_turnover_rate_pct": 0.0,
                "total_terminated": 0,
                "total_active": total_active,
                "departments": dept_data,
            })

        return json.dumps({
            "period_months": months,
            "overall_turnover_rate_pct": overall_rate,
            "total_terminated": total_terminated,
            "total_active": total_active,
            "departments": dept_data,
        })

    # ──────────────────────────────────────────────────────────────
    # Tool 4: Department Budget
    # ──────────────────────────────────────────────────────────────

    async def _get_department_budget(self, tool_input: dict) -> str:
        department_id = tool_input.get("department_id")
        if not department_id:
            return json.dumps({"error": "department_id is required."})

        # Get department
        dept_result = await self.db.execute(
            select(Department).where(
                Department.id == department_id,
                Department.tenant_id == self.tenant_id,
            )
        )
        dept = dept_result.scalar_one_or_none()
        if not dept:
            return json.dumps({"error": "Department not found."})

        # Sum monthly salaries for active employees
        active_statuses = [EmployeeStatus.active, EmployeeStatus.onboarding, EmployeeStatus.on_leave]
        salary_result = await self.db.execute(
            select(
                func.count(Employee.id).label("headcount"),
                func.coalesce(func.sum(Employee.salary_sar), 0).label("monthly_cost"),
            )
            .where(
                Employee.tenant_id == self.tenant_id,
                Employee.department_id == department_id,
                Employee.status.in_(active_statuses),
            )
        )
        row = salary_result.one()
        headcount = int(row.headcount)
        monthly_cost = int(row.monthly_cost)
        annual_cost = monthly_cost * 12

        annual_budget = dept.cost_budget_sar or 0

        # Project year-end: current month's cost * remaining months
        current_month = datetime.now(_RIYADH_TZ).date().month
        months_elapsed = current_month
        months_remaining = 12 - months_elapsed
        spent_ytd = monthly_cost * months_elapsed
        projected_year_end = spent_ytd + (monthly_cost * months_remaining)

        # Suppress exact salary costs for small departments (k-anonymity)
        suppress_salary = headcount < self.MIN_GROUP_SIZE

        if annual_budget == 0:
            result = {
                "department": dept.name,
                "department_id": str(dept.id),
                "headcount": headcount,
                "headcount_budget": dept.headcount_budget,
                "annual_budget_sar": 0,
                "budget_configured": False,
                "note": "Budget not configured for this department.",
            }
            if not suppress_salary:
                result["monthly_salary_cost_sar"] = monthly_cost
                result["annual_salary_cost_sar"] = annual_cost
                result["spent_ytd_sar"] = spent_ytd
                result["projected_year_end_sar"] = projected_year_end
            else:
                result["salary_note"] = "Salary costs suppressed — fewer than 5 employees (privacy threshold)."
            return json.dumps(result)

        projected_utilization_pct = round((annual_cost / annual_budget * 100), 1)
        over_budget = projected_year_end > annual_budget
        variance = projected_year_end - annual_budget

        result = {
            "department": dept.name,
            "department_id": str(dept.id),
            "headcount": headcount,
            "headcount_budget": dept.headcount_budget,
            "annual_budget_sar": annual_budget,
            "budget_configured": True,
            "over_budget": over_budget,
        }
        if not suppress_salary:
            result["monthly_salary_cost_sar"] = monthly_cost
            result["annual_salary_cost_sar"] = annual_cost
            result["projected_utilization_pct"] = projected_utilization_pct
            result["spent_ytd_sar"] = spent_ytd
            result["projected_year_end_sar"] = projected_year_end
            result["variance_sar"] = variance
        else:
            result["salary_note"] = "Salary costs suppressed — fewer than 5 employees (privacy threshold)."
        return json.dumps(result)

    # ──────────────────────────────────────────────────────────────
    # Tool 5: Salary Distribution
    # ──────────────────────────────────────────────────────────────

    async def _get_salary_distribution(self, tool_input: dict) -> str:
        department_id = tool_input.get("department_id")
        active_statuses = [EmployeeStatus.active, EmployeeStatus.onboarding, EmployeeStatus.on_leave]

        base_where = [
            Employee.tenant_id == self.tenant_id,
            Employee.status.in_(active_statuses),
            Employee.salary_sar.isnot(None),
        ]
        if department_id:
            base_where.append(Employee.department_id == department_id)

        # Overall stats per department
        dept_stats_q = (
            select(
                Department.name.label("dept_name"),
                Department.id.label("dept_id"),
                func.count(Employee.id).label("count"),
                func.min(Employee.salary_sar).label("min_salary"),
                func.max(Employee.salary_sar).label("max_salary"),
                func.avg(Employee.salary_sar).label("avg_salary"),
            )
            .join(Department, Employee.department_id == Department.id)
            .where(*base_where)
            .group_by(Department.id, Department.name)
        )
        dept_result = await self.db.execute(dept_stats_q)
        dept_rows = dept_result.all()

        if not dept_rows:
            return json.dumps({"message": "No salary data available.", "departments": []})

        # Saudi vs non-Saudi comparison (org-level)
        nationality_q = (
            select(
                Employee.is_saudi,
                func.count(Employee.id).label("count"),
                func.min(Employee.salary_sar).label("min_salary"),
                func.max(Employee.salary_sar).label("max_salary"),
                func.avg(Employee.salary_sar).label("avg_salary"),
            )
            .where(*base_where, Employee.is_saudi.isnot(None))
            .group_by(Employee.is_saudi)
        )
        nat_result = await self.db.execute(nationality_q)
        nat_rows = nat_result.all()

        # Gender comparison (org-level)
        gender_q = (
            select(
                Employee.gender,
                func.count(Employee.id).label("count"),
                func.min(Employee.salary_sar).label("min_salary"),
                func.max(Employee.salary_sar).label("max_salary"),
                func.avg(Employee.salary_sar).label("avg_salary"),
            )
            .where(*base_where, Employee.gender.isnot(None))
            .group_by(Employee.gender)
        )
        gender_result = await self.db.execute(gender_q)
        gender_rows = gender_result.all()

        MIN_GROUP_SIZE = self.MIN_GROUP_SIZE

        departments = []
        for r in dept_rows:
            if int(r.count) < MIN_GROUP_SIZE:
                departments.append({
                    "department": r.dept_name,
                    "department_id": str(r.dept_id),
                    "employee_count": int(r.count),
                    "note": "Salary statistics suppressed — fewer than 5 employees (privacy threshold).",
                })
            else:
                departments.append({
                    "department": r.dept_name,
                    "department_id": str(r.dept_id),
                    "employee_count": int(r.count),
                    "min_salary_sar": int(r.min_salary),
                    "max_salary_sar": int(r.max_salary),
                    "avg_salary_sar": round(float(r.avg_salary)),
                })

        nationality_comparison = []
        for r in nat_rows:
            entry = {"group": "Saudi" if r.is_saudi else "Non-Saudi", "count": int(r.count)}
            if int(r.count) < MIN_GROUP_SIZE:
                entry["note"] = "Suppressed — fewer than 5 employees."
            else:
                entry.update({
                    "min_salary_sar": int(r.min_salary),
                    "max_salary_sar": int(r.max_salary),
                    "avg_salary_sar": round(float(r.avg_salary)),
                })
            nationality_comparison.append(entry)

        gender_comparison = []
        for r in gender_rows:
            entry = {"group": r.gender.value if r.gender else "unspecified", "count": int(r.count)}
            if int(r.count) < MIN_GROUP_SIZE:
                entry["note"] = "Suppressed — fewer than 5 employees."
            else:
                entry.update({
                    "min_salary_sar": int(r.min_salary),
                    "max_salary_sar": int(r.max_salary),
                    "avg_salary_sar": round(float(r.avg_salary)),
                })
            gender_comparison.append(entry)

        return json.dumps({
            "privacy_note": "Aggregated statistics only. Groups with fewer than 5 employees are suppressed for privacy.",
            "departments": departments,
            "nationality_comparison": nationality_comparison,
            "gender_comparison": gender_comparison,
        })

    # ──────────────────────────────────────────────────────────────
    # Tool 6: Workforce Overview (Executive Dashboard)
    # ──────────────────────────────────────────────────────────────

    async def _get_workforce_overview(self, tool_input: dict) -> str:
        active_statuses = [EmployeeStatus.active, EmployeeStatus.onboarding, EmployeeStatus.on_leave]

        # Total headcount
        hc_result = await self.db.execute(
            select(
                func.count(Employee.id).label("total"),
                func.coalesce(func.sum(case((Employee.is_saudi == True, 1), else_=0)), 0).label("saudi"),
                func.coalesce(func.sum(case((Employee.gender == Gender.male, 1), else_=0)), 0).label("male"),
                func.coalesce(func.sum(case((Employee.gender == Gender.female, 1), else_=0)), 0).label("female"),
                func.coalesce(func.sum(case((Employee.status == EmployeeStatus.onboarding, 1), else_=0)), 0).label("onboarding"),
            )
            .where(
                Employee.tenant_id == self.tenant_id,
                Employee.status.in_(active_statuses),
            )
        )
        hc = hc_result.one()
        total = int(hc.total)
        saudi = int(hc.saudi)
        male = int(hc.male)
        female = int(hc.female)
        onboarding = int(hc.onboarding)

        saudi_pct = round((saudi / total * 100), 1) if total > 0 else 0.0

        # Department count
        dept_count_result = await self.db.execute(
            select(func.count(Department.id)).where(Department.tenant_id == self.tenant_id)
        )
        dept_count = dept_count_result.scalar() or 0

        # Department breakdown
        dept_q = (
            select(
                Department.name.label("dept_name"),
                func.count(Employee.id).label("count"),
            )
            .join(Department, Employee.department_id == Department.id)
            .where(
                Employee.tenant_id == self.tenant_id,
                Employee.status.in_(active_statuses),
            )
            .group_by(Department.name)
            .order_by(func.count(Employee.id).desc())
        )
        dept_result = await self.db.execute(dept_q)
        dept_breakdown = [{"department": r.dept_name, "headcount": int(r.count)} for r in dept_result.all()]

        # AI agents count
        agent_result = await self.db.execute(
            select(func.count(DeployedAgent.id)).where(
                DeployedAgent.tenant_id == self.tenant_id,
                DeployedAgent.status == AgentStatus.active,
            )
        )
        ai_agent_count = agent_result.scalar() or 0

        # Nitaqat config
        nc_result = await self.db.execute(
            select(NitaqatConfig).where(NitaqatConfig.tenant_id == self.tenant_id)
        )
        nitaqat_config = nc_result.scalar_one_or_none()
        band = self._calculate_nitaqat_band(saudi_pct, nitaqat_config) if total > 0 else "n/a"

        # Key highlights
        highlights = []
        if total > 0:
            highlights.append(f"Total workforce: {total} employees across {dept_count} departments")
            highlights.append(f"Saudization: {saudi_pct}% ({band.replace('_', ' ').title()} band)")
            if female > 0:
                female_pct = round((female / total * 100), 1)
                highlights.append(f"Gender diversity: {female_pct}% female representation")
            if onboarding > 0:
                highlights.append(f"{onboarding} employee(s) currently onboarding")
            if ai_agent_count > 0:
                highlights.append(f"{ai_agent_count} active AI agent(s) deployed")

        return json.dumps({
            "headcount": {
                "total": total,
                "saudi": saudi,
                "non_saudi": total - saudi,
                "saudi_pct": saudi_pct,
                "male": male,
                "female": female,
                "onboarding": onboarding,
            },
            "nitaqat_band": band,
            "department_count": dept_count,
            "department_breakdown": dept_breakdown,
            "ai_agents_active": ai_agent_count,
            "highlights": highlights,
        })

    # ──────────────────────────────────────────────────────────────
    # Tool 7: Compliance Status
    # ──────────────────────────────────────────────────────────────

    VALID_COMPLIANCE_CATEGORIES = {"gosi", "nitaqat", "labor_law", "wps", "mol", "hr_policy"}

    async def _get_compliance_status(self, tool_input: dict) -> str:
        category_filter = tool_input.get("category")
        if category_filter and category_filter not in self.VALID_COMPLIANCE_CATEGORIES:
            return json.dumps({
                "error": f"Unknown category '{category_filter}'.",
                "valid_categories": sorted(self.VALID_COMPLIANCE_CATEGORIES),
            })

        # Query compliance records
        q = select(ComplianceRecord).where(ComplianceRecord.tenant_id == self.tenant_id)
        if category_filter:
            q = q.where(ComplianceRecord.category == category_filter)
        result = await self.db.execute(q)
        records = result.scalars().all()

        if not records:
            return json.dumps({
                "message": "No compliance records found. This may mean compliance tracking has not been configured yet.",
                "total_items": 0,
                "compliant": 0,
                "non_compliant": 0,
                "overdue": 0,
                "categories": [],
            })

        today = datetime.now(_RIYADH_TZ).date()
        total = len(records)
        compliant = 0
        non_compliant = 0
        overdue = 0
        at_risk = 0
        by_category: dict[str, list] = {}

        for rec in records:
            if rec.is_compliant:
                compliant += 1
            else:
                non_compliant += 1

            is_overdue = False
            is_at_risk = False
            if rec.next_deadline:
                if rec.next_deadline < today and not rec.is_compliant:
                    overdue += 1
                    is_overdue = True
                elif rec.next_deadline <= today + timedelta(days=30) and not rec.is_compliant:
                    at_risk += 1
                    is_at_risk = True

            cat = rec.category or "uncategorized"
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append({
                "title": rec.title,
                "is_compliant": rec.is_compliant,
                "last_checked": rec.last_checked.isoformat() if rec.last_checked else None,
                "next_deadline": rec.next_deadline.isoformat() if rec.next_deadline else None,
                "is_overdue": is_overdue,
                "is_at_risk": is_at_risk,
            })

        overall_status = "compliant" if non_compliant == 0 else ("critical" if overdue > 0 else "needs_attention")

        categories_summary = []
        for cat, items in by_category.items():
            cat_compliant = sum(1 for i in items if i["is_compliant"])
            categories_summary.append({
                "category": cat,
                "total": len(items),
                "compliant": cat_compliant,
                "non_compliant": len(items) - cat_compliant,
                "items": items,
            })

        return json.dumps({
            "overall_status": overall_status,
            "total_items": total,
            "compliant": compliant,
            "non_compliant": non_compliant,
            "overdue": overdue,
            "at_risk_30_days": at_risk,
            "categories": categories_summary,
        })

    # ──────────────────────────────────────────────────────────────
    # Tool 8: Recruitment Analytics (A2-01)
    # ──────────────────────────────────────────────────────────────

    async def _get_recruitment_analytics(self, tool_input: dict) -> str:
        department_id = tool_input.get("department_id")
        months = max(1, min(60, tool_input.get("months", 12)))
        cutoff = datetime.now(_RIYADH_TZ).date() - timedelta(days=months * 30)

        dept_filter = []
        if department_id:
            dept_filter = [JobPosting.department_id == department_id]

        # Query 1 — Open positions count
        open_q = (
            select(func.count(JobPosting.id))
            .where(
                JobPosting.tenant_id == self.tenant_id,
                JobPosting.status == PostingStatus.open,
                *dept_filter,
            )
        )
        open_result = await self.db.execute(open_q)
        open_positions = open_result.scalar() or 0

        # Query 2 — Funnel stages
        funnel_q = (
            select(
                Candidate.stage,
                func.count(Candidate.id).label("count"),
            )
            .join(JobPosting, Candidate.job_posting_id == JobPosting.id)
            .where(
                JobPosting.tenant_id == self.tenant_id,
                Candidate.created_at >= cutoff,
                *dept_filter,
            )
            .group_by(Candidate.stage)
        )
        funnel_result = await self.db.execute(funnel_q)
        funnel_rows = funnel_result.all()

        funnel = {}
        for row in funnel_rows:
            funnel[row.stage.value] = int(row.count)

        # Fill all stages with 0 if missing
        all_stages = [s.value for s in CandidateStage]
        for stage in all_stages:
            funnel.setdefault(stage, 0)

        # Query 3 — Time-to-fill (avg days from posting to first hired candidate)
        hired_sub = (
            select(
                JobPosting.id.label("jp_id"),
                JobPosting.created_at.label("posted_at"),
                func.min(Candidate.created_at).label("hired_at"),
            )
            .join(Candidate, Candidate.job_posting_id == JobPosting.id)
            .where(
                JobPosting.tenant_id == self.tenant_id,
                Candidate.stage == CandidateStage.hired,
                JobPosting.created_at >= cutoff,
                *dept_filter,
            )
            .group_by(JobPosting.id, JobPosting.created_at)
        ).subquery()

        ttf_result = await self.db.execute(
            select(hired_sub.c.posted_at, hired_sub.c.hired_at)
        )
        ttf_rows = ttf_result.all()
        if ttf_rows:
            ttf_days = [(row.hired_at - row.posted_at).days for row in ttf_rows]
            avg_ttf = round(sum(ttf_days) / len(ttf_days), 1)
        else:
            avg_ttf = None

        # Query 4 — Average AI match score
        score_q = (
            select(
                func.avg(Candidate.ai_match_score).label("avg_score"),
                func.count(Candidate.id).label("scored_count"),
            )
            .join(JobPosting, Candidate.job_posting_id == JobPosting.id)
            .where(
                JobPosting.tenant_id == self.tenant_id,
                Candidate.ai_match_score.isnot(None),
                Candidate.created_at >= cutoff,
                *dept_filter,
            )
        )
        score_result = await self.db.execute(score_q)
        score_row = score_result.one()
        avg_ai_score = round(float(score_row.avg_score), 1) if score_row.avg_score else None
        candidates_scored = int(score_row.scored_count)

        # Query 5 — Postings by status
        status_q = (
            select(
                JobPosting.status,
                func.count(JobPosting.id).label("count"),
            )
            .where(
                JobPosting.tenant_id == self.tenant_id,
                JobPosting.created_at >= cutoff,
                *dept_filter,
            )
            .group_by(JobPosting.status)
        )
        status_result = await self.db.execute(status_q)
        postings_by_status = {}
        for row in status_result.all():
            postings_by_status[row.status.value] = int(row.count)

        # Conversion rates
        applied = funnel.get("applied", 0)
        screened = funnel.get("screened", 0)
        interviewed = funnel.get("interviewed", 0)
        offer_sent = funnel.get("offer_sent", 0)
        hired = funnel.get("hired", 0)

        conversion_rates = {
            "applied_to_screened_pct": round(screened / applied * 100, 1) if applied > 0 else 0.0,
            "screened_to_interviewed_pct": round(interviewed / screened * 100, 1) if screened > 0 else 0.0,
            "interviewed_to_offered_pct": round(offer_sent / interviewed * 100, 1) if interviewed > 0 else 0.0,
            "offered_to_hired_pct": round(hired / offer_sent * 100, 1) if offer_sent > 0 else 0.0,
            "overall_pct": round(hired / applied * 100, 1) if applied > 0 else 0.0,
        }

        total_candidates = sum(funnel.values())
        if total_candidates == 0 and open_positions == 0:
            return json.dumps({
                "message": f"No job postings or candidates found for the last {months} months.",
                "period_months": months,
                "open_positions": 0,
                "postings_by_status": {},
                "funnel": funnel,
                "conversion_rates": conversion_rates,
                "avg_time_to_fill_days": None,
                "avg_ai_match_score": None,
                "candidates_scored": 0,
                "privacy_note": "Aggregated pipeline data only. No candidate names or personal data.",
            })

        return json.dumps({
            "period_months": months,
            "open_positions": open_positions,
            "postings_by_status": postings_by_status,
            "funnel": funnel,
            "conversion_rates": conversion_rates,
            "avg_time_to_fill_days": avg_ttf,
            "time_to_fill_note": "Approximation: measures posting creation to hired candidate's application date. Actual hire decision date is not tracked.",
            "avg_ai_match_score": avg_ai_score,
            "candidates_scored": candidates_scored,
            "privacy_note": "Aggregated pipeline data only. No candidate names or personal data.",
        })

    # ──────────────────────────────────────────────────────────────
    # Tool 9: Leave Analytics (A2-02)
    # ──────────────────────────────────────────────────────────────

    MONTH_NAMES = {
        1: "January", 2: "February", 3: "March", 4: "April",
        5: "May", 6: "June", 7: "July", 8: "August",
        9: "September", 10: "October", 11: "November", 12: "December",
    }

    async def _get_leave_analytics(self, tool_input: dict) -> str:
        department_id = tool_input.get("department_id")
        months = max(1, min(60, tool_input.get("months", 12)))
        cutoff = datetime.now(_RIYADH_TZ).date() - timedelta(days=months * 30)

        dept_filter = []
        if department_id:
            dept_filter = [Employee.department_id == department_id]

        # Query 1 — Usage by leave type (approved requests in period)
        by_type_q = (
            select(
                LeaveRequest.leave_type,
                func.coalesce(func.sum(LeaveRequest.business_days), 0).label("total_days"),
                func.count(LeaveRequest.id).label("request_count"),
            )
            .join(Employee, LeaveRequest.employee_id == Employee.id)
            .where(
                Employee.tenant_id == self.tenant_id,
                LeaveRequest.status == LeaveStatus.approved,
                LeaveRequest.start_date >= cutoff,
                *dept_filter,
            )
            .group_by(LeaveRequest.leave_type)
        )
        by_type_result = await self.db.execute(by_type_q)
        by_type = [
            {
                "leave_type": row.leave_type.value,
                "total_days": int(row.total_days),
                "request_count": int(row.request_count),
            }
            for row in by_type_result.all()
        ]

        # Query 2 — Approval/rejection rates
        decision_q = (
            select(
                LeaveRequest.status,
                func.count(LeaveRequest.id).label("count"),
            )
            .join(Employee, LeaveRequest.employee_id == Employee.id)
            .where(
                Employee.tenant_id == self.tenant_id,
                LeaveRequest.created_at >= cutoff,
                LeaveRequest.status.in_([
                    LeaveStatus.approved, LeaveStatus.rejected, LeaveStatus.pending,
                ]),
                *dept_filter,
            )
            .group_by(LeaveRequest.status)
        )
        decision_result = await self.db.execute(decision_q)
        decision_map = {row.status.value: int(row.count) for row in decision_result.all()}
        total_requests = sum(decision_map.values())
        approved_count = decision_map.get("approved", 0)
        rejected_count = decision_map.get("rejected", 0)
        pending_count_in_period = decision_map.get("pending", 0)

        approval_rates = {
            "total_requests": total_requests,
            "approved": approved_count,
            "rejected": rejected_count,
            "pending": pending_count_in_period,
            "approval_rate_pct": round(approved_count / total_requests * 100, 1) if total_requests > 0 else 0.0,
            "rejection_rate_pct": round(rejected_count / total_requests * 100, 1) if total_requests > 0 else 0.0,
        }

        # Query 3 — Department comparison (approved days per department)
        dept_q = (
            select(
                Department.name.label("dept_name"),
                Department.id.label("dept_id"),
                func.coalesce(func.sum(LeaveRequest.business_days), 0).label("total_days"),
                func.count(LeaveRequest.id).label("request_count"),
                func.count(func.distinct(LeaveRequest.employee_id)).label("unique_employees"),
            )
            .join(Employee, LeaveRequest.employee_id == Employee.id)
            .join(Department, Employee.department_id == Department.id)
            .where(
                Employee.tenant_id == self.tenant_id,
                LeaveRequest.status == LeaveStatus.approved,
                LeaveRequest.start_date >= cutoff,
            )
            .group_by(Department.id, Department.name)
        )
        if department_id:
            dept_q = dept_q.where(Employee.department_id == department_id)
        dept_result = await self.db.execute(dept_q)

        department_comparison = []
        for row in dept_result.all():
            unique_emp = int(row.unique_employees)
            total_days = int(row.total_days)
            entry = {
                "department": row.dept_name,
                "department_id": str(row.dept_id),
                "total_days": total_days,
                "request_count": int(row.request_count),
                "unique_employees": unique_emp,
            }
            if unique_emp >= self.MIN_GROUP_SIZE:
                entry["avg_days_per_employee"] = round(total_days / unique_emp, 1) if unique_emp > 0 else 0.0
            else:
                entry["note"] = "Per-employee average suppressed — fewer than 5 employees (privacy threshold)."
            department_comparison.append(entry)

        # Query 4 — Monthly seasonal pattern
        monthly_q = (
            select(
                func.extract("month", LeaveRequest.start_date).label("month"),
                func.coalesce(func.sum(LeaveRequest.business_days), 0).label("days"),
                func.count(LeaveRequest.id).label("requests"),
            )
            .join(Employee, LeaveRequest.employee_id == Employee.id)
            .where(
                Employee.tenant_id == self.tenant_id,
                LeaveRequest.status == LeaveStatus.approved,
                LeaveRequest.start_date >= cutoff,
                *dept_filter,
            )
            .group_by(func.extract("month", LeaveRequest.start_date))
            .order_by(func.extract("month", LeaveRequest.start_date))
        )
        monthly_result = await self.db.execute(monthly_q)

        # Saudi seasonal notes
        peak_months_set = set()
        monthly_pattern = []
        for row in monthly_result.all():
            month_num = int(row.month)
            entry = {
                "month": month_num,
                "month_name": self.MONTH_NAMES.get(month_num, ""),
                "days": int(row.days),
                "requests": int(row.requests),
            }
            # Approximate Ramadan/Hajj months (Islamic calendar shifts ~11 days/year;
            # these are approximate for 2026-2027. TODO: use Hijri calendar library)
            if month_num in (2, 3):
                entry["note"] = "Ramadan period (approximate)"
                peak_months_set.add(self.MONTH_NAMES.get(month_num, ""))
            elif month_num in (5, 6):
                entry["note"] = "Hajj season (approximate)"
                peak_months_set.add(self.MONTH_NAMES.get(month_num, ""))
            elif month_num in (7, 8):
                entry["note"] = "Summer break period"
                peak_months_set.add(self.MONTH_NAMES.get(month_num, ""))
            monthly_pattern.append(entry)

        # Query 5 — Balance utilization (current year)
        current_year = datetime.now(_RIYADH_TZ).date().year
        util_q = (
            select(
                LeaveBalance.leave_type,
                func.coalesce(func.sum(LeaveBalance.total_days), 0).label("entitled"),
                func.coalesce(func.sum(LeaveBalance.used_days), 0).label("used"),
            )
            .join(Employee, LeaveBalance.employee_id == Employee.id)
            .where(
                Employee.tenant_id == self.tenant_id,
                LeaveBalance.year == current_year,
                *dept_filter,
            )
            .group_by(LeaveBalance.leave_type)
        )
        util_result = await self.db.execute(util_q)
        balance_utilization = []
        for row in util_result.all():
            entitled = int(row.entitled)
            used = int(row.used)
            balance_utilization.append({
                "leave_type": row.leave_type.value,
                "entitled": entitled,
                "used": used,
                "utilization_pct": round(used / entitled * 100, 1) if entitled > 0 else 0.0,
            })

        # Query 6 — Pending requests count (org-wide)
        pending_q = (
            select(func.count(LeaveRequest.id))
            .join(Employee, LeaveRequest.employee_id == Employee.id)
            .where(
                Employee.tenant_id == self.tenant_id,
                LeaveRequest.status == LeaveStatus.pending,
            )
        )
        pending_result = await self.db.execute(pending_q)
        pending_requests = pending_result.scalar() or 0

        if not by_type and total_requests == 0:
            return json.dumps({
                "message": f"No leave requests found for the last {months} months.",
                "period_months": months,
                "by_type": [],
                "approval_rates": approval_rates,
                "department_comparison": [],
                "monthly_pattern": [],
                "balance_utilization": balance_utilization,
                "pending_requests": pending_requests,
            })

        # Hajj leave count from by_type data
        hajj_leaves = next((t["request_count"] for t in by_type if t["leave_type"] == "hajj"), 0)

        saudi_insights = {
            "hajj_leaves_taken": hajj_leaves,
            "hajj_note": "Hajj leave is a one-time entitlement during employment.",
            "peak_months": sorted(peak_months_set),
            "peak_note": "Leave peaks align with Ramadan and Hajj seasons.",
        }

        return json.dumps({
            "period_months": months,
            "by_type": by_type,
            "approval_rates": approval_rates,
            "department_comparison": department_comparison,
            "monthly_pattern": monthly_pattern,
            "balance_utilization": balance_utilization,
            "pending_requests": pending_requests,
            "saudi_insights": saudi_insights,
        })

    # ──────────────────────────────────────────────────────────────
    # Tool 10: Attendance Analytics (A2-03)
    # ──────────────────────────────────────────────────────────────

    DOW_NAMES = {
        0: ("Sunday", "الأحد"),
        1: ("Monday", "الاثنين"),
        2: ("Tuesday", "الثلاثاء"),
        3: ("Wednesday", "الأربعاء"),
        4: ("Thursday", "الخميس"),
        5: ("Friday", "الجمعة"),
        6: ("Saturday", "السبت"),
    }

    async def _get_attendance_analytics(self, tool_input: dict) -> str:
        department_id = tool_input.get("department_id")
        months = max(1, min(12, tool_input.get("months", 3)))
        cutoff = datetime.now(_RIYADH_TZ).date() - timedelta(days=months * 30)

        exclude_statuses = [AttendanceStatus.weekend, AttendanceStatus.holiday]

        # Build optional department join/filter
        dept_join = []
        dept_where = []
        if department_id:
            dept_join = [(Employee, AttendanceRecord.employee_id == Employee.id)]
            dept_where = [Employee.department_id == department_id]

        # Query 1 — Status breakdown
        status_q = (
            select(
                AttendanceRecord.status,
                func.count(AttendanceRecord.id).label("count"),
            )
            .where(
                AttendanceRecord.tenant_id == self.tenant_id,
                AttendanceRecord.date >= cutoff,
                AttendanceRecord.status.notin_(exclude_statuses),
            )
            .group_by(AttendanceRecord.status)
        )
        if department_id:
            status_q = status_q.join(
                Employee, AttendanceRecord.employee_id == Employee.id
            ).where(Employee.department_id == department_id)
        status_result = await self.db.execute(status_q)
        status_map = {row.status.value: int(row.count) for row in status_result.all()}

        total_records = sum(status_map.values())
        if total_records == 0:
            return json.dumps({
                "message": f"No attendance records found for the last {months} months. Attendance tracking may not be configured yet.",
                "period_months": months,
            })

        present = status_map.get("present", 0)
        late = status_map.get("late", 0)
        absent = status_map.get("absent", 0)
        half_day = status_map.get("half_day", 0)
        on_leave = status_map.get("on_leave", 0)

        summary = {
            "total_work_records": total_records,
            "present": present,
            "late": late,
            "absent": absent,
            "half_day": half_day,
            "on_leave": on_leave,
            "attendance_rate_pct": round((present + late) / total_records * 100, 1) if total_records > 0 else 0.0,
            "late_rate_pct": round(late / total_records * 100, 1) if total_records > 0 else 0.0,
            "absence_rate_pct": round(absent / total_records * 100, 1) if total_records > 0 else 0.0,
        }

        # Query 2 — Overtime summary
        ot_q = (
            select(
                func.coalesce(func.sum(AttendanceRecord.overtime_hours), 0.0).label("total_ot"),
                func.count(func.distinct(AttendanceRecord.employee_id)).label("employees_with_ot"),
                func.avg(AttendanceRecord.overtime_hours).label("avg_ot_per_record"),
            )
            .where(
                AttendanceRecord.tenant_id == self.tenant_id,
                AttendanceRecord.date >= cutoff,
                AttendanceRecord.overtime_hours > 0,
            )
        )
        if department_id:
            ot_q = ot_q.join(
                Employee, AttendanceRecord.employee_id == Employee.id
            ).where(Employee.department_id == department_id)
        ot_result = await self.db.execute(ot_q)
        ot_row = ot_result.one()

        overtime = {
            "total_hours": round(float(ot_row.total_ot), 1),
            "employees_with_overtime": int(ot_row.employees_with_ot),
            "avg_hours_per_record": round(float(ot_row.avg_ot_per_record), 1) if ot_row.avg_ot_per_record else 0.0,
        }

        # Query 3 — Department comparison
        dept_q = (
            select(
                Department.name.label("dept_name"),
                Department.id.label("dept_id"),
                func.count(AttendanceRecord.id).label("total_records"),
                func.sum(case((AttendanceRecord.status == AttendanceStatus.present, 1), else_=0)).label("present"),
                func.sum(case((AttendanceRecord.status == AttendanceStatus.late, 1), else_=0)).label("late"),
                func.sum(case((AttendanceRecord.status == AttendanceStatus.absent, 1), else_=0)).label("absent"),
                func.coalesce(func.sum(AttendanceRecord.overtime_hours), 0.0).label("overtime"),
                func.count(func.distinct(AttendanceRecord.employee_id)).label("unique_employees"),
            )
            .join(Employee, AttendanceRecord.employee_id == Employee.id)
            .join(Department, Employee.department_id == Department.id)
            .where(
                AttendanceRecord.tenant_id == self.tenant_id,
                AttendanceRecord.date >= cutoff,
                AttendanceRecord.status.notin_(exclude_statuses),
            )
            .group_by(Department.id, Department.name)
        )
        if department_id:
            dept_q = dept_q.where(Employee.department_id == department_id)
        dept_result = await self.db.execute(dept_q)

        department_comparison = []
        for row in dept_result.all():
            unique_emp = int(row.unique_employees)
            dept_total = int(row.total_records)
            dept_present = int(row.present)
            dept_late = int(row.late)
            dept_absent = int(row.absent)
            entry = {
                "department": row.dept_name,
                "department_id": str(row.dept_id),
            }
            if unique_emp >= self.MIN_GROUP_SIZE:
                entry.update({
                    "total_records": dept_total,
                    "present": dept_present,
                    "late": dept_late,
                    "absent": dept_absent,
                    "attendance_rate_pct": round((dept_present + dept_late) / dept_total * 100, 1) if dept_total > 0 else 0.0,
                    "late_rate_pct": round(dept_late / dept_total * 100, 1) if dept_total > 0 else 0.0,
                    "overtime_hours": round(float(row.overtime), 1),
                })
            else:
                entry["note"] = "Attendance details suppressed — fewer than 5 employees (privacy threshold)."
            department_comparison.append(entry)

        # Query 4 — Day-of-week pattern
        dow_q = (
            select(
                func.extract("dow", AttendanceRecord.date).label("day_of_week"),
                func.count(AttendanceRecord.id).label("total"),
                func.sum(case(
                    (AttendanceRecord.status.in_([AttendanceStatus.present, AttendanceStatus.late]), 1),
                    else_=0,
                )).label("present_count"),
                func.sum(case(
                    (AttendanceRecord.status == AttendanceStatus.late, 1),
                    else_=0,
                )).label("late_count"),
            )
            .where(
                AttendanceRecord.tenant_id == self.tenant_id,
                AttendanceRecord.date >= cutoff,
                AttendanceRecord.status.notin_(exclude_statuses),
            )
            .group_by(func.extract("dow", AttendanceRecord.date))
            .order_by(func.extract("dow", AttendanceRecord.date))
        )
        if department_id:
            dow_q = dow_q.join(
                Employee, AttendanceRecord.employee_id == Employee.id
            ).where(Employee.department_id == department_id)
        dow_result = await self.db.execute(dow_q)

        # Compute average late rate for flagging
        dow_rows_data = []
        for row in dow_result.all():
            dow_num = int(row.day_of_week)
            row_total = int(row.total)
            row_present = int(row.present_count)
            row_late = int(row.late_count)
            att_rate = round(row_present / row_total * 100, 1) if row_total > 0 else 0.0
            late_rate = round(row_late / row_total * 100, 1) if row_total > 0 else 0.0
            dow_rows_data.append((dow_num, att_rate, late_rate))

        avg_late_rate = (
            sum(lr for _, _, lr in dow_rows_data) / len(dow_rows_data)
            if dow_rows_data else 0.0
        )

        day_of_week_pattern = []
        for dow_num, att_rate, late_rate in dow_rows_data:
            names = self.DOW_NAMES.get(dow_num, ("Unknown", "غير معروف"))
            entry = {
                "day": names[0],
                "day_ar": names[1],
                "attendance_rate_pct": att_rate,
                "late_rate_pct": late_rate,
            }
            if dow_num == 4 and late_rate > avg_late_rate:
                entry["note"] = "Pre-weekend dip typical"
            elif dow_num == 0 and late_rate > avg_late_rate:
                entry["note"] = "Start-of-week pattern"
            day_of_week_pattern.append(entry)

        return json.dumps({
            "period_months": months,
            "summary": summary,
            "overtime": overtime,
            "department_comparison": department_comparison,
            "day_of_week_pattern": day_of_week_pattern,
            "saudi_context": {
                "weekend_days": "Friday & Saturday",
                "work_week": "Sunday to Thursday",
                "note": "Attendance rates exclude Fri/Sat weekends and public holidays.",
            },
        })

    # ──────────────────────────────────────────────────────────────
    # Tool 11: Onboarding Analytics (A2-04)
    # ──────────────────────────────────────────────────────────────

    async def _get_onboarding_analytics(self, tool_input: dict) -> str:
        department_id = tool_input.get("department_id")
        months = max(1, min(24, tool_input.get("months", 6)))
        cutoff = datetime.now(timezone.utc) - timedelta(days=months * 30)

        dept_join = []
        dept_where = []
        if department_id:
            dept_join = [(Employee, OnboardingAssignment.employee_id == Employee.id)]
            dept_where = [Employee.department_id == department_id]

        # Query 1 — Overall completion stats
        stats_q = (
            select(
                func.count(OnboardingAssignment.id).label("total"),
                func.sum(case(
                    (OnboardingAssignment.status == OnboardingAssignmentStatus.completed, 1),
                    else_=0,
                )).label("completed"),
                func.sum(case(
                    (OnboardingAssignment.status == OnboardingAssignmentStatus.in_progress, 1),
                    else_=0,
                )).label("in_progress"),
                func.sum(case(
                    (OnboardingAssignment.status == OnboardingAssignmentStatus.cancelled, 1),
                    else_=0,
                )).label("cancelled"),
            )
            .where(
                OnboardingAssignment.tenant_id == self.tenant_id,
                OnboardingAssignment.started_at >= cutoff,
            )
        )
        if department_id:
            stats_q = stats_q.join(
                Employee, OnboardingAssignment.employee_id == Employee.id
            ).where(Employee.department_id == department_id)
        stats_result = await self.db.execute(stats_q)
        stats_row = stats_result.one()

        total_assignments = int(stats_row.total)
        completed = int(stats_row.completed or 0)
        in_progress = int(stats_row.in_progress or 0)
        cancelled = int(stats_row.cancelled or 0)

        if total_assignments == 0:
            return json.dumps({
                "message": f"No onboarding assignments found for the last {months} months.",
                "period_months": months,
                "summary": {
                    "total_assignments": 0,
                    "completed": 0,
                    "in_progress": 0,
                    "cancelled": 0,
                    "completion_rate_pct": 0.0,
                },
                "completion_time": {"avg_days": None, "min_days": None, "max_days": None},
                "overdue_steps": 0,
                "bottleneck_steps": [],
                "department_breakdown": [],
            })

        completion_rate = round(completed / total_assignments * 100, 1) if total_assignments > 0 else 0.0

        # Query 2 — Average completion time (completed assignments only)
        avg_q = (
            select(
                func.avg(
                    func.extract("epoch",
                        OnboardingAssignment.completed_at - OnboardingAssignment.started_at
                    ) / 86400
                ).label("avg_days"),
                func.min(
                    func.extract("epoch",
                        OnboardingAssignment.completed_at - OnboardingAssignment.started_at
                    ) / 86400
                ).label("min_days"),
                func.max(
                    func.extract("epoch",
                        OnboardingAssignment.completed_at - OnboardingAssignment.started_at
                    ) / 86400
                ).label("max_days"),
            )
            .where(
                OnboardingAssignment.tenant_id == self.tenant_id,
                OnboardingAssignment.status == OnboardingAssignmentStatus.completed,
                OnboardingAssignment.started_at >= cutoff,
                OnboardingAssignment.completed_at.isnot(None),
            )
        )
        if department_id:
            avg_q = avg_q.join(
                Employee, OnboardingAssignment.employee_id == Employee.id
            ).where(Employee.department_id == department_id)
        avg_result = await self.db.execute(avg_q)
        avg_row = avg_result.one()

        completion_time = {
            "avg_days": round(float(avg_row.avg_days), 1) if avg_row.avg_days else None,
            "min_days": round(float(avg_row.min_days), 1) if avg_row.min_days else None,
            "max_days": round(float(avg_row.max_days), 1) if avg_row.max_days else None,
        }

        # Query 3 — Bottleneck steps
        bottleneck_q = (
            select(
                OnboardingTemplateStep.name.label("step_name"),
                OnboardingTemplateStep.name_ar.label("step_name_ar"),
                OnboardingTemplateStep.order.label("step_order"),
                func.count(OnboardingStepAssignment.id).label("total"),
                func.sum(case(
                    (OnboardingStepAssignment.status == OnboardingStepStatus.completed, 1),
                    else_=0,
                )).label("completed"),
            )
            .join(
                OnboardingAssignment,
                OnboardingStepAssignment.assignment_id == OnboardingAssignment.id,
            )
            .join(
                OnboardingTemplateStep,
                OnboardingStepAssignment.template_step_id == OnboardingTemplateStep.id,
            )
            .where(
                OnboardingAssignment.tenant_id == self.tenant_id,
                OnboardingAssignment.started_at >= cutoff,
            )
            .group_by(
                OnboardingTemplateStep.id,
                OnboardingTemplateStep.name,
                OnboardingTemplateStep.name_ar,
                OnboardingTemplateStep.order,
            )
            .order_by(OnboardingTemplateStep.order)
        )
        if department_id:
            bottleneck_q = bottleneck_q.join(
                Employee, OnboardingAssignment.employee_id == Employee.id
            ).where(Employee.department_id == department_id)
        bottleneck_result = await self.db.execute(bottleneck_q)
        bottleneck_rows = bottleneck_result.all()

        # Compute per-step completion rates and find the lowest
        step_data = []
        min_rate = 100.0
        for row in bottleneck_rows:
            step_total = int(row.total)
            step_completed = int(row.completed or 0)
            rate = round(step_completed / step_total * 100, 1) if step_total > 0 else 0.0
            if rate < min_rate:
                min_rate = rate
            entry = {
                "step_name": row.step_name,
                "step_name_ar": row.step_name_ar,
                "step_order": int(row.step_order),
            }
            if step_total >= self.MIN_GROUP_SIZE:
                entry["total_assignments"] = step_total
                entry["completed"] = step_completed
                entry["completion_rate_pct"] = rate
            else:
                entry["note"] = "Details suppressed — fewer than 5 assignments (privacy threshold)."
                rate = None  # Don't use for bottleneck detection
            step_data.append(entry)

        # Mark bottlenecks (steps at the minimum completion rate, skip suppressed)
        for step in step_data:
            step_rate = step.get("completion_rate_pct")
            step["is_bottleneck"] = (step_rate == min_rate) if step_rate is not None and step_data else False

        # Query 4 — Overdue steps count
        now_utc = datetime.now(timezone.utc)
        overdue_q = (
            select(func.count(OnboardingStepAssignment.id))
            .join(
                OnboardingAssignment,
                OnboardingStepAssignment.assignment_id == OnboardingAssignment.id,
            )
            .where(
                OnboardingAssignment.tenant_id == self.tenant_id,
                OnboardingAssignment.status == OnboardingAssignmentStatus.in_progress,
                OnboardingStepAssignment.status.in_([
                    OnboardingStepStatus.pending,
                    OnboardingStepStatus.in_progress,
                ]),
                OnboardingStepAssignment.due_date < now_utc,
            )
        )
        overdue_result = await self.db.execute(overdue_q)
        overdue_steps = overdue_result.scalar() or 0

        # Department breakdown
        dept_breakdown_q = (
            select(
                Department.name.label("dept_name"),
                func.count(OnboardingAssignment.id).label("total"),
                func.sum(case(
                    (OnboardingAssignment.status == OnboardingAssignmentStatus.completed, 1),
                    else_=0,
                )).label("completed"),
                func.sum(case(
                    (OnboardingAssignment.status == OnboardingAssignmentStatus.in_progress, 1),
                    else_=0,
                )).label("in_progress"),
            )
            .join(Employee, OnboardingAssignment.employee_id == Employee.id)
            .join(Department, Employee.department_id == Department.id)
            .where(
                OnboardingAssignment.tenant_id == self.tenant_id,
                OnboardingAssignment.started_at >= cutoff,
            )
            .group_by(Department.id, Department.name)
        )
        if department_id:
            dept_breakdown_q = dept_breakdown_q.where(Employee.department_id == department_id)
        dept_bd_result = await self.db.execute(dept_breakdown_q)

        department_breakdown = []
        for row in dept_bd_result.all():
            dept_total = int(row.total)
            dept_completed = int(row.completed or 0)
            dept_in_progress = int(row.in_progress or 0)
            entry = {
                "department": row.dept_name,
                "total": dept_total,
            }
            if dept_total >= self.MIN_GROUP_SIZE:
                entry.update({
                    "completed": dept_completed,
                    "in_progress": dept_in_progress,
                    "completion_rate_pct": round(dept_completed / dept_total * 100, 1) if dept_total > 0 else 0.0,
                })
            else:
                entry["note"] = "Details suppressed — fewer than 5 assignments (privacy threshold)."
            department_breakdown.append(entry)

        return json.dumps({
            "period_months": months,
            "summary": {
                "total_assignments": total_assignments,
                "completed": completed,
                "in_progress": in_progress,
                "cancelled": cancelled,
                "completion_rate_pct": completion_rate,
            },
            "completion_time": completion_time,
            "overdue_steps": overdue_steps,
            "bottleneck_steps": step_data,
            "department_breakdown": department_breakdown,
        })

    # ──────────────────────────────────────────────────────────────
    # Tool 12: Payroll Summary (A2-05)
    # ──────────────────────────────────────────────────────────────

    async def _get_payroll_summary(self, tool_input: dict) -> str:
        department_id = tool_input.get("department_id")
        months = max(1, min(24, tool_input.get("months", 6)))
        today = datetime.now(_RIYADH_TZ).date()
        start_date = today - timedelta(days=months * 30)
        start_year, start_month = start_date.year, start_date.month

        # Year-month range filter
        payslip_ym = Payslip.year * 100 + Payslip.month
        start_ym = start_year * 100 + start_month
        end_ym = today.year * 100 + today.month

        dept_join = []
        dept_where = []
        if department_id:
            dept_join = [(Employee, Payslip.employee_id == Employee.id)]
            dept_where = [Employee.department_id == department_id]

        # Query 1 — Aggregate totals
        total_q = (
            select(
                func.coalesce(func.sum(Payslip.gross_salary), 0).label("total_gross"),
                func.coalesce(func.sum(Payslip.total_deductions), 0).label("total_deductions"),
                func.coalesce(func.sum(Payslip.net_salary), 0).label("total_net"),
                func.coalesce(func.sum(Payslip.basic_salary), 0).label("total_basic"),
                func.coalesce(func.sum(Payslip.housing_allowance), 0).label("total_housing"),
                func.coalesce(func.sum(Payslip.transport_allowance), 0).label("total_transport"),
                func.coalesce(func.sum(Payslip.other_allowances), 0).label("total_other_allow"),
                func.coalesce(func.sum(Payslip.gosi_employee), 0).label("total_gosi_employee"),
                func.coalesce(func.sum(Payslip.absent_deduction), 0).label("total_absent_ded"),
                func.coalesce(func.sum(Payslip.other_deductions), 0).label("total_other_ded"),
                func.count(func.distinct(Payslip.employee_id)).label("unique_employees"),
                func.count(Payslip.id).label("payslip_count"),
            )
            .where(
                Payslip.tenant_id == self.tenant_id,
                payslip_ym >= start_ym,
                payslip_ym <= end_ym,
            )
        )
        if department_id:
            total_q = total_q.join(
                Employee, Payslip.employee_id == Employee.id
            ).where(Employee.department_id == department_id)
        total_result = await self.db.execute(total_q)
        t = total_result.one()

        total_gross = int(t.total_gross)
        total_deductions = int(t.total_deductions)
        total_net = int(t.total_net)
        total_basic = int(t.total_basic)
        total_housing = int(t.total_housing)
        total_transport = int(t.total_transport)
        total_other_allow = int(t.total_other_allow)
        total_gosi_employee = int(t.total_gosi_employee)
        total_absent_ded = int(t.total_absent_ded)
        total_other_ded = int(t.total_other_ded)
        unique_employees = int(t.unique_employees)
        payslip_count = int(t.payslip_count)

        if payslip_count == 0:
            return json.dumps({
                "message": f"No payroll data found for the last {months} months.",
                "period_months": months,
                "totals": {
                    "gross_salary_sar": 0,
                    "net_salary_sar": 0,
                    "total_deductions_sar": 0,
                    "unique_employees": 0,
                    "payslip_count": 0,
                },
            })

        # GOSI employer estimate: 12% for Saudis, 2% for non-Saudis (work hazard only)
        gosi_saudi_q = (
            select(
                func.coalesce(func.sum(Payslip.basic_salary), 0).label("saudi_basic"),
            )
            .join(Employee, Payslip.employee_id == Employee.id)
            .where(
                Payslip.tenant_id == self.tenant_id,
                payslip_ym >= start_ym,
                payslip_ym <= end_ym,
                Employee.is_saudi == True,
            )
        )
        if department_id:
            gosi_saudi_q = gosi_saudi_q.where(Employee.department_id == department_id)
        gosi_result = await self.db.execute(gosi_saudi_q)
        saudi_basic = int(gosi_result.scalar_one())
        non_saudi_basic = total_basic - saudi_basic
        gosi_employer_estimate = round(saudi_basic * 0.12) + round(non_saudi_basic * 0.02)
        gosi_total = total_gosi_employee + gosi_employer_estimate

        # Query 2 — Monthly trend
        monthly_q = (
            select(
                Payslip.year,
                Payslip.month,
                func.sum(Payslip.gross_salary).label("gross"),
                func.sum(Payslip.net_salary).label("net"),
                func.sum(Payslip.total_deductions).label("deductions"),
                func.count(func.distinct(Payslip.employee_id)).label("headcount"),
            )
            .where(
                Payslip.tenant_id == self.tenant_id,
                payslip_ym >= start_ym,
                payslip_ym <= end_ym,
            )
            .group_by(Payslip.year, Payslip.month)
            .order_by(Payslip.year, Payslip.month)
        )
        if department_id:
            monthly_q = monthly_q.join(
                Employee, Payslip.employee_id == Employee.id
            ).where(Employee.department_id == department_id)
        monthly_result = await self.db.execute(monthly_q)

        monthly_trend = []
        for row in monthly_result.all():
            monthly_trend.append({
                "year": int(row.year),
                "month": int(row.month),
                "month_name": self.MONTH_NAMES.get(int(row.month), ""),
                "gross_sar": int(row.gross),
                "net_sar": int(row.net),
                "deductions_sar": int(row.deductions),
                "headcount": int(row.headcount),
            })

        # Query 3 — Department comparison (k-anonymity enforced)
        dept_q = (
            select(
                Department.name.label("dept_name"),
                Department.id.label("dept_id"),
                func.sum(Payslip.gross_salary).label("gross"),
                func.sum(Payslip.net_salary).label("net"),
                func.sum(Payslip.gosi_employee).label("gosi_employee"),
                func.count(func.distinct(Payslip.employee_id)).label("headcount"),
            )
            .join(Employee, Payslip.employee_id == Employee.id)
            .join(Department, Employee.department_id == Department.id)
            .where(
                Payslip.tenant_id == self.tenant_id,
                payslip_ym >= start_ym,
                payslip_ym <= end_ym,
            )
            .group_by(Department.id, Department.name)
        )
        if department_id:
            dept_q = dept_q.where(Employee.department_id == department_id)
        dept_result = await self.db.execute(dept_q)

        department_comparison = []
        for row in dept_result.all():
            headcount = int(row.headcount)
            entry = {
                "department": row.dept_name,
                "department_id": str(row.dept_id),
            }
            if headcount >= self.MIN_GROUP_SIZE:
                gross = int(row.gross)
                entry.update({
                    "gross_sar": gross,
                    "net_sar": int(row.net),
                    "gosi_employee_sar": int(row.gosi_employee),
                    "headcount": headcount,
                    "avg_gross_per_employee_sar": round(gross / headcount) if headcount > 0 else 0,
                })
            else:
                entry.update({
                    "headcount": headcount,
                    "note": "Suppressed — fewer than 5 employees (privacy threshold).",
                })
            department_comparison.append(entry)

        # k-anonymity on org-level totals
        suppress_totals = unique_employees < self.MIN_GROUP_SIZE
        if suppress_totals:
            totals_block = {
                "unique_employees": unique_employees,
                "payslip_count": payslip_count,
                "note": "Salary totals suppressed — fewer than 5 employees (privacy threshold).",
            }
            gosi_block = {"note": "Suppressed — fewer than 5 employees."}
            deductions_block = {"note": "Suppressed — fewer than 5 employees."}
        else:
            totals_block = {
                "gross_salary_sar": total_gross,
                "net_salary_sar": total_net,
                "total_deductions_sar": total_deductions,
                "basic_salary_sar": total_basic,
                "housing_allowance_sar": total_housing,
                "transport_allowance_sar": total_transport,
                "other_allowances_sar": total_other_allow,
                "unique_employees": unique_employees,
                "payslip_count": payslip_count,
            }
            gosi_block = {
                "employee_contribution_sar": total_gosi_employee,
                "employer_contribution_estimated_sar": gosi_employer_estimate,
                "total_gosi_estimated_sar": gosi_total,
                "note": "Employer: 12% Saudi + 2% non-Saudi of basic salary (estimated).",
            }
            deductions_block = {
                "gosi_employee_sar": total_gosi_employee,
                "absent_deduction_sar": total_absent_ded,
                "other_deductions_sar": total_other_ded,
            }

        return json.dumps({
            "period_months": months,
            "totals": totals_block,
            "gosi_breakdown": gosi_block,
            "deductions_breakdown": deductions_block,
            "monthly_trend": monthly_trend,
            "department_comparison": department_comparison,
            "privacy_note": "Aggregated payroll data. Departments with fewer than 5 employees have details suppressed.",
        })

    # ──────────────────────────────────────────────────────────────
    # Tool 13: Attrition Risk Prediction (A3-01)
    # ──────────────────────────────────────────────────────────────

    RISK_THRESHOLD_MIN = {"high": 70, "medium": 40, "low": 0}

    def _compute_risk_score(
        self,
        hire_date: date,
        salary_sar: int | None,
        dept_median_salary: float,
        dept_p25_salary: float,
        recent_sick_days: int,
        prior_sick_days: int,
        recent_attendance_issues: int,
        prior_attendance_issues: int,
        last_updated: datetime,
        probation_end_date: date | None,
    ) -> tuple[float, list[str]]:
        """Returns (score 0-100, list of contributing factor names)."""
        factors: dict[str, float] = {}
        today = datetime.now(_RIYADH_TZ).date()

        # 1. Tenure risk (30%)
        tenure_days = (today - hire_date).days
        if tenure_days < 365:
            factors["short_tenure"] = 75.0
        elif tenure_days > 5 * 365:
            factors["long_tenure_stagnation"] = 60.0
        else:
            factors["tenure"] = max(0, 50 - (tenure_days / 365) * 5)
        tenure_score = list(factors.values())[-1]

        # 2. Salary position (25%)
        if salary_sar and dept_median_salary > 0:
            if salary_sar <= dept_p25_salary:
                salary_score = 80.0
                factors["below_25pct_salary"] = salary_score
            elif salary_sar < dept_median_salary:
                salary_score = 50.0
                factors["below_median_salary"] = salary_score
            else:
                salary_score = 20.0
        else:
            salary_score = 50.0  # Neutral when data missing

        # 3. Leave pattern (20%) -- 2x spike detection
        prior_monthly_avg = prior_sick_days / 9.0 if prior_sick_days > 0 else 0
        recent_monthly_avg = recent_sick_days / 3.0
        if prior_monthly_avg > 0 and recent_monthly_avg >= 2 * prior_monthly_avg:
            leave_score = 80.0
            factors["sick_leave_spike"] = leave_score
        elif recent_sick_days > 5:
            leave_score = 50.0
        else:
            leave_score = 20.0

        # 4. Attendance trend (15%)
        prior_monthly_att = prior_attendance_issues / 9.0 if prior_attendance_issues > 0 else 0
        recent_monthly_att = recent_attendance_issues / 3.0
        if prior_monthly_att > 0 and recent_monthly_att >= 1.5 * prior_monthly_att:
            attend_score = 75.0
            factors["attendance_deterioration"] = attend_score
        elif recent_attendance_issues > 6:
            attend_score = 50.0
        else:
            attend_score = 20.0

        # 5. Stagnation (10%)
        update_date = last_updated.date() if isinstance(last_updated, datetime) else last_updated
        months_since_update = (today - update_date).days / 30
        if months_since_update >= 24:
            stag_score = 80.0
            factors["no_change_24m"] = stag_score
        elif months_since_update >= 12:
            stag_score = 50.0
        else:
            stag_score = 20.0

        # Weighted composite
        score = (
            tenure_score * 0.30
            + salary_score * 0.25
            + leave_score * 0.20
            + attend_score * 0.15
            + stag_score * 0.10
        )

        top_factors = sorted(factors.keys(), key=lambda k: factors[k], reverse=True)[:2]
        return round(score, 1), top_factors

    @staticmethod
    def _risk_tier(score: float) -> str:
        if score >= 70:
            return "high"
        elif score >= 40:
            return "medium"
        return "low"

    async def _predict_attrition_risk(self, tool_input: dict) -> str:
        department_id = tool_input.get("department_id")
        include_individuals = tool_input.get("include_individuals", False)
        risk_threshold = tool_input.get("risk_threshold")
        threshold_min = self.RISK_THRESHOLD_MIN.get(risk_threshold, 0) if risk_threshold else 0

        today = datetime.now(_RIYADH_TZ).date()
        twelve_months_ago = today - timedelta(days=365)
        three_months_ago = today - timedelta(days=90)

        active_statuses = [EmployeeStatus.active, EmployeeStatus.onboarding, EmployeeStatus.on_leave]

        # Query 1 -- Active employees with department
        emp_q = (
            select(
                Employee.id,
                Employee.department_id,
                Employee.hire_date,
                Employee.salary_sar,
                Employee.is_saudi,
                Employee.updated_at,
                Employee.manager_id,
                Employee.probation_end_date,
                Department.name.label("dept_name"),
            )
            .join(Department, Employee.department_id == Department.id)
            .where(
                Employee.tenant_id == self.tenant_id,
                Employee.status.in_(active_statuses),
            )
        )
        if department_id:
            emp_q = emp_q.where(Employee.department_id == department_id)
        emp_result = await self.db.execute(emp_q)
        employees = emp_result.all()

        if not employees:
            return json.dumps({"message": "No employees found for the given criteria."})

        # Query 2 -- Sick leave counts per employee (last 12 months, approved only)
        sick_leave_q = (
            select(
                LeaveRequest.employee_id,
                func.coalesce(func.sum(
                    case(
                        (LeaveRequest.start_date >= three_months_ago, LeaveRequest.business_days),
                        else_=0,
                    )
                ), 0).label("recent_sick_days"),
                func.coalesce(func.sum(
                    case(
                        (LeaveRequest.start_date < three_months_ago, LeaveRequest.business_days),
                        else_=0,
                    )
                ), 0).label("prior_sick_days"),
            )
            .join(Employee, LeaveRequest.employee_id == Employee.id)
            .where(
                Employee.tenant_id == self.tenant_id,
                LeaveRequest.leave_type == LeaveType.sick,
                LeaveRequest.status == LeaveStatus.approved,
                LeaveRequest.start_date >= twelve_months_ago,
            )
            .group_by(LeaveRequest.employee_id)
        )
        sick_result = await self.db.execute(sick_leave_q)
        sick_map = {
            row.employee_id: (int(row.recent_sick_days), int(row.prior_sick_days))
            for row in sick_result.all()
        }

        # Query 3 -- Attendance trend per employee (last 12 months, late + absent)
        attendance_q = (
            select(
                AttendanceRecord.employee_id,
                func.coalesce(func.sum(
                    case(
                        (
                            (AttendanceRecord.date >= three_months_ago) &
                            (AttendanceRecord.status.in_([AttendanceStatus.late, AttendanceStatus.absent])),
                            1,
                        ),
                        else_=0,
                    )
                ), 0).label("recent_issues"),
                func.coalesce(func.sum(
                    case(
                        (
                            (AttendanceRecord.date < three_months_ago) &
                            (AttendanceRecord.date >= twelve_months_ago) &
                            (AttendanceRecord.status.in_([AttendanceStatus.late, AttendanceStatus.absent])),
                            1,
                        ),
                        else_=0,
                    )
                ), 0).label("prior_issues"),
            )
            .where(
                AttendanceRecord.tenant_id == self.tenant_id,
                AttendanceRecord.date >= twelve_months_ago,
            )
            .group_by(AttendanceRecord.employee_id)
        )
        att_result = await self.db.execute(attendance_q)
        att_map = {
            row.employee_id: (int(row.recent_issues), int(row.prior_issues))
            for row in att_result.all()
        }

        # Compute department salary stats for percentile calculations
        dept_salaries: dict[str, list[int]] = {}
        for emp in employees:
            if emp.salary_sar is not None:
                dept_key = str(emp.department_id)
                dept_salaries.setdefault(dept_key, []).append(emp.salary_sar)

        dept_stats: dict[str, tuple[float, float]] = {}  # dept_id -> (median, p25)
        for dept_key, salaries in dept_salaries.items():
            sorted_s = sorted(salaries)
            n = len(sorted_s)
            median = sorted_s[n // 2] if n % 2 == 1 else (sorted_s[n // 2 - 1] + sorted_s[n // 2]) / 2.0
            p25_idx = max(0, n // 4)
            p25 = float(sorted_s[p25_idx])
            dept_stats[dept_key] = (median, p25)

        # Score each employee
        emp_scores: list[dict] = []
        probation_count = 0

        for emp in employees:
            dept_key = str(emp.department_id)
            d_median, d_p25 = dept_stats.get(dept_key, (0.0, 0.0))

            # New hire (<30 days): skip leave/attendance signals
            is_new_hire = (today - emp.hire_date).days < 30
            is_probation = (
                emp.probation_end_date is not None and emp.probation_end_date > today
            )
            if is_probation:
                probation_count += 1

            if is_new_hire:
                # Simplified scoring for new hires
                salary_score = 50.0
                if emp.salary_sar and d_median > 0:
                    if emp.salary_sar <= d_p25:
                        salary_score = 80.0
                    elif emp.salary_sar < d_median:
                        salary_score = 50.0
                    else:
                        salary_score = 20.0
                score = salary_score * 0.25 + 50.0 * 0.75  # Neutral on other factors
                score = round(score, 1)
                top_factors = ["new_hire"]
            else:
                sick_data = sick_map.get(emp.id, (0, 0))
                att_data = att_map.get(emp.id, (0, 0))

                score, top_factors = self._compute_risk_score(
                    hire_date=emp.hire_date,
                    salary_sar=emp.salary_sar,
                    dept_median_salary=d_median,
                    dept_p25_salary=d_p25,
                    recent_sick_days=sick_data[0],
                    prior_sick_days=sick_data[1],
                    recent_attendance_issues=att_data[0],
                    prior_attendance_issues=att_data[1],
                    last_updated=emp.updated_at,
                    probation_end_date=emp.probation_end_date,
                )

            emp_scores.append({
                "employee_id": str(emp.id),
                "department_id": dept_key,
                "department_name": emp.dept_name,
                "risk_score": score,
                "risk_tier": self._risk_tier(score),
                "top_factors": top_factors,
                "is_probation": is_probation,
                "is_new_hire": is_new_hire,
            })

        # Aggregate by department
        dept_agg: dict[str, dict] = {}
        for es in emp_scores:
            dk = es["department_id"]
            if dk not in dept_agg:
                dept_agg[dk] = {
                    "department_name": es["department_name"],
                    "department_id": dk,
                    "scores": [],
                    "factor_counts": {},
                }
            dept_agg[dk]["scores"].append(es["risk_score"])
            for f in es["top_factors"]:
                dept_agg[dk]["factor_counts"][f] = dept_agg[dk]["factor_counts"].get(f, 0) + 1

        departments_out = []
        too_small = []
        for dk, agg in dept_agg.items():
            headcount = len(agg["scores"])
            if headcount < self.MIN_GROUP_SIZE:
                too_small.append(dk)
                continue
            avg_score = round(sum(agg["scores"]) / headcount, 1)
            tier = self._risk_tier(avg_score)

            # Apply threshold filter
            if avg_score < threshold_min:
                continue

            high_count = sum(1 for s in agg["scores"] if s >= 70)
            medium_count = sum(1 for s in agg["scores"] if 40 <= s < 70)
            low_count = sum(1 for s in agg["scores"] if s < 40)

            top_dept_factors = sorted(
                agg["factor_counts"].keys(),
                key=lambda k: agg["factor_counts"][k],
                reverse=True,
            )[:2]

            departments_out.append({
                "department_name": agg["department_name"],
                "department_id": dk,
                "headcount": headcount,
                "avg_risk_score": avg_score,
                "risk_tier": tier,
                "high_risk_count": high_count,
                "medium_risk_count": medium_count,
                "low_risk_count": low_count,
                "top_risk_factors": top_dept_factors,
            })

        departments_out.sort(key=lambda d: d["avg_risk_score"], reverse=True)

        # Org-level summary
        all_scores = [es["risk_score"] for es in emp_scores]
        org_avg = round(sum(all_scores) / len(all_scores), 1) if all_scores else 0.0
        total_high = sum(1 for s in all_scores if s >= 70)
        total_medium = sum(1 for s in all_scores if 40 <= s < 70)
        total_low = sum(1 for s in all_scores if s < 40)

        result: dict = {
            "departments": departments_out,
            "too_small_to_report": too_small,
            "summary": {
                "org_avg_risk_score": org_avg,
                "org_risk_tier": self._risk_tier(org_avg),
                "total_high_risk": total_high,
                "total_medium_risk": total_medium,
                "total_low_risk": total_low,
                "departments_analyzed": len(departments_out),
                "departments_excluded_privacy": len(too_small),
            },
            "saudi_context": {
                "probation_employees_flagged": probation_count,
                "note": (
                    "Employees in probation period (first 90 days per Saudi Labor Law "
                    "Article 53) have different termination dynamics and are flagged separately."
                ),
            },
        }

        # Include individuals if requested — requires HR/manager role
        # TODO: When RBAC is implemented (Sprint 8+), verify employee_role before returning individual data
        # For now, individual data is only exposed via the tool parameter which the LLM controls
        if include_individuals and len(emp_scores) >= self.MIN_GROUP_SIZE:
            individuals = []
            for es in emp_scores:
                if es["risk_score"] < threshold_min:
                    continue
                individuals.append({
                    "employee_id": es["employee_id"],
                    "department_name": es["department_name"],
                    "risk_score": es["risk_score"],
                    "risk_tier": es["risk_tier"],
                    "factors": {f: 1.0 for f in es["top_factors"]},
                    "is_probation": es["is_probation"],
                })
            individuals.sort(key=lambda i: i["risk_score"], reverse=True)
            result["individuals"] = individuals

        return json.dumps(result)

    # ──────────────────────────────────────────────────────────────
    # Tool 14: Budget Forecasting (A3-02)
    # ──────────────────────────────────────────────────────────────

    GROWTH_RATES = {
        "flat": 0.0,
        "moderate": 0.05,
        "aggressive": 0.10,
    }

    async def _forecast_budget(self, tool_input: dict) -> str:
        department_id = tool_input.get("department_id")
        horizon = tool_input.get("horizon_months", 6)
        if horizon not in (3, 6, 12):
            horizon = 6
        growth_scenario = tool_input.get("growth_scenario")
        custom_growth_pct = tool_input.get("custom_growth_pct")

        # Validate custom growth
        if growth_scenario == "custom":
            if custom_growth_pct is None:
                return json.dumps({"error": "custom_growth_pct is required when growth_scenario is 'custom'."})
            if custom_growth_pct < 0:
                return json.dumps({"error": "Negative growth rate is not supported. Use flat (0%) for no-growth projection."})

        active_statuses = [EmployeeStatus.active, EmployeeStatus.onboarding, EmployeeStatus.on_leave]

        # Query 1 -- Current payroll baseline
        baseline_q = (
            select(
                func.count(Employee.id).label("headcount"),
                func.coalesce(func.sum(Employee.salary_sar), 0).label("total_monthly_salary"),
                func.coalesce(
                    func.sum(case((Employee.is_saudi == True, Employee.salary_sar), else_=0)), 0
                ).label("saudi_salary_total"),
                func.coalesce(
                    func.sum(case((Employee.is_saudi == False, Employee.salary_sar), else_=0)), 0
                ).label("non_saudi_salary_total"),
                # GOSI: sum min(salary, ceiling) per employee for correct per-employee capping
                func.coalesce(
                    func.sum(case((Employee.is_saudi == True, func.least(Employee.salary_sar, self.GOSI_SALARY_CEILING_SAR)), else_=0)), 0
                ).label("saudi_gosi_base"),
                func.coalesce(
                    func.sum(case((Employee.is_saudi == False, func.least(Employee.salary_sar, self.GOSI_SALARY_CEILING_SAR)), else_=0)), 0
                ).label("non_saudi_gosi_base"),
                func.coalesce(
                    func.sum(case((Employee.is_saudi == True, 1), else_=0)), 0
                ).label("saudi_count"),
                func.coalesce(
                    func.sum(case((Employee.is_saudi == False, 1), else_=0)), 0
                ).label("non_saudi_count"),
            )
            .where(
                Employee.tenant_id == self.tenant_id,
                Employee.status.in_(active_statuses),
                Employee.salary_sar.isnot(None),
            )
        )
        if department_id:
            baseline_q = baseline_q.where(Employee.department_id == department_id)
        baseline_result = await self.db.execute(baseline_q)
        row = baseline_result.one()

        headcount = int(row.headcount)
        total_monthly_salary = int(row.total_monthly_salary)
        saudi_salary_total = int(row.saudi_salary_total)
        non_saudi_salary_total = int(row.non_saudi_salary_total)
        saudi_count = int(row.saudi_count)
        non_saudi_count = int(row.non_saudi_count)

        if headcount == 0:
            return json.dumps({"message": "No active employees with salary data found."})

        # k-anonymity check for department filter
        if department_id and headcount < self.MIN_GROUP_SIZE:
            return json.dumps({"error": "department_too_small"})

        # Count employees with missing salary (for warning)
        missing_salary_q = (
            select(func.count(Employee.id))
            .where(
                Employee.tenant_id == self.tenant_id,
                Employee.status.in_(active_statuses),
                Employee.salary_sar.is_(None),
            )
        )
        if department_id:
            missing_salary_q = missing_salary_q.where(Employee.department_id == department_id)
        missing_result = await self.db.execute(missing_salary_q)
        employees_missing_salary = missing_result.scalar() or 0

        # GOSI calculation — per-employee ceiling applied in SQL via func.least()
        saudi_gosi_base = int(row.saudi_gosi_base)
        non_saudi_gosi_base = int(row.non_saudi_gosi_base)

        gosi_saudi = saudi_gosi_base * self.GOSI_EMPLOYER_SAUDI_PCT
        gosi_non_saudi = non_saudi_gosi_base * self.GOSI_EMPLOYER_NON_SAUDI_PCT
        monthly_gosi = round(gosi_saudi + gosi_non_saudi)

        baseline_monthly_cost = total_monthly_salary + monthly_gosi

        saudi_pct = round(saudi_count / headcount * 100, 1) if headcount > 0 else 0.0

        current_baseline = {
            "headcount": headcount,
            "saudi_count": saudi_count,
            "non_saudi_count": non_saudi_count,
            "saudi_pct": saudi_pct,
            "monthly_payroll_sar": total_monthly_salary,
            "monthly_gosi_employer_sar": monthly_gosi,
            "monthly_total_cost_sar": baseline_monthly_cost,
        }
        if employees_missing_salary > 0:
            current_baseline["employees_missing_salary"] = employees_missing_salary

        # Build scenarios
        scenarios_to_compute: dict[str, float] = {}
        if growth_scenario and growth_scenario != "custom":
            rate = self.GROWTH_RATES.get(growth_scenario, 0.0)
            scenarios_to_compute[growth_scenario] = rate
        elif growth_scenario == "custom":
            scenarios_to_compute["custom"] = custom_growth_pct / 100.0
        else:
            # Return all three
            scenarios_to_compute = dict(self.GROWTH_RATES)

        today = datetime.now(_RIYADH_TZ).date()
        scenarios_out: dict[str, dict] = {}

        for scenario_name, annual_rate in scenarios_to_compute.items():
            monthly_rate = annual_rate / 12
            forecast = []
            total_period_cost = 0

            for m in range(1, horizon + 1):
                factor = (1 + monthly_rate) ** m
                month_date = today + timedelta(days=m * 30)
                proj_headcount = round(headcount * factor)
                proj_payroll = round(total_monthly_salary * factor)
                proj_gosi = round(monthly_gosi * factor)
                proj_total = round(baseline_monthly_cost * factor)
                total_period_cost += proj_total

                forecast.append({
                    "month_number": m,
                    "month_label": month_date.strftime("%b %Y"),
                    "projected_headcount": proj_headcount,
                    "projected_monthly_payroll_sar": proj_payroll,
                    "projected_gosi_sar": proj_gosi,
                    "projected_total_sar": proj_total,
                })

            end_cost = forecast[-1]["projected_total_sar"]
            cost_increase_pct = round(
                (end_cost - baseline_monthly_cost) / baseline_monthly_cost * 100, 1
            ) if baseline_monthly_cost > 0 else 0.0

            scenarios_out[scenario_name] = {
                "growth_pct_annual": round(annual_rate * 100, 2),
                "forecast": forecast,
                "summary": {
                    "end_monthly_cost_sar": end_cost,
                    "total_period_cost_sar": total_period_cost,
                    "cost_increase_pct": cost_increase_pct,
                },
            }

        # Nitaqat note
        nitaqat_note = (
            f"Current Saudization is {saudi_pct}%. "
            "If hiring under growth scenarios, maintaining this ratio requires "
            "proportional Saudi hires to meet Nitaqat requirements."
        )

        return json.dumps({
            "current_baseline": current_baseline,
            "scenarios": scenarios_out,
            "nitaqat_note": nitaqat_note,
        })

    # ──────────────────────────────────────────────────────────────
    # Tool 15: GOSI Compliance Audit (A3-03)
    # ──────────────────────────────────────────────────────────────

    async def _audit_gosi_compliance(self, tool_input: dict) -> str:
        department_id = tool_input.get("department_id")
        month_str = tool_input.get("month")
        tolerance_pct = tool_input.get("tolerance_pct", 1.0)

        # Resolve target month
        if month_str:
            try:
                parts = month_str.split("-")
                target_year = int(parts[0])
                target_month = int(parts[1])
                if target_month < 1 or target_month > 12:
                    return json.dumps({"error": "Invalid month format. Use YYYY-MM (e.g. 2026-03)."})
            except (ValueError, IndexError):
                return json.dumps({"error": "Invalid month format. Use YYYY-MM (e.g. 2026-03)."})
        else:
            latest_q = (
                select(Payslip.year, Payslip.month)
                .where(Payslip.tenant_id == self.tenant_id)
                .order_by(Payslip.year.desc(), Payslip.month.desc())
                .limit(1)
            )
            latest_result = await self.db.execute(latest_q)
            latest_row = latest_result.one_or_none()
            if not latest_row:
                return json.dumps({"message": "No payslip data found. Ensure payroll has been processed."})
            target_year = latest_row.year
            target_month = latest_row.month

        # Query payslips for the target month
        audit_q = (
            select(
                Payslip.id,
                Payslip.employee_id,
                Payslip.basic_salary,
                Payslip.gosi_employee,
                Employee.is_saudi,
                Employee.salary_sar,
                Employee.department_id,
                Department.name.label("dept_name"),
            )
            .join(Employee, Payslip.employee_id == Employee.id)
            .join(Department, Employee.department_id == Department.id)
            .where(
                Payslip.tenant_id == self.tenant_id,
                Payslip.year == target_year,
                Payslip.month == target_month,
            )
        )
        if department_id:
            audit_q = audit_q.where(Employee.department_id == department_id)
        audit_result = await self.db.execute(audit_q)
        payslip_rows = audit_result.all()

        if not payslip_rows:
            month_label = f"{target_year}-{target_month:02d}"
            return json.dumps({
                "message": f"No payslip data found for {month_label}. Ensure payroll has been processed."
            })

        # Audit each payslip
        compliant_count = 0
        minor_count = 0
        major_count = 0
        missing_count = 0
        discrepancies = []
        total_expected_employer_gosi = 0
        total_actual_employee_gosi = 0
        total_expected_employee_gosi = 0
        total_variance = 0

        for row in payslip_rows:
            gosi_eligible_salary = min(row.basic_salary, self.GOSI_SALARY_CEILING_SAR)

            if row.is_saudi:
                expected_employee_gosi = round(gosi_eligible_salary * self.GOSI_EMPLOYEE_SAUDI_PCT)
                expected_employer_gosi = round(gosi_eligible_salary * self.GOSI_EMPLOYER_SAUDI_PCT)
            else:
                expected_employee_gosi = 0
                expected_employer_gosi = round(gosi_eligible_salary * self.GOSI_EMPLOYER_NON_SAUDI_PCT)

            total_expected_employer_gosi += expected_employer_gosi
            total_expected_employee_gosi += expected_employee_gosi
            actual_employee_gosi = row.gosi_employee

            if actual_employee_gosi is not None:
                total_actual_employee_gosi += actual_employee_gosi

            # Check severity
            if actual_employee_gosi is None:
                severity = "missing_gosi_data"
                missing_count += 1
                variance = expected_employee_gosi
                variance_pct = 100.0
            elif expected_employee_gosi > 0:
                variance = abs(actual_employee_gosi - expected_employee_gosi)
                variance_pct = round((variance / expected_employee_gosi) * 100, 1)
                if variance_pct > tolerance_pct * 2:
                    severity = "major"
                    major_count += 1
                elif variance_pct > tolerance_pct:
                    severity = "minor"
                    minor_count += 1
                else:
                    severity = "compliant"
                    compliant_count += 1
            elif actual_employee_gosi > 0:
                # Non-Saudi with unexpected deduction
                variance = actual_employee_gosi
                variance_pct = 100.0
                severity = "major"
                major_count += 1
            else:
                severity = "compliant"
                compliant_count += 1
                variance = 0
                variance_pct = 0.0

            total_variance += variance

            if severity != "compliant":
                # Privacy: no individual employee IDs or salaries — aggregate by department
                discrepancies.append({
                    "department_name": row.dept_name,
                    "nationality_type": "saudi" if row.is_saudi else "non_saudi",
                    "variance_sar": variance,
                    "severity": severity,
                })

        month_label = f"{target_year}-{target_month:02d}"

        return json.dumps({
            "audit_month": month_label,
            "summary": {
                "total_employees_audited": len(payslip_rows),
                "compliant_count": compliant_count,
                "minor_discrepancy_count": minor_count,
                "major_discrepancy_count": major_count,
                "missing_gosi_data_count": missing_count,
                "total_expected_employer_gosi_sar": total_expected_employer_gosi,
                "total_actual_employee_gosi_sar": total_actual_employee_gosi,
                "total_expected_employee_gosi_sar": total_expected_employee_gosi,
                "total_variance_sar": total_variance,
            },
            "discrepancies": discrepancies,
            "gosi_rates_applied": {
                "saudi_employer_pct": 12.0,
                "saudi_employee_pct": 10.0,
                "non_saudi_employer_pct": 2.0,
                "non_saudi_employee_pct": 0.0,
                "salary_ceiling_sar": self.GOSI_SALARY_CEILING_SAR,
            },
            "notes": [
                "Employer GOSI share is estimated (no gosi_employer column in payslips). Actual billing may vary.",
                f"GOSI salary ceiling of SAR {self.GOSI_SALARY_CEILING_SAR:,} applied to contributions above this threshold.",
            ],
        })

    # ──────────────────────────────────────────────────────────────
    # Tool 16: Policy Acknowledgment Tracking (A3-04)
    # ──────────────────────────────────────────────────────────────

    MANDATORY_POLICY_CATEGORIES = {PolicyCategory.safety, PolicyCategory.conduct}

    async def _get_policy_acknowledgments(self, tool_input: dict) -> str:
        policy_id_str = tool_input.get("policy_id")
        department_id = tool_input.get("department_id")
        category_str = tool_input.get("category")

        # Validate policy_id if provided
        policy_id = None
        if policy_id_str:
            try:
                policy_id = UUID(policy_id_str)
            except (ValueError, AttributeError):
                return json.dumps({"error": "Invalid policy_id — must be a valid UUID."})

        today = datetime.now(_RIYADH_TZ).date()
        active_statuses = [EmployeeStatus.active, EmployeeStatus.onboarding, EmployeeStatus.on_leave]

        # Query 1 -- Published policies in scope
        policy_q = (
            select(HRPolicy)
            .where(
                HRPolicy.tenant_id == self.tenant_id,
                HRPolicy.status == PolicyStatus.published,
                HRPolicy.effective_date <= today,
            )
        )
        if policy_id:
            policy_q = policy_q.where(HRPolicy.id == policy_id)
        if category_str:
            try:
                cat_enum = PolicyCategory(category_str)
                policy_q = policy_q.where(HRPolicy.category == cat_enum)
            except ValueError:
                return json.dumps({
                    "error": f"Unknown category '{category_str}'.",
                    "valid_categories": [c.value for c in PolicyCategory],
                })
        policy_result = await self.db.execute(policy_q)
        policies = policy_result.scalars().all()

        if not policies:
            return json.dumps({"message": "No published policies found matching the criteria."})

        # Query 2 -- Active employee count by department
        emp_count_q = (
            select(
                Employee.department_id,
                func.count(Employee.id).label("active_count"),
            )
            .where(
                Employee.tenant_id == self.tenant_id,
                Employee.status.in_(active_statuses),
            )
            .group_by(Employee.department_id)
        )
        if department_id:
            emp_count_q = emp_count_q.where(Employee.department_id == department_id)
        emp_count_result = await self.db.execute(emp_count_q)
        dept_emp_counts = {row.department_id: int(row.active_count) for row in emp_count_result.all()}
        total_active = sum(dept_emp_counts.values())

        if total_active == 0:
            return json.dumps({"message": "No active employees found."})

        # Query 3 -- Acknowledgment counts per policy and department
        ack_q = (
            select(
                PolicyAcknowledgment.policy_id,
                Employee.department_id,
                func.count(PolicyAcknowledgment.id).label("ack_count"),
            )
            .join(Employee, PolicyAcknowledgment.employee_id == Employee.id)
            .where(
                PolicyAcknowledgment.tenant_id == self.tenant_id,
                Employee.status.in_(active_statuses),
            )
            .group_by(PolicyAcknowledgment.policy_id, Employee.department_id)
        )
        if department_id:
            ack_q = ack_q.where(Employee.department_id == department_id)
        ack_result = await self.db.execute(ack_q)

        # Build ack lookup: (policy_id, dept_id) -> count
        ack_map: dict[tuple, int] = {}
        for row in ack_result.all():
            ack_map[(row.policy_id, row.department_id)] = int(row.ack_count)

        # Get department names
        dept_name_q = select(Department.id, Department.name).where(Department.tenant_id == self.tenant_id)
        dept_name_result = await self.db.execute(dept_name_q)
        dept_names = {row.id: row.name for row in dept_name_result.all()}

        # Build policy-level results
        policies_out = []
        total_acks = 0
        total_possible = 0
        fully_compliant_count = 0
        critical_gaps = []

        for pol in policies:
            is_mandatory = pol.category in self.MANDATORY_POLICY_CATEGORIES
            # Sum acks across departments for this policy
            pol_ack_count = sum(
                count for (pid, did), count in ack_map.items() if pid == pol.id
            )
            not_acked = total_active - pol_ack_count
            compliance_rate = round(pol_ack_count / total_active * 100, 1) if total_active > 0 else 0.0

            total_acks += pol_ack_count
            total_possible += total_active

            if compliance_rate == 100.0:
                fully_compliant_count += 1

            if compliance_rate < 50.0:
                critical_gaps.append({
                    "title": pol.title,
                    "compliance_rate_pct": compliance_rate,
                    "category": pol.category.value,
                    "mandatory": is_mandatory,
                })

            policies_out.append({
                "policy_id": str(pol.id),
                "title": pol.title,
                "title_ar": pol.title_ar,
                "category": pol.category.value,
                "effective_date": pol.effective_date.isoformat(),
                "compliance_rate_pct": compliance_rate,
                "acknowledged_count": pol_ack_count,
                "not_acknowledged_count": not_acked,
                "mandatory": is_mandatory,
            })

        # Build department-level results with k-anonymity
        by_department = []
        other_dept_scores: list[float] = []
        other_dept_count = 0

        for dept_id_key, emp_count in dept_emp_counts.items():
            dept_name = dept_names.get(dept_id_key, "Unknown")

            if emp_count < self.MIN_GROUP_SIZE:
                # Group under "Other" for k-anonymity
                for pol in policies:
                    acks = ack_map.get((pol.id, dept_id_key), 0)
                    rate = round(acks / emp_count * 100, 1) if emp_count > 0 else 0.0
                    other_dept_scores.append(rate)
                other_dept_count += 1
                continue

            dept_policy_rates = []
            lowest_policy = None
            lowest_rate = 101.0

            for pol in policies:
                acks = ack_map.get((pol.id, dept_id_key), 0)
                rate = round(acks / emp_count * 100, 1) if emp_count > 0 else 0.0
                dept_policy_rates.append(rate)
                if rate < lowest_rate:
                    lowest_rate = rate
                    lowest_policy = {"title": pol.title, "compliance_rate_pct": rate}

            avg_rate = round(sum(dept_policy_rates) / len(dept_policy_rates), 1) if dept_policy_rates else 0.0

            by_department.append({
                "department_name": dept_name,
                "department_id": str(dept_id_key),
                "total_policies": len(policies),
                "avg_compliance_rate_pct": avg_rate,
                "lowest_compliance_policy": lowest_policy,
            })

        # Add "Other" group if any small departments
        if other_dept_count > 0 and other_dept_scores:
            avg_other = round(sum(other_dept_scores) / len(other_dept_scores), 1)
            by_department.append({
                "department_name": "Other (small departments)",
                "department_id": "grouped",
                "total_policies": len(policies),
                "avg_compliance_rate_pct": avg_other,
                "lowest_compliance_policy": None,
                "note": f"{other_dept_count} department(s) grouped for privacy (fewer than {self.MIN_GROUP_SIZE} employees).",
            })

        by_department.sort(key=lambda d: d["avg_compliance_rate_pct"])

        org_compliance = round(total_acks / total_possible * 100, 1) if total_possible > 0 else 0.0

        result: dict = {
            "policies": policies_out,
            "by_department": by_department,
            "summary": {
                "total_published_policies": len(policies),
                "org_wide_compliance_rate_pct": org_compliance,
                "fully_compliant_policies_count": fully_compliant_count,
                "critical_gaps": critical_gaps,
            },
            "saudi_context": {
                "mandatory_policy_categories": [c.value for c in self.MANDATORY_POLICY_CATEGORIES],
                "note": (
                    "Policies in 'safety' and 'conduct' categories are flagged as mandatory "
                    "per Saudi Labor Law Articles 121 and 98."
                ),
            },
        }

        # Query 4 -- Non-compliant employees (only when policy_id specified)
        if policy_id:
            acked_subq = (
                select(PolicyAcknowledgment.employee_id)
                .where(PolicyAcknowledgment.policy_id == policy_id)
            ).subquery()

            non_compliant_q = (
                select(Employee.id, Department.name.label("dept_name"))
                .join(Department, Employee.department_id == Department.id)
                .where(
                    Employee.tenant_id == self.tenant_id,
                    Employee.status.in_(active_statuses),
                    Employee.id.notin_(select(acked_subq.c.employee_id)),
                )
            )
            if department_id:
                non_compliant_q = non_compliant_q.where(Employee.department_id == department_id)
            nc_result = await self.db.execute(non_compliant_q)
            nc_rows = nc_result.all()

            # Privacy: only show individual non-compliant list if above k-anonymity threshold
            if len(nc_rows) >= self.MIN_GROUP_SIZE:
                result["non_compliant_employees"] = [
                    {"employee_id": str(row.id), "department_name": row.dept_name}
                    for row in nc_rows
                ]
            else:
                result["non_compliant_count"] = len(nc_rows)
                result["non_compliant_note"] = f"Individual list suppressed — fewer than {self.MIN_GROUP_SIZE} employees (privacy threshold)."

        return json.dumps(result)

    # ──────────────────────────────────────────────────────────────
    # Tool 17: Custom Report Generator (A3-05)
    # ──────────────────────────────────────────────────────────────

    DOMAIN_TOOL_MAP = {
        # English keywords
        "headcount": "get_headcount_summary",
        "employees": "get_headcount_summary",
        "saudization": "get_saudization_status",
        "nitaqat": "get_saudization_status",
        "turnover": "get_turnover_metrics",
        "attrition": "predict_attrition_risk",
        "salary": "get_salary_distribution",
        "budget": "get_department_budget",
        "workforce": "get_workforce_overview",
        "compliance": "get_compliance_status",
        "recruitment": "get_recruitment_analytics",
        "hiring": "get_recruitment_analytics",
        "leave": "get_leave_analytics",
        "attendance": "get_attendance_analytics",
        "onboarding": "get_onboarding_analytics",
        "payroll": "get_payroll_summary",
        "gosi": "audit_gosi_compliance",
        "policy": "get_policy_acknowledgments",
        # Arabic keywords
        "موظفين": "get_headcount_summary",
        "سعودة": "get_saudization_status",
        "نطاقات": "get_saudization_status",
        "دوران": "get_turnover_metrics",
        "تسرب": "predict_attrition_risk",
        "رواتب": "get_salary_distribution",
        "ميزانية": "get_department_budget",
        "إجازات": "get_leave_analytics",
        "حضور": "get_attendance_analytics",
        "تأهيل": "get_onboarding_analytics",
        "توظيف": "get_recruitment_analytics",
        "امتثال": "get_compliance_status",
        "تأمينات": "audit_gosi_compliance",
    }

    async def _generate_custom_report(self, tool_input: dict) -> str:
        query = tool_input.get("query", "")
        if not query or not query.strip():
            return json.dumps({"error": "A query is required to generate a custom report."})

        fmt = tool_input.get("format", "summary")
        export = tool_input.get("export", False)

        # Step 1: Identify domains referenced in the query
        query_lower = query.lower()
        matched_tools: set[str] = set()
        for keyword, tool_name in self.DOMAIN_TOOL_MAP.items():
            if keyword in query_lower:
                matched_tools.add(tool_name)

        # Fallback: ambiguous query -> workforce overview
        if not matched_tools:
            matched_tools = {"get_workforce_overview"}

        # Cap at 4 tools to prevent excessive queries
        if len(matched_tools) > 4:
            matched_tools = set(list(matched_tools)[:4])

        tools_used = sorted(matched_tools)
        warning = None
        if len(matched_tools) > 3:
            warning = "Report combines 4+ data domains. Results may be complex."

        # Step 2: Execute each matched tool sequentially (no asyncio.gather on single session)
        results: dict[str, dict] = {}
        for tool_name in tools_used:
            sub_input: dict = {}
            dept_id = tool_input.get("department_id")
            if dept_id:
                sub_input["department_id"] = dept_id
            # For tools that need a query (generate_custom_report itself), skip
            if tool_name == "generate_custom_report":
                continue
            # For department budget, skip if no dept_id (it requires one)
            if tool_name == "get_department_budget" and not dept_id:
                results[tool_name] = {"note": "Department budget requires a specific department_id."}
                continue
            result_str = await self.handle_tool_call(tool_name, sub_input)
            try:
                results[tool_name] = json.loads(result_str)
            except json.JSONDecodeError:
                results[tool_name] = {"raw": result_str}

        # Step 3: Format output
        report: dict = {
            "title": f"Custom Report: {query[:100]}",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "data_sources_used": tools_used,
            "data": results,
        }

        if warning:
            report["warning"] = warning

        if fmt == "table":
            columns, rows = self._results_to_table(results)
            report["columns"] = columns
            report["rows"] = rows
        elif fmt == "summary":
            report["narrative"] = self._results_to_narrative(results, query)

        if export:
            report["csv_text"] = self._results_to_csv(results)

        return json.dumps(report)

    def _results_to_narrative(self, results: dict, query: str) -> str:
        """Build a brief narrative summary from combined tool results."""
        parts = []
        for tool_name, data in results.items():
            if isinstance(data, dict):
                if "message" in data:
                    parts.append(data["message"])
                elif "org_summary" in data:
                    summary = data["org_summary"]
                    if "total_headcount" in summary:
                        parts.append(f"Total headcount: {summary['total_headcount']}")
                    if "saudi_pct" in summary:
                        parts.append(f"Saudization: {summary.get('saudi_pct', 'N/A')}%")
                elif "overall_turnover_rate_pct" in data:
                    parts.append(f"Turnover rate: {data['overall_turnover_rate_pct']}%")
                elif "headcount" in data and "nitaqat_band" in data:
                    parts.append(f"Workforce: {data['headcount'].get('total', 'N/A')} employees")
                elif "summary" in data and isinstance(data["summary"], dict):
                    s = data["summary"]
                    for k, v in s.items():
                        parts.append(f"{k.replace('_', ' ').title()}: {v}")
                        if len(parts) >= 8:
                            break
        if not parts:
            parts.append(f"Report generated for query: {query}")
        return " | ".join(parts[:10])

    def _results_to_table(self, results: dict) -> tuple[list[str], list[list]]:
        """Convert results to a simple table format."""
        columns = ["Source", "Metric", "Value"]
        rows = []
        for tool_name, data in results.items():
            if isinstance(data, dict):
                for key, val in data.items():
                    if isinstance(val, (str, int, float, bool)):
                        rows.append([tool_name, key, val])
                    elif isinstance(val, dict):
                        for sub_k, sub_v in val.items():
                            if isinstance(sub_v, (str, int, float, bool)):
                                rows.append([tool_name, f"{key}.{sub_k}", sub_v])
        return columns, rows[:50]  # Cap rows

    def _results_to_csv(self, results: dict) -> str:
        """Convert results to CSV text."""
        columns, rows = self._results_to_table(results)
        lines = [",".join(str(c) for c in columns)]
        for row in rows:
            lines.append(",".join(str(v) for v in row))
        return "\n".join(lines) + "\n"

    # ──────────────────────────────────────────────────────────────
    # System prompt customization
    # ──────────────────────────────────────────────────────────────

    def get_system_prompt(self, employee_name: str, employee_id: str, language: str = "ar") -> str:
        base_prompt = super().get_system_prompt(employee_name, employee_id, language)
        handoff_from = self._handoff_from
        is_first = self._is_first_message

        if handoff_from:
            agent_display = {
                "ahmad": "أحمد",
                "deema": "ديمة",
                "waleed": "وليد",
                "mohammad": "محمد",
                "yara": "يارا",
            }
            from_name = agent_display.get(handoff_from, handoff_from)
            base_prompt += (
                f"\n\nIMPORTANT — Agent handoff: Transferred from {from_name}. "
                "Introduce yourself briefly then address their request directly."
            )
        elif is_first:
            base_prompt += (
                "\n\nThis is the start of a new conversation. Greet the employee warmly, "
                "introduce yourself as Ahmad the CHRO intelligence partner, and ask how you can help "
                "with HR analytics, metrics, or compliance insights."
            )

        return base_prompt
