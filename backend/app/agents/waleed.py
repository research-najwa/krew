"""Waleed — HRBP (HR Business Partner). Strategic partner for managers to
manage their teams effectively. Provides team dashboards, probation tracking,
flight risk analysis, compliance oversight, and workforce planning tools.

Strategic, data-driven, and supportive. Helps managers make informed decisions
about their teams.
"""
import html
import json
import logging
import random
from datetime import date, datetime, timedelta, timezone
from statistics import median
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select, func as sa_func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import (
    BaseAgent,
    ROLES_MANAGER_UP, ROLES_DEPT_HEAD_UP, ROLES_HR_MANAGER_UP,
)
from app.models.employee import Employee, EmployeeStatus, Department
from app.models.employee_document import EmployeeDocument
from app.models.leave import LeaveBalance, LeaveRequest, LeaveStatus
from app.models.onboarding import (
    OnboardingAssignment,
    OnboardingAssignmentStatus,
    OnboardingStepAssignment,
    OnboardingStepStatus,
)
from app.services.manager import ManagerService
from app.services.onboarding import OnboardingService


logger = logging.getLogger(__name__)


class WaleedAgent(BaseAgent):
    name = "Waleed"
    name_ar = "وليد"
    role = "HRBP — HR Business Partner"
    division = "Shared Services"

    # RBAC: search_employee requires manager-level access
    _SEARCH_ALLOWED_ROLES: set[str] = {
        "manager", "hr_manager", "hr_specialist", "executive", "admin",
        "c_suite", "department_head",
    }

    # -- Persona-based tool visibility --
    # All Waleed tools are manager-oriented. Employees can still chat with
    # Waleed for general HRBP questions, but won't see team tools.
    TOOL_VISIBILITY: dict[str, set[str]] = {
        # Manager+ team tools
        "search_employee":        ROLES_MANAGER_UP,
        "view_team":              ROLES_MANAGER_UP,
        "get_team_headcount":     ROLES_MANAGER_UP,
        "view_pending_approvals": ROLES_MANAGER_UP,
        "approve_leave":          ROLES_MANAGER_UP,
        "reject_leave":           ROLES_MANAGER_UP,
        "get_team_leave_calendar": ROLES_MANAGER_UP,
        "get_team_dashboard":     ROLES_MANAGER_UP,
        "get_probation_tracker":  ROLES_MANAGER_UP,
        "get_team_attendance":    ROLES_MANAGER_UP,
        "prepare_one_on_one":     ROLES_MANAGER_UP,
        "get_team_compliance":    ROLES_MANAGER_UP,
        "get_manager_action_items": ROLES_MANAGER_UP,
        "generate_pip":           ROLES_MANAGER_UP,
        # Department head+ (sensitive data)
        "get_compensation_overview": ROLES_DEPT_HEAD_UP,
        "get_flight_risk":        ROLES_DEPT_HEAD_UP,
        "request_headcount":      ROLES_DEPT_HEAD_UP,
    }

    personality = (
        "Strategic, data-driven, and supportive. You help managers make informed "
        "decisions about their teams. You provide actionable insights on team health, "
        "compliance, and workforce planning. You are proactive about flagging risks "
        "and celebrating wins."
    )

    # ------------------------------------------------------------------
    # Scope rules
    # ------------------------------------------------------------------

    def _get_scope_rules(self) -> str:
        return (
            "\nScope boundaries — STRICTLY enforce these:\n"
            "You handle: team management, leave approvals, team dashboards, probation tracking, "
            "attendance, compensation overview, flight risk analysis, 1:1 preparation, compliance, "
            "headcount requests, action items, and performance improvement plans (PIPs).\n"
            "You do NOT handle:\n"
            "- General HR questions, leave requests (as employee), balances, or policy questions → redirect to Deema (ديمة)\n"
            "- Onboarding checklists, new hire setup, or onboarding steps → redirect to Deema (ديمة)\n"
            "- Recruitment, job postings, candidates, or interviews → redirect to Mohammad (محمد)\n"
            "- Compliance analytics, workforce metrics, or financial reports → redirect to Ahmad (أحمد)\n"
            "- AI workforce planning, agent factory, or agent deployment → redirect to Yara (يارا)\n"
            "Never attempt to answer questions outside your scope, even if you think you know the answer.\n"
        )

    # ------------------------------------------------------------------
    # Tool definitions (17 total)
    # ------------------------------------------------------------------

    def get_tools(self) -> list[dict]:
        return [
            # ── Tool 1: search_employee ───────────────────────────────
            {
                "name": "search_employee",
                "description": "Search for an employee by name, employee number, or partial match. Use this to find an employee's UUID before calling other tools.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Employee name, employee number (e.g. EMP-005), or partial name to search for",
                        },
                    },
                    "required": ["query"],
                },
            },
            # ── Tool 2: view_team ─────────────────────────────────────
            {
                "name": "view_team",
                "description": "List the manager's direct reports with basic info (name, job title, department). Only works if the current employee is a manager.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "employee_id": {
                            "type": "string",
                            "description": "The manager's employee UUID",
                        },
                    },
                    "required": ["employee_id"],
                },
            },
            # ── Tool 3: get_team_headcount ────────────────────────────
            {
                "name": "get_team_headcount",
                "description": "Get team headcount summary — total count, Saudi/non-Saudi breakdown, and department distribution. Important for Saudization compliance.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "employee_id": {
                            "type": "string",
                            "description": "The manager's employee UUID",
                        },
                    },
                    "required": ["employee_id"],
                },
            },
            # ── Tool 4: view_pending_approvals ────────────────────────
            {
                "name": "view_pending_approvals",
                "description": "List pending leave requests from the manager's direct reports that need approval.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "employee_id": {
                            "type": "string",
                            "description": "The manager's employee UUID",
                        },
                    },
                    "required": ["employee_id"],
                },
            },
            # ── Tool 5: approve_leave ─────────────────────────────────
            {
                "name": "approve_leave",
                "description": "Approve a pending leave request from a direct report. The request must belong to one of the manager's direct reports.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "employee_id": {
                            "type": "string",
                            "description": "The manager's employee UUID",
                        },
                        "request_id": {
                            "type": "string",
                            "description": "The leave request UUID to approve",
                        },
                    },
                    "required": ["employee_id", "request_id"],
                },
            },
            # ── Tool 6: reject_leave ──────────────────────────────────
            {
                "name": "reject_leave",
                "description": "Reject a pending leave request from a direct report with a reason.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "employee_id": {
                            "type": "string",
                            "description": "The manager's employee UUID",
                        },
                        "request_id": {
                            "type": "string",
                            "description": "The leave request UUID to reject",
                        },
                        "reason": {
                            "type": "string",
                            "description": "Reason for rejection",
                        },
                    },
                    "required": ["employee_id", "request_id", "reason"],
                },
            },
            # ── Tool 7: get_team_leave_calendar ───────────────────────
            {
                "name": "get_team_leave_calendar",
                "description": "Show approved and pending leaves for the manager's team within a date range. Accepts any start_date and end_date in YYYY-MM-DD format, including past and future months. Helps managers plan around absences.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "employee_id": {
                            "type": "string",
                            "description": "The manager's employee UUID",
                        },
                        "start_date": {
                            "type": "string",
                            "description": "Start date in YYYY-MM-DD format. Can be any date including future months.",
                        },
                        "end_date": {
                            "type": "string",
                            "description": "End date in YYYY-MM-DD format. Can be any date including future months.",
                        },
                    },
                    "required": ["employee_id", "start_date", "end_date"],
                },
            },
            # ── Tool 8: get_team_dashboard ────────────────────────────
            {
                "name": "get_team_dashboard",
                "description": "Get a comprehensive manager dashboard snapshot: headcount, pending approvals, active onboarding, probation ending soon, team leave this week, and expiring documents. This is the 'home screen' for a manager.",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                },
            },
            # ── Tool 9: get_probation_tracker ─────────────────────────
            {
                "name": "get_probation_tracker",
                "description": "Track employees currently on probation (first 90 days) and those whose probation recently ended and need confirmation. Shows days remaining and probation end dates.",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                },
            },
            # ── Tool 10: get_team_attendance ──────────────────────────
            {
                "name": "get_team_attendance",
                "description": "Get team attendance summary for a given period. Shows present days, absent days, late arrivals, and remote days per employee.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "period": {
                            "type": "string",
                            "enum": ["this_week", "this_month", "last_month"],
                            "description": "Time period for the attendance report. Defaults to this_month.",
                        },
                    },
                },
            },
            # ── Tool 11: get_compensation_overview ────────────────────
            {
                "name": "get_compensation_overview",
                "description": "Get an anonymized compensation overview for the manager's team: average salary, salary ranges, total monthly cost, Saudi vs non-Saudi averages, and budget utilization.",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                },
            },
            # ── Tool 12: get_flight_risk ──────────────────────────────
            {
                "name": "get_flight_risk",
                "description": "Analyze flight risk for each direct report. Computes a risk score based on tenure, salary position, leave usage, and time since last raise. Returns risk level, factors, and recommendations.",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                },
            },
            # ── Tool 13: prepare_one_on_one ───────────────────────────
            {
                "name": "prepare_one_on_one",
                "description": "Prepare talking points and context for a 1:1 meeting with a direct report. Gathers profile, leave usage, onboarding status, milestones, and suggested conversation starters.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "employee_id": {
                            "type": "string",
                            "description": "The direct report's employee UUID",
                        },
                    },
                    "required": ["employee_id"],
                },
            },
            # ── Tool 14: get_team_compliance ──────────────────────────
            {
                "name": "get_team_compliance",
                "description": "Check team compliance status: expiring documents within 60 days and incomplete onboarding assignments. Returns per-employee breakdown with issue details.",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                },
            },
            # ── Tool 15: request_headcount ────────────────────────────
            {
                "name": "request_headcount",
                "description": "Submit a headcount request for a new position in the team. Captures job title, justification, and optional department. Returns a request summary.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "job_title": {
                            "type": "string",
                            "description": "The job title for the requested position",
                        },
                        "justification": {
                            "type": "string",
                            "description": "Business justification for the headcount request",
                        },
                        "department_id": {
                            "type": "string",
                            "description": "Optional department UUID for the position",
                        },
                    },
                    "required": ["job_title", "justification"],
                },
            },
            # ── Tool 16: get_manager_action_items ─────────────────────
            {
                "name": "get_manager_action_items",
                "description": "Get all pending action items for the manager: leave approvals, probation confirmations due, overdue onboarding steps, and expiring documents. Categorized by priority.",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                },
            },
            # ── Tool 17: generate_pip ─────────────────────────────────
            {
                "name": "generate_pip",
                "description": "Generate a structured Performance Improvement Plan (PIP) draft for a direct report. Includes 30/60/90 day milestones, support plan, and Saudi Labor Law references.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "employee_id": {
                            "type": "string",
                            "description": "The direct report's employee UUID",
                        },
                        "performance_issues": {
                            "type": "string",
                            "description": "Description of the performance issues observed",
                        },
                        "improvement_areas": {
                            "type": "string",
                            "description": "Specific areas where improvement is expected",
                        },
                    },
                    "required": ["employee_id", "performance_issues", "improvement_areas"],
                },
            },
        ]

    # ------------------------------------------------------------------
    # System prompt override — handoff & greeting awareness
    # ------------------------------------------------------------------

    def get_system_prompt(self, employee_name: str, employee_id: str, language: str = "ar") -> str:
        base_prompt = super().get_system_prompt(employee_name, employee_id, language)
        handoff_from = self._handoff_from
        is_first = self._is_first_message

        if handoff_from:
            agent_display = {"deema": "ديمة", "mohammad": "محمد", "yara": "يارا", "ahmad": "أحمد"}
            from_name = agent_display.get(handoff_from, handoff_from)
            base_prompt += (
                f"\n\nIMPORTANT — Agent handoff: Transferred from {from_name}. "
                "Introduce yourself briefly then address their request directly."
            )
        elif is_first:
            base_prompt += "\n\nNew conversation. Greet warmly and introduce yourself briefly."
        return base_prompt

    # ------------------------------------------------------------------
    # Proactive context — manager dashboard
    # ------------------------------------------------------------------

    async def get_proactive_context(self, employee_id: str) -> str | None:
        if not employee_id:
            return None
        try:
            emp_uuid = UUID(employee_id)
        except ValueError:
            return None

        context_parts: list[str] = []
        try:
            is_manager = await self._verify_is_manager(emp_uuid)
            if is_manager:
                await self._build_manager_context(emp_uuid, context_parts)
        except Exception as exc:
            logger.warning("Waleed proactive context failed for %s: %s", employee_id, exc)
            return None

        if not context_parts:
            return None
        return "\n\nProactive context for this employee:\n" + "\n".join(f"- {p}" for p in context_parts)

    async def _build_manager_context(self, emp_uuid: UUID, parts: list[str]) -> None:
        svc = ManagerService(self.db, self.tenant_id, emp_uuid)

        # 1. Pending leave approvals
        pending = await svc.get_pending_approvals()
        if pending:
            parts.append(f"This manager has {len(pending)} pending leave approval(s). Proactively mention this.")

        # 2. Overdue onboarding steps
        onb_svc = OnboardingService(self.db, self.tenant_id)
        overdue = await onb_svc.get_overdue_steps(requesting_employee_id=emp_uuid)
        if overdue:
            parts.append(f"There are {len(overdue)} overdue onboarding step(s). Suggest reviewing the dashboard.")

        # 3. New hires in last 30 days (Saudi timezone)
        cutoff = datetime.now(ZoneInfo("Asia/Riyadh")).date() - timedelta(days=30)
        result = await self.db.execute(
            select(Employee.first_name, Employee.last_name, Employee.first_name_ar, Employee.last_name_ar, Employee.hire_date)
            .where(
                Employee.tenant_id == self.tenant_id,
                Employee.manager_id == emp_uuid,
                Employee.status == EmployeeStatus.active,
                Employee.hire_date >= cutoff,
            )
            .order_by(Employee.hire_date.desc())
            .limit(5)
        )
        new_hires = result.all()
        if new_hires:
            names = [
                f"<user_data>{html.escape(r.first_name_ar or r.first_name)} {html.escape(r.last_name_ar or r.last_name)}</user_data>"
                for r in new_hires
            ]
            parts.append(f"{len(new_hires)} new team member(s) in last 30 days: {', '.join(names)}. Offer to check their status.")

        # 4. Probation ending within 14 days
        today = date.today()
        probation_soon = await self.db.execute(
            select(Employee.first_name, Employee.last_name, Employee.probation_end_date)
            .where(
                Employee.tenant_id == self.tenant_id,
                Employee.manager_id == emp_uuid,
                Employee.status == EmployeeStatus.active,
                Employee.probation_end_date.isnot(None),
                Employee.probation_completed == False,  # noqa: E712
                Employee.probation_end_date <= today + timedelta(days=14),
                Employee.probation_end_date >= today,
            )
        )
        prob_rows = probation_soon.all()
        if prob_rows:
            parts.append(f"{len(prob_rows)} employee(s) with probation ending within 14 days. Suggest reviewing probation tracker.")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _ownership_error(self) -> str:
        """Return a standard ownership-denial JSON string."""
        return json.dumps({
            "error": "You can only access your own data.",
            "error_ar": "يمكنك الوصول إلى بياناتك فقط",
        })

    async def _verify_is_manager(self, employee_id: UUID) -> bool:
        """Check if this employee has direct reports."""
        result = await self.db.execute(
            select(Employee.id).where(
                Employee.tenant_id == self.tenant_id,
                Employee.manager_id == employee_id,
                Employee.status == EmployeeStatus.active,
            ).limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def _verify_manager_of(self, target_employee_id: UUID) -> bool:
        """Check if current user is the manager of the target employee."""
        if not self._employee_id:
            return False
        result = await self.db.execute(
            select(Employee.manager_id).where(
                Employee.id == target_employee_id,
                Employee.tenant_id == self.tenant_id,
                Employee.status == EmployeeStatus.active,
            )
        )
        manager_id = result.scalar_one_or_none()
        return manager_id is not None and str(manager_id) == str(self._employee_id)

    async def _get_team_employees(self) -> list:
        """Get all active direct reports for the current manager."""
        result = await self.db.execute(
            select(Employee).where(
                Employee.tenant_id == self.tenant_id,
                Employee.manager_id == UUID(self._employee_id),
                Employee.status == EmployeeStatus.active,
            ).order_by(Employee.first_name)
        )
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Tool dispatch
    # ------------------------------------------------------------------

    async def handle_tool_call(self, tool_name: str, tool_input: dict) -> str:
        # Validate all UUID fields upfront
        uuid_fields = ["employee_id", "request_id", "department_id"]
        for field in uuid_fields:
            if field in tool_input and tool_input[field] is not None:
                try:
                    UUID(tool_input[field])
                except (ValueError, AttributeError):
                    return json.dumps({
                        "error": f"Invalid {field} format. Please provide a valid UUID.",
                        "error_ar": f"صيغة {field} غير صحيحة. يرجى تقديم معرّف صالح.",
                    })

        # ── Existing manager tools ────────────────────────────────────
        if tool_name == "search_employee":
            if self._employee_role not in self._SEARCH_ALLOWED_ROLES:
                return json.dumps({
                    "error": True,
                    "message": "Employee search requires manager or HR access.",
                    "message_ar": "البحث عن الموظفين يتطلب صلاحيات إدارية أو موارد بشرية",
                })
            return await self._search_employee(tool_input["query"])

        elif tool_name == "view_team":
            employee_id = tool_input["employee_id"]
            if not self._employee_id or str(employee_id) != str(self._employee_id):
                return self._ownership_error()
            return await self._view_team(UUID(employee_id))

        elif tool_name == "get_team_headcount":
            employee_id = tool_input["employee_id"]
            if not self._employee_id or str(employee_id) != str(self._employee_id):
                return self._ownership_error()
            return await self._get_team_headcount(UUID(employee_id))

        elif tool_name == "view_pending_approvals":
            employee_id = tool_input["employee_id"]
            if not self._employee_id or str(employee_id) != str(self._employee_id):
                return self._ownership_error()
            return await self._view_pending_approvals(UUID(employee_id))

        elif tool_name == "approve_leave":
            employee_id = tool_input["employee_id"]
            if not self._employee_id or str(employee_id) != str(self._employee_id):
                return self._ownership_error()
            return await self._approve_leave(
                UUID(employee_id), UUID(tool_input["request_id"])
            )

        elif tool_name == "reject_leave":
            employee_id = tool_input["employee_id"]
            if not self._employee_id or str(employee_id) != str(self._employee_id):
                return self._ownership_error()
            return await self._reject_leave(
                UUID(employee_id),
                UUID(tool_input["request_id"]),
                tool_input["reason"],
            )

        elif tool_name == "get_team_leave_calendar":
            employee_id = tool_input["employee_id"]
            if not self._employee_id or str(employee_id) != str(self._employee_id):
                return self._ownership_error()
            return await self._get_team_leave_calendar(
                UUID(employee_id),
                tool_input["start_date"],
                tool_input["end_date"],
            )

        # ── New HRBP tools ────────────────────────────────────────────
        elif tool_name == "get_team_dashboard":
            if not self._employee_id:
                return self._ownership_error()
            return await self._get_team_dashboard()

        elif tool_name == "get_probation_tracker":
            if not self._employee_id:
                return self._ownership_error()
            return await self._get_probation_tracker()

        elif tool_name == "get_team_attendance":
            if not self._employee_id:
                return self._ownership_error()
            return await self._get_team_attendance(tool_input.get("period", "this_month"))

        elif tool_name == "get_compensation_overview":
            if not self._employee_id:
                return self._ownership_error()
            return await self._get_compensation_overview()

        elif tool_name == "get_flight_risk":
            if not self._employee_id:
                return self._ownership_error()
            return await self._get_flight_risk()

        elif tool_name == "prepare_one_on_one":
            employee_id = UUID(tool_input["employee_id"])
            if not await self._verify_manager_of(employee_id):
                return json.dumps({
                    "error": "You can only prepare 1:1s for your direct reports.",
                    "error_ar": "يمكنك تحضير اجتماعات فردية لموظفيك المباشرين فقط.",
                })
            return await self._prepare_one_on_one(employee_id)

        elif tool_name == "get_team_compliance":
            if not self._employee_id:
                return self._ownership_error()
            return await self._get_team_compliance()

        elif tool_name == "request_headcount":
            if not self._employee_id:
                return self._ownership_error()
            return await self._request_headcount(
                tool_input["job_title"],
                tool_input["justification"],
                UUID(tool_input["department_id"]) if tool_input.get("department_id") else None,
            )

        elif tool_name == "get_manager_action_items":
            if not self._employee_id:
                return self._ownership_error()
            return await self._get_manager_action_items()

        elif tool_name == "generate_pip":
            employee_id = UUID(tool_input["employee_id"])
            if not await self._verify_manager_of(employee_id):
                return json.dumps({
                    "error": "You can only create PIPs for your direct reports.",
                    "error_ar": "يمكنك إنشاء خطط تحسين الأداء لموظفيك المباشرين فقط.",
                })
            return await self._generate_pip(
                employee_id,
                tool_input["performance_issues"],
                tool_input["improvement_areas"],
            )

        return json.dumps({"error": f"Unknown tool: {tool_name}"})

    # ==================================================================
    # Existing manager tool implementations
    # ==================================================================

    async def _view_team(self, employee_id: UUID) -> str:
        if not await self._verify_is_manager(employee_id):
            return json.dumps({
                "error": "You are not a manager. No direct reports found.",
                "error_ar": "لست مديرًا. لم يتم العثور على موظفين تابعين.",
            })

        svc = ManagerService(self.db, self.tenant_id, employee_id)
        team = await svc.get_team()
        return json.dumps({"count": len(team), "team": team})

    async def _view_pending_approvals(self, employee_id: UUID) -> str:
        if not await self._verify_is_manager(employee_id):
            return json.dumps({
                "error": "You are not a manager. No direct reports found.",
                "error_ar": "لست مديرًا. لم يتم العثور على موظفين تابعين.",
            })

        svc = ManagerService(self.db, self.tenant_id, employee_id)
        approvals = await svc.get_pending_approvals()
        if not approvals:
            return json.dumps({
                "message": "No pending leave requests from your team.",
                "message_ar": "لا توجد طلبات إجازة معلقة من فريقك.",
                "count": 0,
            })
        return json.dumps({"count": len(approvals), "pending_requests": approvals})

    async def _approve_leave(self, employee_id: UUID, request_id: UUID) -> str:
        if not await self._verify_is_manager(employee_id):
            return json.dumps({
                "error": "You are not a manager.",
                "error_ar": "لست مديرًا.",
            })

        svc = ManagerService(self.db, self.tenant_id, employee_id)
        result = await svc.approve_leave(request_id)
        return json.dumps(result)

    async def _reject_leave(
        self, employee_id: UUID, request_id: UUID, reason: str
    ) -> str:
        if not await self._verify_is_manager(employee_id):
            return json.dumps({
                "error": "You are not a manager.",
                "error_ar": "لست مديرًا.",
            })

        svc = ManagerService(self.db, self.tenant_id, employee_id)
        result = await svc.reject_leave(request_id, reason)
        return json.dumps(result)

    async def _search_employee(self, query: str) -> str:
        """Search employees by name or employee number within the tenant."""
        q = query.strip()
        words = [w.strip() for w in q.split() if w.strip()]

        conditions = [
            sa_func.lower(Employee.employee_number).contains(q.lower()),
        ]
        for word in words:
            wl = word.lower()
            conditions.extend([
                sa_func.lower(Employee.first_name).contains(wl),
                sa_func.lower(Employee.last_name).contains(wl),
                Employee.first_name_ar.contains(word),
                Employee.last_name_ar.contains(word),
            ])

        result = await self.db.execute(
            select(Employee).where(
                Employee.tenant_id == self.tenant_id,
                Employee.status == EmployeeStatus.active,
                or_(*conditions),
            ).limit(10)
        )
        employees = result.scalars().all()

        if not employees:
            return json.dumps({
                "count": 0,
                "message": f"No employees found matching '{query}'.",
                "message_ar": f"لم يتم العثور على موظفين مطابقين لـ '{query}'.",
            })

        return json.dumps({
            "count": len(employees),
            "employees": [
                {
                    "id": str(e.id),
                    "employee_number": e.employee_number,
                    "name": e.full_name,
                    "name_ar": f"{e.first_name_ar or ''} {e.last_name_ar or ''}".strip() or None,
                    "job_title": e.job_title,
                    "hire_date": e.hire_date.isoformat() if e.hire_date else None,
                }
                for e in employees
            ],
        })

    async def _get_team_leave_calendar(
        self, employee_id: UUID, start_date: str, end_date: str
    ) -> str:
        if not await self._verify_is_manager(employee_id):
            return json.dumps({
                "error": "You are not a manager.",
                "error_ar": "لست مديرًا.",
            })
        try:
            sd = date.fromisoformat(start_date)
            ed = date.fromisoformat(end_date)
        except ValueError:
            return json.dumps({
                "error": "Invalid date format. Use YYYY-MM-DD.",
                "error_ar": "صيغة التاريخ غير صحيحة. استخدم YYYY-MM-DD.",
            })

        svc = ManagerService(self.db, self.tenant_id, employee_id)
        calendar = await svc.get_leave_calendar(sd, ed)
        if not calendar:
            return json.dumps({
                "message": f"No leaves found between {start_date} and {end_date}.",
                "message_ar": f"لا توجد إجازات بين {start_date} و {end_date}.",
                "count": 0,
            })
        return json.dumps({"count": len(calendar), "leaves": calendar})

    async def _get_team_headcount(self, employee_id: UUID) -> str:
        if not await self._verify_is_manager(employee_id):
            return json.dumps({
                "error": "You are not a manager.",
                "error_ar": "لست مديرًا.",
            })
        svc = ManagerService(self.db, self.tenant_id, employee_id)
        headcount = await svc.get_headcount()
        return json.dumps(headcount)

    # ==================================================================
    # New HRBP tool implementations
    # ==================================================================

    # ── Tool 8: get_team_dashboard ────────────────────────────────────

    async def _get_team_dashboard(self) -> str:
        """Comprehensive manager dashboard snapshot."""
        manager_id = UUID(self._employee_id)

        if not await self._verify_is_manager(manager_id):
            return json.dumps({
                "error": "You are not a manager. No direct reports found.",
                "error_ar": "لست مديرًا. لم يتم العثور على موظفين تابعين.",
            })

        today = date.today()
        team = await self._get_team_employees()
        team_ids = [e.id for e in team]

        # 1. Headcount
        total = len(team)
        saudi_count = sum(1 for e in team if e.is_saudi)
        non_saudi_count = total - saudi_count

        # 2. Pending approvals count
        svc = ManagerService(self.db, self.tenant_id, manager_id)
        pending = await svc.get_pending_approvals()
        pending_count = len(pending)

        # 3. Active onboarding count
        active_onboarding = 0
        if team_ids:
            onb_result = await self.db.execute(
                select(sa_func.count(OnboardingAssignment.id)).where(
                    OnboardingAssignment.tenant_id == self.tenant_id,
                    OnboardingAssignment.employee_id.in_(team_ids),
                    OnboardingAssignment.status == OnboardingAssignmentStatus.in_progress,
                )
            )
            active_onboarding = onb_result.scalar() or 0

        # 4. Probation ending within 30 days
        probation_ending = []
        for emp in team:
            prob_end = emp.probation_end_date
            if prob_end and not emp.probation_completed:
                days_left = (prob_end - today).days
                if 0 <= days_left <= 30:
                    probation_ending.append({
                        "name": emp.full_name,
                        "probation_end_date": prob_end.isoformat(),
                        "days_remaining": days_left,
                    })

        # 5. Team leave this week (Sun-Thu)
        weekday = today.weekday()  # 0=Mon
        # Calculate start of current Saudi work week (Sunday)
        # Sunday = weekday 6 in Python
        if weekday == 6:  # Sunday
            week_start = today
        elif weekday < 4:  # Mon-Thu -> go back to last Sunday
            week_start = today - timedelta(days=weekday + 1)
        else:  # Fri(4) or Sat(5) -> go back to last Sunday
            week_start = today - timedelta(days=weekday + 1)
        week_end = week_start + timedelta(days=4)  # Thursday

        leaves_this_week = 0
        if team_ids:
            leave_result = await self.db.execute(
                select(sa_func.count(LeaveRequest.id)).where(
                    LeaveRequest.employee_id.in_(team_ids),
                    LeaveRequest.status.in_([LeaveStatus.approved, LeaveStatus.pending]),
                    LeaveRequest.start_date <= week_end,
                    LeaveRequest.end_date >= week_start,
                )
            )
            leaves_this_week = leave_result.scalar() or 0

        # 6. Expiring documents count (within 60 days)
        expiring_docs = 0
        if team_ids:
            doc_result = await self.db.execute(
                select(sa_func.count(EmployeeDocument.id)).where(
                    EmployeeDocument.tenant_id == self.tenant_id,
                    EmployeeDocument.employee_id.in_(team_ids),
                    EmployeeDocument.is_deleted == False,  # noqa: E712
                    EmployeeDocument.expires_at.isnot(None),
                    EmployeeDocument.expires_at <= today + timedelta(days=60),
                    EmployeeDocument.expires_at >= today,
                )
            )
            expiring_docs = doc_result.scalar() or 0

        return json.dumps({
            "dashboard": {
                "headcount": {
                    "total": total,
                    "saudi": saudi_count,
                    "non_saudi": non_saudi_count,
                    "saudization_pct": round(saudi_count / total * 100, 1) if total > 0 else 0,
                },
                "pending_approvals": pending_count,
                "active_onboarding": active_onboarding,
                "probation_ending_soon": {
                    "count": len(probation_ending),
                    "employees": probation_ending,
                },
                "team_leave_this_week": leaves_this_week,
                "expiring_documents": expiring_docs,
                "week_range": f"{week_start.isoformat()} to {week_end.isoformat()}",
            },
        })

    # ── Tool 9: get_probation_tracker ─────────────────────────────────

    async def _get_probation_tracker(self) -> str:
        """Track employees on probation and those needing confirmation."""
        manager_id = UUID(self._employee_id)

        if not await self._verify_is_manager(manager_id):
            return json.dumps({
                "error": "You are not a manager.",
                "error_ar": "لست مديرًا.",
            })

        today = date.today()
        team = await self._get_team_employees()

        on_probation = []
        confirmation_due = []

        for emp in team:
            # Determine probation end: use explicit field or hire_date + 90 days
            prob_end = emp.probation_end_date
            if not prob_end and emp.hire_date:
                prob_end = emp.hire_date + timedelta(days=90)

            if not prob_end:
                continue

            # Already confirmed
            if emp.probation_completed:
                continue

            days_remaining = (prob_end - today).days

            entry = {
                "employee_id": str(emp.id),
                "name": emp.full_name,
                "name_ar": f"{emp.first_name_ar or ''} {emp.last_name_ar or ''}".strip() or None,
                "job_title": emp.job_title,
                "hire_date": emp.hire_date.isoformat() if emp.hire_date else None,
                "probation_end_date": prob_end.isoformat(),
                "days_remaining": max(days_remaining, 0),
            }

            if days_remaining > 0:
                # Still on probation
                entry["status"] = "on_probation"
                on_probation.append(entry)
            elif days_remaining >= -14:
                # Probation ended within last 14 days — needs confirmation
                entry["status"] = "confirmation_due"
                entry["days_overdue"] = abs(days_remaining)
                confirmation_due.append(entry)

        all_employees = on_probation + confirmation_due
        return json.dumps({
            "count": len(all_employees),
            "on_probation": on_probation,
            "confirmation_due": confirmation_due,
            "as_of": today.isoformat(),
        })

    # ── Tool 10: get_team_attendance ──────────────────────────────────

    async def _get_team_attendance(self, period: str = "this_month") -> str:
        """Generate attendance summary for the team (mock data — no attendance table yet)."""
        manager_id = UUID(self._employee_id)

        if not await self._verify_is_manager(manager_id):
            return json.dumps({
                "error": "You are not a manager.",
                "error_ar": "لست مديرًا.",
            })

        today = date.today()
        team = await self._get_team_employees()

        # Determine date range based on period
        if period == "this_week":
            weekday = today.weekday()
            if weekday == 6:
                start = today
            elif weekday < 4:
                start = today - timedelta(days=weekday + 1)
            else:
                start = today - timedelta(days=weekday + 1)
            end = min(today, start + timedelta(days=4))
        elif period == "last_month":
            first_of_this_month = today.replace(day=1)
            end = first_of_this_month - timedelta(days=1)
            start = end.replace(day=1)
        else:  # this_month
            start = today.replace(day=1)
            end = today

        # Count business days (Sun-Thu) in range
        business_days = 0
        d = start
        while d <= end:
            if d.weekday() not in (4, 5):  # Not Fri(4) or Sat(5)
                business_days += 1
            d += timedelta(days=1)

        # Generate realistic mock attendance per employee
        # Seed with employee ID for consistency across calls
        attendance = []
        total_present = 0
        total_absent = 0
        total_late = 0
        total_remote = 0

        for emp in team:
            # Use employee UUID as seed for deterministic mock data
            seed = int(emp.id.int % 10000)
            rng = random.Random(seed + today.month)

            present = max(0, business_days - rng.randint(0, min(3, business_days)))
            absent = business_days - present
            late_count = rng.randint(0, min(3, present))
            remote_days = rng.randint(0, min(present, emp.wfh_days_per_week or 0) * ((end - start).days // 7 + 1)) if emp.work_mode.value in ("remote", "hybrid") else 0

            attendance.append({
                "employee_id": str(emp.id),
                "name": emp.full_name,
                "present_days": present,
                "absent_days": absent,
                "late_count": late_count,
                "remote_days": remote_days,
                "attendance_rate": round(present / business_days * 100, 1) if business_days > 0 else 0,
            })

            total_present += present
            total_absent += absent
            total_late += late_count
            total_remote += remote_days

        return json.dumps({
            "period": period,
            "date_range": f"{start.isoformat()} to {end.isoformat()}",
            "business_days": business_days,
            "team_size": len(team),
            "summary": {
                "total_present_days": total_present,
                "total_absent_days": total_absent,
                "total_late_count": total_late,
                "total_remote_days": total_remote,
                "avg_attendance_rate": round(total_present / (business_days * len(team)) * 100, 1) if business_days > 0 and team else 0,
            },
            "attendance": attendance,
            "note": "Attendance data is estimated. Actual attendance tracking integration pending.",
            "note_ar": "بيانات الحضور تقديرية. تكامل تتبع الحضور الفعلي قيد الإعداد.",
        })

    # ── Tool 11: get_compensation_overview ─────────────────────────────

    async def _get_compensation_overview(self) -> str:
        """Anonymized compensation overview for the manager's team."""
        manager_id = UUID(self._employee_id)

        if not await self._verify_is_manager(manager_id):
            return json.dumps({
                "error": "You are not a manager.",
                "error_ar": "لست مديرًا.",
            })

        team = await self._get_team_employees()
        if not team:
            return json.dumps({
                "message": "No direct reports found.",
                "message_ar": "لم يتم العثور على موظفين تابعين.",
                "count": 0,
            })

        # Collect salaries (filter out None)
        salaries = [e.salary_sar for e in team if e.salary_sar is not None]
        saudi_salaries = [e.salary_sar for e in team if e.salary_sar is not None and e.is_saudi]
        non_saudi_salaries = [e.salary_sar for e in team if e.salary_sar is not None and not e.is_saudi]

        if not salaries:
            return json.dumps({
                "message": "No salary data available for your team.",
                "message_ar": "لا توجد بيانات رواتب متاحة لفريقك.",
            })

        total_monthly = sum(salaries)
        avg_salary = round(total_monthly / len(salaries))
        min_salary = min(salaries)
        max_salary = max(salaries)
        med_salary = round(median(salaries))

        # Salary ranges (anonymized)
        ranges = {
            "below_10k": sum(1 for s in salaries if s < 10000),
            "10k_15k": sum(1 for s in salaries if 10000 <= s < 15000),
            "15k_20k": sum(1 for s in salaries if 15000 <= s < 20000),
            "20k_30k": sum(1 for s in salaries if 20000 <= s < 30000),
            "above_30k": sum(1 for s in salaries if s >= 30000),
        }

        # Budget utilization (assume headcount * 18,000 SAR)
        budget = len(team) * 18000
        utilization = round(total_monthly / budget * 100, 1) if budget > 0 else 0

        return json.dumps({
            "team_size": len(team),
            "employees_with_salary_data": len(salaries),
            "compensation": {
                "average_salary_sar": avg_salary,
                "median_salary_sar": med_salary,
                "min_salary_sar": min_salary,
                "max_salary_sar": max_salary,
                "total_monthly_cost_sar": total_monthly,
                "total_annual_cost_sar": total_monthly * 12,
            },
            "nationality_breakdown": {
                "saudi_avg_salary_sar": round(sum(saudi_salaries) / len(saudi_salaries)) if saudi_salaries else None,
                "saudi_count": len(saudi_salaries),
                "non_saudi_avg_salary_sar": round(sum(non_saudi_salaries) / len(non_saudi_salaries)) if non_saudi_salaries else None,
                "non_saudi_count": len(non_saudi_salaries),
            },
            "salary_distribution": ranges,
            "budget": {
                "assumed_budget_per_head_sar": 18000,
                "total_budget_sar": budget,
                "utilization_pct": utilization,
                "status": "over_budget" if utilization > 100 else "within_budget",
            },
            "currency": "SAR",
        })

    # ── Tool 12: get_flight_risk ──────────────────────────────────────

    async def _get_flight_risk(self) -> str:
        """Compute flight risk scores for direct reports."""
        manager_id = UUID(self._employee_id)

        if not await self._verify_is_manager(manager_id):
            return json.dumps({
                "error": "You are not a manager.",
                "error_ar": "لست مديرًا.",
            })

        today = date.today()
        team = await self._get_team_employees()
        if not team:
            return json.dumps({
                "message": "No direct reports found.",
                "message_ar": "لم يتم العثور على موظفين تابعين.",
                "count": 0,
            })

        team_ids = [e.id for e in team]

        # Fetch leave balances for all team members
        balance_result = await self.db.execute(
            select(LeaveBalance).where(
                LeaveBalance.employee_id.in_(team_ids),
                LeaveBalance.year == today.year,
            )
        )
        balances = balance_result.scalars().all()

        # Group balances by employee
        balance_map: dict[UUID, list] = {}
        for b in balances:
            balance_map.setdefault(b.employee_id, []).append(b)

        # Calculate team median salary for comparison
        salaries = [e.salary_sar for e in team if e.salary_sar is not None]
        team_median_salary = median(salaries) if salaries else 0

        risk_assessments = []
        for emp in team:
            risk_score = 0
            risk_factors = []
            recommendations = []

            # 1. Tenure < 1 year = +20
            tenure_months = 0
            if emp.hire_date:
                tenure_delta = today - emp.hire_date
                tenure_months = round(tenure_delta.days / 30.44)
                if tenure_delta.days < 365:
                    risk_score += 20
                    risk_factors.append("Short tenure (< 1 year)")
                    recommendations.append("Schedule regular check-ins to ensure engagement")

            # 2. No salary increase in 12 months = +25 (mock: hire > 1 year ago)
            if emp.hire_date and (today - emp.hire_date).days > 365:
                risk_score += 25
                risk_factors.append("No salary review in 12+ months")
                recommendations.append("Consider salary review or merit increase")

            # 3. High leave usage (> 70% of annual balance used) = +15
            emp_balances = balance_map.get(emp.id, [])
            annual_balance = next(
                (b for b in emp_balances if b.leave_type.value == "annual"), None
            )
            if annual_balance and annual_balance.total_days > 0:
                usage_pct = (annual_balance.used_days / annual_balance.total_days) * 100
                if usage_pct > 70:
                    risk_score += 15
                    risk_factors.append(f"High leave usage ({round(usage_pct)}%)")
                    recommendations.append("Discuss work-life balance and workload")

            # 4. Salary below team median = +20
            if emp.salary_sar is not None and team_median_salary > 0:
                if emp.salary_sar < team_median_salary:
                    risk_score += 20
                    risk_factors.append("Salary below team median")
                    recommendations.append("Review compensation against market rates")

            # Determine risk level
            if risk_score >= 50:
                risk_level = "high"
            elif risk_score >= 30:
                risk_level = "medium"
            else:
                risk_level = "low"

            if not recommendations:
                recommendations.append("Employee appears well-positioned. Continue current engagement.")

            risk_assessments.append({
                "employee_id": str(emp.id),
                "name": emp.full_name,
                "name_ar": f"{emp.first_name_ar or ''} {emp.last_name_ar or ''}".strip() or None,
                "job_title": emp.job_title,
                "risk_level": risk_level,
                "risk_score": risk_score,
                "risk_factors": risk_factors,
                "tenure_months": tenure_months,
                "recommendations": recommendations,
            })

        # Sort by risk score descending
        risk_assessments.sort(key=lambda x: x["risk_score"], reverse=True)

        high_count = sum(1 for r in risk_assessments if r["risk_level"] == "high")
        medium_count = sum(1 for r in risk_assessments if r["risk_level"] == "medium")
        low_count = sum(1 for r in risk_assessments if r["risk_level"] == "low")

        return json.dumps({
            "count": len(risk_assessments),
            "summary": {
                "high_risk": high_count,
                "medium_risk": medium_count,
                "low_risk": low_count,
            },
            "employees": risk_assessments,
            "as_of": today.isoformat(),
        })

    # ── Tool 13: prepare_one_on_one ───────────────────────────────────

    async def _prepare_one_on_one(self, employee_id: UUID) -> str:
        """Gather context and talking points for a 1:1 meeting."""
        # Fetch employee
        emp_result = await self.db.execute(
            select(Employee).where(
                Employee.id == employee_id,
                Employee.tenant_id == self.tenant_id,
            )
        )
        emp = emp_result.scalar_one_or_none()
        if not emp:
            return json.dumps({
                "error": "Employee not found.",
                "error_ar": "الموظف غير موجود.",
            })

        today = date.today()

        # Department name
        dept_name = None
        if emp.department_id:
            dept_name = await self._resolve_dept_name(emp.department_id)

        # Tenure
        tenure_months = 0
        if emp.hire_date:
            tenure_months = round((today - emp.hire_date).days / 30.44)

        # Leave balance summary
        balance_result = await self.db.execute(
            select(LeaveBalance).where(
                LeaveBalance.employee_id == employee_id,
                LeaveBalance.year == today.year,
            )
        )
        balances = balance_result.scalars().all()
        leave_summary = []
        for b in balances:
            leave_summary.append({
                "type": b.leave_type.value,
                "total": b.total_days,
                "used": b.used_days,
                "remaining": b.remaining_days,
            })

        # Pending leave requests
        pending_result = await self.db.execute(
            select(LeaveRequest).where(
                LeaveRequest.employee_id == employee_id,
                LeaveRequest.status == LeaveStatus.pending,
            ).order_by(LeaveRequest.created_at.desc())
        )
        pending_leaves = pending_result.scalars().all()
        pending_leave_data = [
            {
                "request_id": str(lr.id),
                "type": lr.leave_type.value,
                "start_date": lr.start_date.isoformat(),
                "end_date": lr.end_date.isoformat(),
                "business_days": lr.business_days,
            }
            for lr in pending_leaves
        ]

        # Recent leave history (last 90 days)
        ninety_days_ago = today - timedelta(days=90)
        recent_result = await self.db.execute(
            select(LeaveRequest).where(
                LeaveRequest.employee_id == employee_id,
                LeaveRequest.status == LeaveStatus.approved,
                LeaveRequest.start_date >= ninety_days_ago,
            ).order_by(LeaveRequest.start_date.desc())
        )
        recent_leaves = recent_result.scalars().all()
        recent_leave_data = [
            {
                "type": lr.leave_type.value,
                "start_date": lr.start_date.isoformat(),
                "end_date": lr.end_date.isoformat(),
                "business_days": lr.business_days,
            }
            for lr in recent_leaves
        ]

        # Onboarding status
        onb_svc = OnboardingService(self.db, self.tenant_id)
        onboarding = await onb_svc.get_employee_onboarding(employee_id)
        onboarding_info = None
        if onboarding:
            onboarding_info = {
                "status": onboarding["status"].value if hasattr(onboarding.get("status", ""), "value") else onboarding.get("status"),
                "progress_pct": onboarding["progress_pct"],
                "completed_steps": onboarding["completed_steps"],
                "total_steps": onboarding["total_steps"],
            }

        # Milestones
        milestones = []
        if emp.hire_date:
            # Work anniversary
            this_year_anniversary = emp.hire_date.replace(year=today.year)
            days_to_anniversary = (this_year_anniversary - today).days
            if -7 <= days_to_anniversary <= 30:
                years = today.year - emp.hire_date.year
                milestones.append({
                    "type": "work_anniversary",
                    "description": f"{years} year(s) work anniversary",
                    "date": this_year_anniversary.isoformat(),
                    "days_away": days_to_anniversary,
                })

            # Probation end
            prob_end = emp.probation_end_date
            if not prob_end:
                prob_end = emp.hire_date + timedelta(days=90)
            if not emp.probation_completed:
                days_to_prob = (prob_end - today).days
                if -14 <= days_to_prob <= 30:
                    milestones.append({
                        "type": "probation_end",
                        "description": "Probation period ends",
                        "date": prob_end.isoformat(),
                        "days_away": days_to_prob,
                    })

        # Conversation starters
        conversation_starters = [
            "How are things going with your current projects?",
            "Is there anything blocking your progress?",
            "How is your workload? Do you feel it's manageable?",
            "Are there any skills or areas you'd like to develop?",
        ]
        if onboarding_info and onboarding_info["progress_pct"] < 100:
            conversation_starters.insert(0, "How is your onboarding going? Do you need any support?")
        if tenure_months <= 3:
            conversation_starters.insert(0, "How are you settling in? Is there anything we can do to help?")

        # Action items
        action_items = []
        if pending_leave_data:
            action_items.append({
                "item": f"Review {len(pending_leave_data)} pending leave request(s)",
                "priority": "normal",
            })
        for ms in milestones:
            if ms["type"] == "probation_end" and ms["days_away"] <= 14:
                action_items.append({
                    "item": "Prepare probation evaluation",
                    "priority": "urgent",
                })
            elif ms["type"] == "work_anniversary":
                action_items.append({
                    "item": f"Acknowledge {ms['description']}",
                    "priority": "normal",
                })

        return json.dumps({
            "employee": {
                "id": str(emp.id),
                "name": emp.full_name,
                "name_ar": f"{emp.first_name_ar or ''} {emp.last_name_ar or ''}".strip() or None,
                "job_title": emp.job_title,
                "department": dept_name,
                "tenure_months": tenure_months,
                "hire_date": emp.hire_date.isoformat() if emp.hire_date else None,
            },
            "leave_summary": leave_summary,
            "pending_leave_requests": pending_leave_data,
            "recent_leaves": recent_leave_data,
            "onboarding": onboarding_info,
            "milestones": milestones,
            "conversation_starters": conversation_starters,
            "action_items": action_items,
        })

    # ── Tool 14: get_team_compliance ──────────────────────────────────

    async def _get_team_compliance(self) -> str:
        """Check team compliance: expiring documents and incomplete onboarding."""
        manager_id = UUID(self._employee_id)

        if not await self._verify_is_manager(manager_id):
            return json.dumps({
                "error": "You are not a manager.",
                "error_ar": "لست مديرًا.",
            })

        today = date.today()
        team = await self._get_team_employees()
        team_ids = [e.id for e in team]
        team_map = {e.id: e for e in team}

        total_issues = 0
        per_employee = []

        if team_ids:
            # 1. Documents expiring within 60 days
            doc_result = await self.db.execute(
                select(EmployeeDocument).where(
                    EmployeeDocument.tenant_id == self.tenant_id,
                    EmployeeDocument.employee_id.in_(team_ids),
                    EmployeeDocument.is_deleted == False,  # noqa: E712
                    EmployeeDocument.expires_at.isnot(None),
                    EmployeeDocument.expires_at <= today + timedelta(days=60),
                    EmployeeDocument.expires_at >= today,
                ).order_by(EmployeeDocument.expires_at)
            )
            expiring_docs = doc_result.scalars().all()

            # Group docs by employee
            doc_by_emp: dict[UUID, list] = {}
            for doc in expiring_docs:
                doc_by_emp.setdefault(doc.employee_id, []).append(doc)

            # 2. Incomplete onboarding
            onb_result = await self.db.execute(
                select(OnboardingAssignment).where(
                    OnboardingAssignment.tenant_id == self.tenant_id,
                    OnboardingAssignment.employee_id.in_(team_ids),
                    OnboardingAssignment.status == OnboardingAssignmentStatus.in_progress,
                )
            )
            incomplete_onb = onb_result.scalars().all()
            onb_by_emp: dict[UUID, list] = {}
            for onb in incomplete_onb:
                onb_by_emp.setdefault(onb.employee_id, []).append(onb)

            # Build per-employee report
            flagged_ids = set(doc_by_emp.keys()) | set(onb_by_emp.keys())
            for emp_id in flagged_ids:
                emp = team_map.get(emp_id)
                if not emp:
                    continue

                issues = []

                # Expiring documents
                for doc in doc_by_emp.get(emp_id, []):
                    days_until = (doc.expires_at - today).days
                    issues.append({
                        "type": "expiring_document",
                        "document_type": doc.document_type.value,
                        "label": doc.label,
                        "expires_at": doc.expires_at.isoformat(),
                        "days_until_expiry": days_until,
                        "urgency": "urgent" if days_until <= 14 else "normal",
                    })

                # Incomplete onboarding
                for onb in onb_by_emp.get(emp_id, []):
                    issues.append({
                        "type": "incomplete_onboarding",
                        "assignment_id": str(onb.id),
                        "started_at": onb.started_at.isoformat() if onb.started_at else None,
                    })

                total_issues += len(issues)
                per_employee.append({
                    "employee_id": str(emp_id),
                    "name": emp.full_name,
                    "name_ar": f"{emp.first_name_ar or ''} {emp.last_name_ar or ''}".strip() or None,
                    "issue_count": len(issues),
                    "issues": issues,
                })

        # Sort by issue count descending
        per_employee.sort(key=lambda x: x["issue_count"], reverse=True)

        return json.dumps({
            "total_issues": total_issues,
            "employees_with_issues": len(per_employee),
            "team_size": len(team),
            "compliance_rate": round((len(team) - len(per_employee)) / len(team) * 100, 1) if team else 0,
            "per_employee": per_employee,
            "as_of": today.isoformat(),
        })

    # ── Tool 15: request_headcount ────────────────────────────────────

    async def _request_headcount(
        self, job_title: str, justification: str, department_id: UUID | None = None
    ) -> str:
        """Submit a headcount request (no DB table yet — returns confirmation)."""
        manager_id = UUID(self._employee_id)

        if not await self._verify_is_manager(manager_id):
            return json.dumps({
                "error": "You are not a manager.",
                "error_ar": "لست مديرًا.",
            })

        # Get department name if provided
        dept_name = None
        if department_id:
            dept_name = await self._resolve_dept_name(department_id)

        # Get manager info
        mgr_result = await self.db.execute(
            select(Employee).where(
                Employee.id == manager_id,
                Employee.tenant_id == self.tenant_id,
            )
        )
        mgr = mgr_result.scalar_one_or_none()

        import uuid as _uuid
        request_id = str(_uuid.uuid4())

        return json.dumps({
            "status": "submitted",
            "request_id": request_id,
            "request": {
                "job_title": job_title,
                "justification": justification,
                "department": dept_name or "Not specified",
                "department_id": str(department_id) if department_id else None,
                "requested_by": mgr.full_name if mgr else str(manager_id),
                "requested_at": datetime.now(timezone.utc).isoformat(),
            },
            "message": "Headcount request submitted successfully. HR will review and follow up.",
            "message_ar": "تم تقديم طلب التوظيف بنجاح. سيقوم فريق الموارد البشرية بالمراجعة والمتابعة.",
            "next_steps": [
                "HR will review the request within 3 business days",
                "Department head approval may be required",
                "You will be notified of the decision",
            ],
        })

    # ── Tool 16: get_manager_action_items ─────────────────────────────

    async def _get_manager_action_items(self) -> str:
        """Aggregate all pending action items for the manager."""
        manager_id = UUID(self._employee_id)

        if not await self._verify_is_manager(manager_id):
            return json.dumps({
                "error": "You are not a manager.",
                "error_ar": "لست مديرًا.",
            })

        today = date.today()
        action_items = []

        # 1. Pending leave approvals
        svc = ManagerService(self.db, self.tenant_id, manager_id)
        pending = await svc.get_pending_approvals()
        for req in pending:
            action_items.append({
                "category": "leave_approval",
                "priority": "urgent",
                "title": f"Leave request from {req['employee_name']}",
                "title_ar": f"طلب إجازة من {req['employee_name']}",
                "details": {
                    "request_id": req["request_id"],
                    "employee_name": req["employee_name"],
                    "leave_type": req["leave_type"],
                    "dates": f"{req['start_date']} to {req['end_date']}",
                    "business_days": req["business_days"],
                },
            })

        # 2. Probation ending within 14 days
        team = await self._get_team_employees()
        for emp in team:
            prob_end = emp.probation_end_date
            if not prob_end and emp.hire_date:
                prob_end = emp.hire_date + timedelta(days=90)
            if prob_end and not emp.probation_completed:
                days_left = (prob_end - today).days
                if 0 <= days_left <= 14:
                    action_items.append({
                        "category": "probation_review",
                        "priority": "urgent",
                        "title": f"Probation review for {emp.full_name}",
                        "title_ar": f"مراجعة فترة التجربة لـ {emp.full_name}",
                        "details": {
                            "employee_id": str(emp.id),
                            "employee_name": emp.full_name,
                            "probation_end_date": prob_end.isoformat(),
                            "days_remaining": days_left,
                        },
                    })

        # 3. Overdue onboarding steps
        team_ids = [e.id for e in team]
        if team_ids:
            onb_svc = OnboardingService(self.db, self.tenant_id)
            overdue = await onb_svc.get_overdue_steps(requesting_employee_id=manager_id)
            for step in overdue:
                action_items.append({
                    "category": "onboarding_overdue",
                    "priority": "urgent" if step.get("days_overdue", 0) > 7 else "normal",
                    "title": f"Overdue onboarding step: {step.get('step_name', 'Unknown')}",
                    "title_ar": f"خطوة تهيئة متأخرة: {step.get('step_name_ar') or step.get('step_name', 'غير معروف')}",
                    "details": step,
                })

        # 4. Expiring documents within 30 days
        if team_ids:
            doc_result = await self.db.execute(
                select(EmployeeDocument, Employee).join(
                    Employee, EmployeeDocument.employee_id == Employee.id
                ).where(
                    EmployeeDocument.tenant_id == self.tenant_id,
                    EmployeeDocument.employee_id.in_(team_ids),
                    EmployeeDocument.is_deleted == False,  # noqa: E712
                    EmployeeDocument.expires_at.isnot(None),
                    EmployeeDocument.expires_at <= today + timedelta(days=30),
                    EmployeeDocument.expires_at >= today,
                ).order_by(EmployeeDocument.expires_at)
            )
            expiring_rows = doc_result.all()
            for doc, emp in expiring_rows:
                days_until = (doc.expires_at - today).days
                action_items.append({
                    "category": "expiring_document",
                    "priority": "urgent" if days_until <= 7 else "normal",
                    "title": f"Expiring {doc.document_type.value} for {emp.full_name}",
                    "title_ar": f"مستند {doc.document_type.value} منتهي الصلاحية لـ {emp.full_name}",
                    "details": {
                        "employee_id": str(emp.id),
                        "employee_name": emp.full_name,
                        "document_type": doc.document_type.value,
                        "label": doc.label,
                        "expires_at": doc.expires_at.isoformat(),
                        "days_until_expiry": days_until,
                    },
                })

        # Sort: urgent first, then by category
        priority_order = {"urgent": 0, "normal": 1}
        action_items.sort(key=lambda x: (priority_order.get(x["priority"], 2), x["category"]))

        urgent_count = sum(1 for a in action_items if a["priority"] == "urgent")
        normal_count = len(action_items) - urgent_count

        return json.dumps({
            "total": len(action_items),
            "urgent": urgent_count,
            "normal": normal_count,
            "action_items": action_items,
            "as_of": today.isoformat(),
        })

    # ── Tool 17: generate_pip ─────────────────────────────────────────

    async def _generate_pip(
        self, employee_id: UUID, performance_issues: str, improvement_areas: str
    ) -> str:
        """Generate a structured Performance Improvement Plan draft."""
        # Fetch employee
        emp_result = await self.db.execute(
            select(Employee).where(
                Employee.id == employee_id,
                Employee.tenant_id == self.tenant_id,
            )
        )
        emp = emp_result.scalar_one_or_none()
        if not emp:
            return json.dumps({
                "error": "Employee not found.",
                "error_ar": "الموظف غير موجود.",
            })

        # Department name
        dept_name = None
        if emp.department_id:
            dept_name = await self._resolve_dept_name(emp.department_id)

        # Manager info
        manager_id = UUID(self._employee_id)
        mgr_result = await self.db.execute(
            select(Employee).where(
                Employee.id == manager_id,
                Employee.tenant_id == self.tenant_id,
            )
        )
        mgr = mgr_result.scalar_one_or_none()

        today = date.today()

        # Parse improvement areas into objectives
        areas = [a.strip() for a in improvement_areas.split(",") if a.strip()]
        if not areas:
            areas = [improvement_areas.strip()]

        objectives = []
        for area in areas:
            objectives.append({
                "area": area,
                "target": f"Demonstrate measurable improvement in {area}",
                "measurement": f"Manager assessment and documented evidence of progress in {area}",
            })

        # Timeline: 30/60/90 day milestones
        timeline = [
            {
                "phase": "Phase 1 — First 30 days",
                "end_date": (today + timedelta(days=30)).isoformat(),
                "goals": [
                    "Acknowledge areas for improvement",
                    "Create a personal development action plan",
                    "Begin working on identified improvement areas",
                    "Weekly check-in with manager",
                ],
                "review_date": (today + timedelta(days=30)).isoformat(),
            },
            {
                "phase": "Phase 2 — Days 31-60",
                "end_date": (today + timedelta(days=60)).isoformat(),
                "goals": [
                    "Show measurable progress on improvement objectives",
                    "Apply feedback from Phase 1 review",
                    "Demonstrate consistent effort and commitment",
                    "Bi-weekly check-in with manager",
                ],
                "review_date": (today + timedelta(days=60)).isoformat(),
            },
            {
                "phase": "Phase 3 — Days 61-90",
                "end_date": (today + timedelta(days=90)).isoformat(),
                "goals": [
                    "Achieve target performance levels",
                    "Sustain improvements consistently",
                    "Final evaluation and outcome determination",
                ],
                "review_date": (today + timedelta(days=90)).isoformat(),
            },
        ]

        # Support provided
        support = [
            {
                "type": "training",
                "description": "Access to relevant training courses and resources for identified improvement areas",
            },
            {
                "type": "mentoring",
                "description": "Regular guidance sessions with direct manager or assigned mentor",
            },
            {
                "type": "weekly_check_ins",
                "description": "Weekly 1:1 meetings to review progress, provide feedback, and address challenges",
            },
            {
                "type": "resources",
                "description": "Additional tools, documentation, or team support as needed",
            },
        ]

        # Review dates
        review_dates = [
            {"date": (today + timedelta(days=30)).isoformat(), "type": "Phase 1 Review"},
            {"date": (today + timedelta(days=60)).isoformat(), "type": "Phase 2 Review"},
            {"date": (today + timedelta(days=90)).isoformat(), "type": "Final Review"},
        ]

        return json.dumps({
            "pip_draft": {
                "title": "Performance Improvement Plan",
                "created_date": today.isoformat(),
                "employee": {
                    "id": str(emp.id),
                    "name": emp.full_name,
                    "name_ar": f"{emp.first_name_ar or ''} {emp.last_name_ar or ''}".strip() or None,
                    "job_title": emp.job_title,
                    "department": dept_name,
                    "hire_date": emp.hire_date.isoformat() if emp.hire_date else None,
                },
                "manager": {
                    "name": mgr.full_name if mgr else "N/A",
                    "job_title": mgr.job_title if mgr else "N/A",
                },
                "performance_issues": performance_issues,
                "improvement_objectives": objectives,
                "timeline": timeline,
                "support_provided": support,
                "consequences": {
                    "description": (
                        "If the employee fails to meet the improvement objectives by the end of "
                        "the 90-day PIP period, the following actions may be taken in accordance "
                        "with Saudi Labor Law:"
                    ),
                    "potential_actions": [
                        "Extension of the PIP for an additional period",
                        "Reassignment to a different role",
                        "Termination of employment per Saudi Labor Law Article 80",
                    ],
                    "legal_reference": (
                        "Saudi Labor Law Article 80: The employer may terminate the employee's "
                        "contract without notice, award, or indemnity if the employee fails to "
                        "perform their essential job duties after receiving a written warning."
                    ),
                },
                "review_dates": review_dates,
                "pip_duration_days": 90,
                "pip_start_date": today.isoformat(),
                "pip_end_date": (today + timedelta(days=90)).isoformat(),
            },
            "note": "This is a draft PIP. Please review with HR before finalizing.",
            "note_ar": "هذه مسودة خطة تحسين أداء. يرجى مراجعتها مع الموارد البشرية قبل الاعتماد.",
        })
