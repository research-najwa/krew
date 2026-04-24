"""Ahmad — CHRO Intelligence Agent.

Provides executive-level HR analytics, workforce metrics, compliance status,
and strategic insights. Read-only: Ahmad never modifies data.

Phase A1: Core HR Metrics + Compliance
"""
import json
import logging
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import BaseAgent
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

logger = logging.getLogger(__name__)


class AhmadAgent(BaseAgent):
    name = "Ahmad"
    name_ar = "أحمد"
    role = "CHRO"
    division = "Executive Leadership"
    MIN_GROUP_SIZE = 5  # k-anonymity threshold for all analytics tools
    personality = (
        "Strategic, data-driven, and executive-oriented. You lead with headline numbers "
        "and tie every metric to business impact. You present insights clearly, using "
        "structured summaries with key takeaways. You understand Saudi labor law, Nitaqat, "
        "and GOSI deeply. You are bilingual and switch naturally between Arabic and English."
    )

    def _get_scope_rules(self) -> str:
        return (
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
        ]

    # ──────────────────────────────────────────────────────────────
    # Tool dispatch
    # ──────────────────────────────────────────────────────────────

    async def handle_tool_call(self, tool_name: str, tool_input: dict) -> str:
        try:
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
        cutoff_date = date.today() - timedelta(days=months * 30)

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
        current_month = date.today().month
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

        today = date.today()
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
        cutoff = date.today() - timedelta(days=months * 30)

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
        cutoff = date.today() - timedelta(days=months * 30)

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
        current_year = date.today().year
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
        cutoff = date.today() - timedelta(days=months * 30)

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
        today = date.today()
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
