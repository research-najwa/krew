"""Waleed — Onboarding & Manager agent. Guides new hires through their first days,
checklists, and check-ins. Also provides manager tools for team oversight and leave approvals.

Patient, encouraging, and structured. Makes the onboarding journey feel seamless.
"""
import html
import json
import logging
from datetime import date, datetime, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import BaseAgent
from app.models.employee import Employee, EmployeeStatus, Department
from app.services.manager import ManagerService
from app.services.onboarding import OnboardingService
from app.services.notification import NotificationService


logger = logging.getLogger(__name__)


class WaleedAgent(BaseAgent):
    name = "Waleed"
    name_ar = "وليد"
    role = "Onboarding"
    division = "Shared Services"
    personality = (
        "Patient, encouraging, and structured. You guide new hires step by step, "
        "making their first days feel welcoming and organized. "
        "You celebrate small wins and never rush anyone through the process. "
        "For managers, you also help them oversee their team, review pending leave requests, "
        "and approve or reject them efficiently."
    )

    def get_tools(self) -> list[dict]:
        return [
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
            {
                "name": "get_onboarding_checklist",
                "description": "Retrieve the onboarding checklist for a new hire, including completed and pending items.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "employee_id": {
                            "type": "string",
                            "description": "The new hire's employee UUID",
                        },
                    },
                    "required": ["employee_id"],
                },
            },
            {
                "name": "send_checkin",
                "description": "Send a check-in message or survey to a new hire to see how they are doing.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "employee_id": {
                            "type": "string",
                            "description": "The new hire's employee UUID",
                        },
                        "checkin_type": {
                            "type": "string",
                            "enum": ["day_1", "week_1", "month_1", "month_3"],
                            "description": "The type/stage of check-in to send",
                        },
                        "message": {
                            "type": "string",
                            "description": "Optional custom message to include with the check-in",
                        },
                    },
                    "required": ["employee_id", "checkin_type"],
                },
            },
            {
                "name": "get_new_hire_info",
                "description": "Look up a new hire's profile, start date, assigned buddy, and onboarding status.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "employee_id": {
                            "type": "string",
                            "description": "The new hire's employee UUID",
                        },
                    },
                    "required": ["employee_id"],
                },
            },
            # ── Manager tools ──────────────────────────────────────
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
            # ── New high-impact tools ────────────────────────────────
            {
                "name": "complete_onboarding_step",
                "description": "Mark a specific onboarding step as completed for a new hire. Use get_onboarding_checklist first to get the step IDs.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "employee_id": {
                            "type": "string",
                            "description": "The new hire's employee UUID (used for verification)",
                        },
                        "assignment_id": {
                            "type": "string",
                            "description": "The onboarding assignment UUID",
                        },
                        "step_id": {
                            "type": "string",
                            "description": "The step UUID to mark as completed",
                        },
                    },
                    "required": ["employee_id", "assignment_id", "step_id"],
                },
            },
            {
                "name": "get_onboarding_dashboard",
                "description": "Get an overview of all in-progress onboarding assignments across the team — shows each new hire's progress, overdue steps, and completion percentage. Useful for managers and HR.",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                },
            },
            {
                "name": "get_overdue_onboarding_steps",
                "description": "List all overdue onboarding steps across the organization — shows which new hires have fallen behind and by how many days.",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                },
            },
            {
                "name": "get_team_leave_calendar",
                "description": "Show approved and pending leaves for the manager's team within a date range. Accepts any start_date and end_date in YYYY-MM-DD format, including past and future months (e.g. April 2026, next quarter). Helps managers plan around absences.",
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
            {
                "name": "assign_onboarding",
                "description": "Assign an onboarding checklist template to a new hire. If no template is specified, the tenant's default template is used.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "employee_id": {
                            "type": "string",
                            "description": "The new hire's employee UUID to assign onboarding to",
                        },
                        "template_id": {
                            "type": "string",
                            "description": "Optional: specific onboarding template UUID. If omitted, the default template is used.",
                        },
                    },
                    "required": ["employee_id"],
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
    # Proactive context — manager dashboard & employee onboarding
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
            else:
                await self._build_employee_context(emp_uuid, context_parts)
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
            parts.append(f"{len(new_hires)} new team member(s) in last 30 days: {', '.join(names)}. Offer to check onboarding.")

    async def _build_employee_context(self, emp_uuid: UUID, parts: list[str]) -> None:
        onb_svc = OnboardingService(self.db, self.tenant_id)
        onboarding = await onb_svc.get_employee_onboarding(emp_uuid)
        if not onboarding:
            return
        progress = onboarding["progress_pct"]
        total = onboarding["total_steps"]
        completed = onboarding["completed_steps"]
        overdue_count = sum(1 for s in onboarding["steps"] if s["is_overdue"])

        parts.append(f"Active onboarding: {completed}/{total} steps ({progress}%).")
        if overdue_count > 0:
            parts.append(f"{overdue_count} step(s) overdue. Gently remind and offer to help.")
        elif progress < 100:
            parts.append("All remaining steps on schedule. Encourage them.")
        if progress == 100:
            parts.append("Onboarding fully complete! Congratulate them.")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _ownership_error(self) -> str:
        """Return a standard ownership-denial JSON string."""
        return json.dumps({
            "error": "You can only access your own data.",
            "error_ar": "يمكنك الوصول إلى بياناتك فقط",
        })

    async def _verify_onboarding_access(self, target_employee_id: UUID) -> bool:
        """Check if current user can access target employee's onboarding.
        Returns True if self-access or manager of target.
        """
        if not self._employee_id:
            return False
        current_id = str(self._employee_id)
        target_id = str(target_employee_id)
        # Self-access
        if current_id == target_id:
            return True
        # Manager access
        result = await self.db.execute(
            select(Employee.manager_id).where(
                Employee.id == target_employee_id,
                Employee.tenant_id == self.tenant_id,
                Employee.status == EmployeeStatus.active,
            )
        )
        manager_id = result.scalar_one_or_none()
        return manager_id is not None and str(manager_id) == current_id

    async def _verify_manager_of(self, target_employee_id: UUID) -> bool:
        """Check if current user is the manager of the target employee. No self-access."""
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

    async def handle_tool_call(self, tool_name: str, tool_input: dict) -> str:
        # Validate all UUID fields upfront
        uuid_fields = ["employee_id", "request_id", "assignment_id", "step_id", "template_id"]
        for field in uuid_fields:
            if field in tool_input and tool_input[field] is not None:
                try:
                    UUID(tool_input[field])
                except (ValueError, AttributeError):
                    return json.dumps({
                        "error": f"Invalid {field} format. Please provide a valid UUID.",
                        "error_ar": f"صيغة {field} غير صحيحة. يرجى تقديم معرّف صالح.",
                    })

        if tool_name == "search_employee":
            return await self._search_employee(tool_input["query"])
        elif tool_name == "get_onboarding_checklist":
            employee_id = UUID(tool_input["employee_id"])
            if not await self._verify_onboarding_access(employee_id):
                return self._ownership_error()
            return await self._get_onboarding_checklist(employee_id)
        elif tool_name == "send_checkin":
            employee_id = UUID(tool_input["employee_id"])
            # Manager-only tool — must be the target's manager
            if not await self._verify_manager_of(employee_id):
                return self._ownership_error()
            return await self._send_checkin(
                employee_id,
                tool_input["checkin_type"],
                tool_input.get("message"),
            )
        elif tool_name == "get_new_hire_info":
            employee_id = UUID(tool_input["employee_id"])
            if not await self._verify_onboarding_access(employee_id):
                return self._ownership_error()
            return await self._get_new_hire_info(employee_id)
        # ── Manager tool dispatch ──────────────────────────────────
        elif tool_name == "view_team":
            employee_id = tool_input["employee_id"]
            if not self._employee_id or str(employee_id) != str(self._employee_id):
                return self._ownership_error()
            return await self._view_team(UUID(employee_id))
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
        # ── New high-impact tool dispatch ──────────────────────────
        elif tool_name == "complete_onboarding_step":
            employee_id = UUID(tool_input["employee_id"])
            if not await self._verify_onboarding_access(employee_id):
                return self._ownership_error()
            return await self._complete_onboarding_step(
                employee_id,
                UUID(tool_input["assignment_id"]),
                UUID(tool_input["step_id"]),
            )
        elif tool_name == "get_onboarding_dashboard":
            if not self._employee_id:
                return self._ownership_error()
            return await self._get_onboarding_dashboard()
        elif tool_name == "get_overdue_onboarding_steps":
            if not self._employee_id:
                return self._ownership_error()
            return await self._get_overdue_onboarding_steps()
        elif tool_name == "get_team_leave_calendar":
            employee_id = tool_input["employee_id"]
            if not self._employee_id or str(employee_id) != str(self._employee_id):
                return self._ownership_error()
            return await self._get_team_leave_calendar(
                UUID(employee_id),
                tool_input["start_date"],
                tool_input["end_date"],
            )
        elif tool_name == "get_team_headcount":
            employee_id = tool_input["employee_id"]
            if not self._employee_id or str(employee_id) != str(self._employee_id):
                return self._ownership_error()
            return await self._get_team_headcount(UUID(employee_id))
        elif tool_name == "assign_onboarding":
            employee_id = UUID(tool_input["employee_id"])
            # Manager-only tool — must be the target's manager
            if not await self._verify_manager_of(employee_id):
                return self._ownership_error()
            return await self._assign_onboarding(
                employee_id,
                UUID(tool_input["template_id"]) if tool_input.get("template_id") else None,
            )
        return json.dumps({"error": f"Unknown tool: {tool_name}"})

    # ------------------------------------------------------------------
    # Manager tool implementations
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Employee search
    # ------------------------------------------------------------------

    async def _search_employee(self, query: str) -> str:
        """Search employees by name or employee number within the tenant."""
        from sqlalchemy import or_, func as sa_func

        q = query.strip()
        # Split into words for matching first/last name separately
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

    # ------------------------------------------------------------------
    # Onboarding tool implementations
    # ------------------------------------------------------------------

    async def _get_onboarding_checklist(self, employee_id: UUID) -> str:
        svc = OnboardingService(self.db, self.tenant_id)
        result = await svc.get_employee_onboarding(employee_id)
        if not result:
            return json.dumps({
                "employee_id": str(employee_id),
                "message": "No active onboarding assignment found for this employee.",
                "message_ar": "لا يوجد برنامج تهيئة نشط لهذا الموظف.",
            })
        return json.dumps({
            "employee_id": str(employee_id),
            "assignment_id": result["assignment_id"],
            "progress_pct": result["progress_pct"],
            "completed_steps": result["completed_steps"],
            "total_steps": result["total_steps"],
            "status": result["status"].value if hasattr(result["status"], "value") else result["status"],
            "checklist": [
                {
                    "step_id": s["step_id"],
                    "item": s["name"],
                    "item_ar": s["name_ar"],
                    "status": s["status"],
                    "due_date": s["due_date"],
                    "is_overdue": s["is_overdue"],
                    "is_required": s["is_required"],
                    "completed_at": s["completed_at"],
                }
                for s in result["steps"]
            ],
        })

    async def _send_checkin(
        self, employee_id: UUID, checkin_type: str, message: str | None = None
    ) -> str:
        # Verify employee exists and belongs to tenant
        emp_result = await self.db.execute(
            select(Employee).where(
                Employee.id == employee_id,
                Employee.tenant_id == self.tenant_id,
            )
        )
        emp = emp_result.scalar_one_or_none()
        if not emp:
            return json.dumps({"error": "Employee not found.", "error_ar": "الموظف غير موجود."})

        checkin_titles = {
            "day_1": ("Day 1 Check-in", "متابعة اليوم الأول"),
            "week_1": ("Week 1 Check-in", "متابعة الأسبوع الأول"),
            "month_1": ("Month 1 Check-in", "متابعة الشهر الأول"),
            "month_3": ("Month 3 Check-in", "متابعة الشهر الثالث"),
        }
        title_en, title_ar = checkin_titles.get(checkin_type, ("Check-in", "متابعة"))

        default_messages = {
            "day_1": f"مرحبا {emp.first_name_ar or emp.first_name}! كيف كان يومك الأول؟ هل تحتاج أي مساعدة؟",
            "week_1": f"أهلا {emp.first_name_ar or emp.first_name}! أسبوع مر على انضمامك. كيف تسير الأمور؟",
            "month_1": f"مرحبا {emp.first_name_ar or emp.first_name}! شهر كامل معنا! كيف تقيّم تجربتك حتى الآن؟",
            "month_3": f"أهلا {emp.first_name_ar or emp.first_name}! 3 أشهر معنا. نود سماع رأيك عن فترة التجربة.",
        }
        body = message or default_messages.get(checkin_type, f"Check-in for {emp.first_name}")

        # Send as a notification
        notif_svc = NotificationService(self.db, self.tenant_id)
        await notif_svc.send(
            employee_id=employee_id,
            title=title_en,
            title_ar=title_ar,
            body=body,
            body_ar=body,
            category="onboarding",
        )

        return json.dumps({
            "status": "sent",
            "employee_id": str(employee_id),
            "employee_name": emp.full_name,
            "checkin_type": checkin_type,
            "message": body,
        })

    # ------------------------------------------------------------------
    # New high-impact tool implementations
    # ------------------------------------------------------------------

    async def _complete_onboarding_step(
        self, employee_id: UUID, assignment_id: UUID, step_id: UUID
    ) -> str:
        svc = OnboardingService(self.db, self.tenant_id)
        result = await svc.complete_step(
            assignment_id, step_id, completed_by=str(employee_id), employee_id=employee_id,
        )
        return json.dumps(result)

    async def _get_onboarding_dashboard(self) -> str:
        svc = OnboardingService(self.db, self.tenant_id)
        items = await svc.get_onboarding_dashboard(
            requesting_employee_id=UUID(self._employee_id) if self._employee_id else None,
        )
        if not items:
            return json.dumps({
                "message": "No in-progress onboarding assignments found.",
                "message_ar": "لا توجد برامج تهيئة قيد التنفيذ.",
                "count": 0,
            })
        return json.dumps({"count": len(items), "assignments": items})

    async def _get_overdue_onboarding_steps(self) -> str:
        svc = OnboardingService(self.db, self.tenant_id)
        items = await svc.get_overdue_steps(
            requesting_employee_id=UUID(self._employee_id) if self._employee_id else None,
        )
        if not items:
            return json.dumps({
                "message": "No overdue onboarding steps. Everyone is on track!",
                "message_ar": "لا توجد خطوات تهيئة متأخرة. الجميع على المسار الصحيح!",
                "count": 0,
            })
        return json.dumps({"count": len(items), "overdue_steps": items})

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

    async def _assign_onboarding(
        self, employee_id: UUID, template_id: UUID | None = None
    ) -> str:
        svc = OnboardingService(self.db, self.tenant_id)
        result = await svc.assign_to_employee(employee_id, template_id)
        return json.dumps(result)

    async def _get_new_hire_info(self, employee_id: UUID) -> str:
        emp_result = await self.db.execute(
            select(Employee).where(
                Employee.id == employee_id,
                Employee.tenant_id == self.tenant_id,
            )
        )
        emp = emp_result.scalar_one_or_none()
        if not emp:
            return json.dumps({"error": "Employee not found.", "error_ar": "الموظف غير موجود."})

        # Get department name
        dept_name = None
        if emp.department_id:
            dept_result = await self.db.execute(
                select(Department.name).where(Department.id == emp.department_id)
            )
            dept_name = dept_result.scalar_one_or_none()

        # Get manager name
        manager_name = None
        if emp.manager_id:
            mgr_result = await self.db.execute(
                select(Employee.first_name, Employee.last_name).where(
                    Employee.id == emp.manager_id,
                    Employee.tenant_id == self.tenant_id,
                )
            )
            mgr = mgr_result.one_or_none()
            if mgr:
                manager_name = f"{mgr[0]} {mgr[1]}"

        # Calculate days since hire
        days_since_start = None
        if emp.hire_date:
            days_since_start = (date.today() - emp.hire_date).days

        # Get onboarding status
        svc = OnboardingService(self.db, self.tenant_id)
        onboarding = await svc.get_employee_onboarding(employee_id)

        return json.dumps({
            "employee_id": str(emp.id),
            "name": emp.full_name,
            "name_ar": f"{emp.first_name_ar or ''} {emp.last_name_ar or ''}".strip() or None,
            "employee_number": emp.employee_number,
            "job_title": emp.job_title,
            "department": dept_name,
            "hire_date": emp.hire_date.isoformat() if emp.hire_date else None,
            "days_since_start": days_since_start,
            "manager": manager_name,
            "status": emp.status.value,
            "onboarding_status": onboarding["status"].value if onboarding and hasattr(onboarding.get("status", ""), "value") else (onboarding["status"] if onboarding else "no_assignment"),
            "onboarding_progress_pct": onboarding["progress_pct"] if onboarding else None,
        })
