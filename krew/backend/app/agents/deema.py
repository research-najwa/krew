"""Deema — Employee Services agent. Handles leave, benefits, policy questions, general HR help.

This is the most-used agent. She's the first point of contact for most employees.
"""
import html
import json
import re
from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import BaseAgent
from app.models.employee import Employee, Department
from app.models.leave import LeaveBalance, LeaveRequest, LeaveType, LeaveStatus
from app.models.escalation import (
    EscalationTicket,
    EscalationCategory,
    EscalationUrgency,
    EscalationStatus,
)
from app.models.conversation import Conversation, ConversationStatus
from app.models.payslip import Payslip
from app.services.leave import check_and_submit_leave, cancel_leave_request as svc_cancel_leave
from app.models.employee_document import EmployeeDocument, DocumentType, EXPIRING_DOCUMENT_TYPES


class DeemaAgent(BaseAgent):
    name = "Deema"
    name_ar = "ديمة"
    role = "Employee Services"
    division = "Shared Services"
    personality = (
        "Warm, efficient, and empathetic. You're the go-to person for any HR question. "
        "You speak clearly and make bureaucratic processes feel simple. "
        "You handle leave requests, benefits questions, and policy lookups."
    )

    def _get_scope_rules(self) -> str:
        return """
Scope boundaries — STRICTLY enforce these:
- You handle: leave, balances, payslips, employee profiles, company policies, HR documents, escalations, team info for managers.
- You do NOT handle: recruitment, job postings, candidates, interviews, hiring, onboarding new hires, job descriptions, salary benchmarking, or anything about open positions.
- If someone asks about recruitment, job openings, candidates, hiring, or salary benchmarking, tell them this is handled by Mohammad (محمد) the recruitment specialist, and suggest they say "switch to mohammad" or "كلم محمد".
- Never attempt to answer recruitment questions yourself, even if you think you know the answer."""

    def get_tools(self) -> list[dict]:
        return [
            {
                "name": "get_leave_balance",
                "description": "Check an employee's remaining leave balance by type (annual, sick, etc.)",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "employee_id": {
                            "type": "string",
                            "description": "The employee's UUID",
                        },
                        "leave_type": {
                            "type": "string",
                            "enum": ["annual", "sick", "emergency", "maternity", "paternity", "hajj", "bereavement", "unpaid"],
                            "description": "Type of leave to check",
                        },
                    },
                    "required": ["employee_id"],
                },
            },
            {
                "name": "submit_leave_request",
                "description": "Submit a leave request on behalf of an employee",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "employee_id": {"type": "string"},
                        "leave_type": {
                            "type": "string",
                            "enum": ["annual", "sick", "emergency", "maternity", "paternity", "hajj", "bereavement", "unpaid"],
                        },
                        "start_date": {
                            "type": "string",
                            "description": "Start date in YYYY-MM-DD format",
                        },
                        "end_date": {
                            "type": "string",
                            "description": "End date in YYYY-MM-DD format",
                        },
                        "reason": {"type": "string"},
                    },
                    "required": ["employee_id", "leave_type", "start_date", "end_date"],
                },
            },
            {
                "name": "get_employee_info",
                "description": "Look up an employee's profile information",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "employee_id": {"type": "string"},
                    },
                    "required": ["employee_id"],
                },
            },
            {
                "name": "get_leave_requests",
                "description": "List an employee's leave requests, optionally filtered by status.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "employee_id": {
                            "type": "string",
                            "description": "The employee's UUID",
                        },
                        "status": {
                            "type": "string",
                            "enum": ["pending", "approved", "rejected", "cancelled"],
                            "description": "Filter by request status (optional — omit for all)",
                        },
                    },
                    "required": ["employee_id"],
                },
            },
            {
                "name": "cancel_leave_request",
                "description": "Cancel a pending leave request and restore the leave balance.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "employee_id": {
                            "type": "string",
                            "description": "The employee's UUID",
                        },
                        "request_id": {
                            "type": "string",
                            "description": "The leave request UUID to cancel",
                        },
                    },
                    "required": ["employee_id", "request_id"],
                },
            },
            {
                "name": "search_policy",
                "description": "Search company policies by topic. Use this when an employee asks about rules, entitlements, or procedures.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The policy topic or question to search for",
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "update_employee_info",
                "description": "Update an employee's contact information and preferences. Only phone, whatsapp_number, work_location, preferred_language, and preferred_channel can be updated.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "employee_id": {"type": "string"},
                        "phone": {
                            "type": "string",
                            "description": "New phone number (e.g., +966501234567)",
                        },
                        "whatsapp_number": {
                            "type": "string",
                            "description": "New WhatsApp number (e.g., +966501234567)",
                        },
                        "work_location": {
                            "type": "string",
                            "description": "Office name or city",
                        },
                        "preferred_language": {
                            "type": "string",
                            "enum": ["ar", "en"],
                            "description": "Preferred language",
                        },
                        "preferred_channel": {
                            "type": "string",
                            "enum": ["whatsapp", "slack", "teams", "email"],
                            "description": "Preferred communication channel",
                        },
                    },
                    "required": ["employee_id"],
                },
            },
            {
                "name": "get_team_calendar",
                "description": "Show who in the employee's department is on approved leave during a given period.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "employee_id": {
                            "type": "string",
                            "description": "The employee's UUID (used to determine their department)",
                        },
                        "period": {
                            "type": "string",
                            "enum": ["this_week", "next_week", "this_month"],
                            "description": "Time period to check (default: this_week)",
                        },
                    },
                    "required": ["employee_id"],
                },
            },
            {
                "name": "get_escalation_status",
                "description": "Look up the status of an escalation ticket by its ticket ID. Use when an employee asks about a previous escalation.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "ticket_id": {
                            "type": "string",
                            "description": "The escalation ticket UUID",
                        },
                    },
                    "required": ["ticket_id"],
                },
            },
            {
                "name": "escalate_to_human",
                "description": "Escalate the conversation to a human HR operator when you cannot resolve the issue or the employee explicitly requests it.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "reason": {
                            "type": "string",
                            "description": "Why this is being escalated",
                        },
                        "category": {
                            "type": "string",
                            "enum": ["employee_request", "agent_failure", "sensitive_topic", "policy_gap"],
                            "description": "Category of escalation",
                        },
                        "urgency": {
                            "type": "string",
                            "enum": ["low", "medium", "high"],
                            "description": "Urgency level",
                        },
                        "summary": {
                            "type": "string",
                            "description": "Brief summary of the conversation context for the HR operator",
                        },
                    },
                    "required": ["reason", "category", "summary"],
                },
            },
            {
                "name": "list_my_escalations",
                "description": "List all escalation tickets for the current employee. Shows open, assigned, and resolved tickets sorted by most recent. Use when the employee asks about their requests/tickets/\u0637\u0644\u0628\u0627\u062a\u064a/\u062a\u0630\u0627\u0643\u0631\u064a.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "employee_id": {
                            "type": "string",
                            "description": "The employee's UUID",
                        },
                        "status": {
                            "type": "string",
                            "enum": ["open", "assigned", "resolved"],
                            "description": "Filter by ticket status (optional — omit for all)",
                        },
                    },
                    "required": ["employee_id"],
                },
            },
            {
                "name": "list_my_leave_requests",
                "description": "List the employee's leave requests with full approval details: who approved/rejected, when, and rejection reasons. Use when the employee asks about their leave history or approval status. More detailed than get_leave_requests.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "employee_id": {
                            "type": "string",
                            "description": "The employee's UUID",
                        },
                        "status": {
                            "type": "string",
                            "enum": ["pending", "approved", "rejected", "cancelled"],
                            "description": "Filter by status (optional — omit for all)",
                        },
                    },
                    "required": ["employee_id"],
                },
            },
            {
                "name": "view_my_profile",
                "description": "View the employee's full profile information (name, email, phone, job title, department, hire date, employee number, work mode, contract type). Use when the employee asks about their profile or personal info.",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
            {
                "name": "view_salary_info",
                "description": "View the employee's basic salary information. Sensitive data — only accessible by the employee themselves. Use when the employee asks about their salary/راتبي.",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
            {
                "name": "view_vacation_balance",
                "description": "View detailed leave balance breakdown by type (annual, sick, etc.) with used and remaining days for the current year. Use when the employee asks 'what is my vacation balance' or 'كم رصيد إجازاتي'.",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
            {
                "name": "view_contract_info",
                "description": "View the employee's contract details: contract type, hire date, probation status, work mode, WFH days. Use when the employee asks about their contract or probation.",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
            {
                "name": "view_payslip",
                "description": "View a payslip for a given month and year. If no payslip record exists, computes an estimated stub from salary using Saudi formulas. Use when the employee asks about their payslip/كشف راتب.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "year": {
                            "type": "integer",
                            "description": "The year of the payslip (e.g. 2026). Defaults to current year.",
                        },
                        "month": {
                            "type": "integer",
                            "description": "The month of the payslip (1-12). Defaults to current month.",
                        },
                    },
                    "required": [],
                },
            },
            {
                "name": "list_my_documents",
                "description": "List the employee's HR documents (national ID, iqama, contract, passport, etc.) with type, verification status, and expiry date. Use when the employee asks about their documents/مستنداتي/وثائقي.",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
            {
                "name": "check_expiring_documents",
                "description": "Check if the employee has any HR documents expiring within the next 60 days. Use when the employee asks about expiring documents or renewals/تجديد/انتهاء صلاحية.",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        ]

    def _ownership_error(self) -> str:
        """Return a standard ownership-denial JSON string."""
        return json.dumps({
            "error": "You can only access your own data.",
            "error_ar": "يمكنك الوصول إلى بياناتك فقط",
        })

    async def handle_tool_call(self, tool_name: str, tool_input: dict) -> str:
        if tool_name == "get_leave_balance":
            employee_id = tool_input["employee_id"]
            if not self._employee_id or str(employee_id) != str(self._employee_id):
                return self._ownership_error()
            return await self._get_leave_balance(
                UUID(employee_id),
                tool_input.get("leave_type"),
            )
        elif tool_name == "submit_leave_request":
            employee_id = tool_input["employee_id"]
            if not self._employee_id or str(employee_id) != str(self._employee_id):
                return self._ownership_error()
            return await self._submit_leave_request(tool_input)
        elif tool_name == "get_employee_info":
            requested_id = tool_input["employee_id"]
            if not self._employee_id or str(requested_id) != str(self._employee_id):
                return self._ownership_error()
            return await self._get_employee_info(UUID(requested_id))
        elif tool_name == "get_leave_requests":
            employee_id = tool_input["employee_id"]
            if not self._employee_id or str(employee_id) != str(self._employee_id):
                return self._ownership_error()
            return await self._get_leave_requests(
                UUID(employee_id),
                tool_input.get("status"),
            )
        elif tool_name == "cancel_leave_request":
            employee_id = tool_input["employee_id"]
            if not self._employee_id or str(employee_id) != str(self._employee_id):
                return self._ownership_error()
            return await self._cancel_leave_request(
                UUID(employee_id),
                UUID(tool_input["request_id"]),
            )
        elif tool_name == "search_policy":
            return await self._search_policy(tool_input["query"])
        elif tool_name == "update_employee_info":
            employee_id = tool_input["employee_id"]
            if not self._employee_id or str(employee_id) != str(self._employee_id):
                return self._ownership_error()
            return await self._update_employee_info(
                UUID(employee_id),
                tool_input,
            )
        elif tool_name == "get_team_calendar":
            employee_id = tool_input["employee_id"]
            if not self._employee_id or str(employee_id) != str(self._employee_id):
                return self._ownership_error()
            return await self._get_team_calendar(
                UUID(employee_id),
                tool_input.get("period", "this_week"),
            )
        elif tool_name == "get_escalation_status":
            return await self._get_escalation_status(tool_input["ticket_id"])
        elif tool_name == "escalate_to_human":
            return await self._escalate_to_human(tool_input)
        elif tool_name == "list_my_escalations":
            employee_id = tool_input["employee_id"]
            if not self._employee_id or str(employee_id) != str(self._employee_id):
                return self._ownership_error()
            return await self._list_my_escalations(
                UUID(employee_id),
                tool_input.get("status"),
            )
        elif tool_name == "list_my_leave_requests":
            employee_id = tool_input["employee_id"]
            if not self._employee_id or str(employee_id) != str(self._employee_id):
                return self._ownership_error()
            return await self._list_my_leave_requests(
                UUID(employee_id),
                tool_input.get("status"),
            )
        elif tool_name == "view_my_profile":
            if not self._employee_id:
                return self._ownership_error()
            return await self._view_my_profile(UUID(self._employee_id))
        elif tool_name == "view_salary_info":
            if not self._employee_id:
                return self._ownership_error()
            return await self._view_salary_info(UUID(self._employee_id))
        elif tool_name == "view_vacation_balance":
            if not self._employee_id:
                return self._ownership_error()
            return await self._view_vacation_balance(UUID(self._employee_id))
        elif tool_name == "view_contract_info":
            if not self._employee_id:
                return self._ownership_error()
            return await self._view_contract_info(UUID(self._employee_id))
        elif tool_name == "view_payslip":
            if not self._employee_id:
                return self._ownership_error()
            return await self._view_payslip(
                UUID(self._employee_id),
                tool_input.get("year"),
                tool_input.get("month"),
            )
        elif tool_name == "list_my_documents":
            if not self._employee_id:
                return self._ownership_error()
            return await self._list_my_documents(UUID(self._employee_id))
        elif tool_name == "check_expiring_documents":
            if not self._employee_id:
                return self._ownership_error()
            return await self._check_expiring_documents(UUID(self._employee_id))
        return json.dumps({"error": f"Unknown tool: {tool_name}"})

    # ── Helpers ─────────────────────────────────────────────────

    async def _verify_employee(self, employee_id: UUID) -> Employee | None:
        """Verify the employee exists and belongs to this tenant."""
        result = await self.db.execute(
            select(Employee).where(
                Employee.id == employee_id,
                Employee.tenant_id == self.tenant_id,
            )
        )
        return result.scalar_one_or_none()

    # ── Tool implementations ───────────────────────────────────

    async def _get_leave_balance(
        self, employee_id: UUID, leave_type: str | None = None
    ) -> str:
        emp = await self._verify_employee(employee_id)
        if not emp:
            return json.dumps({"error": "Employee not found"})

        query = select(LeaveBalance).where(
            LeaveBalance.employee_id == employee_id,
            LeaveBalance.year == date.today().year,
        )
        if leave_type:
            query = query.where(LeaveBalance.leave_type == LeaveType(leave_type))

        result = await self.db.execute(query)
        balances = result.scalars().all()

        if not balances:
            if leave_type:
                return json.dumps({
                    "message": f"This employee is not eligible for {leave_type} leave. No balance exists for this leave type.",
                    "leave_type": leave_type,
                    "eligible": False,
                })
            return json.dumps({"message": "No leave balances found for this employee."})

        return json.dumps([
            {
                "type": b.leave_type.value,
                "total": b.total_days,
                "used": b.used_days,
                "remaining": b.remaining_days,
            }
            for b in balances
        ])

    async def _submit_leave_request(self, data: dict) -> str:
        employee_id = UUID(data["employee_id"])
        emp = await self._verify_employee(employee_id)
        if not emp:
            return json.dumps({"error": "Employee not found"})

        start = date.fromisoformat(data["start_date"])
        end = date.fromisoformat(data["end_date"])

        result = await check_and_submit_leave(
            db=self.db,
            employee_id=employee_id,
            leave_type=data["leave_type"],
            start_date=start,
            end_date=end,
            reason=data.get("reason"),
            channel="web",
            agent="deema",
            tenant_id=self.tenant_id,
        )

        if result["success"]:
            approval_decision = result.get("approval_decision", "pending_manager")
            auto_approved = result.get("auto_approved", False)

            if auto_approved:
                status_label = "auto_approved"
            else:
                status_label = "pending_approval"

            response_payload = {
                "status": status_label,
                "request_id": str(result["request_id"]),
                "start_date": data["start_date"],
                "end_date": data["end_date"],
                "business_days": result["business_days"],
                "leave_type": data["leave_type"],
                "approval_decision": approval_decision,
                "auto_approved": auto_approved,
                "message": result["message"],
                "message_ar": result["message_ar"],
            }

            # Include labor law warnings if any
            if result.get("warnings"):
                response_payload["warnings"] = result["warnings"]

            return json.dumps(response_payload)
        else:
            error_payload = {"error": result["message"], "error_ar": result.get("message_ar", "")}
            if "conflict_request_id" in result:
                error_payload["conflict_request_id"] = result["conflict_request_id"]
            if "labor_law_article" in result:
                error_payload["labor_law_article"] = result["labor_law_article"]
            return json.dumps(error_payload)

    async def _get_employee_info(self, employee_id: UUID) -> str:
        result = await self.db.execute(
            select(Employee).where(
                Employee.id == employee_id,
                Employee.tenant_id == self.tenant_id,
            )
        )
        emp = result.scalar_one_or_none()

        if not emp:
            return json.dumps({"error": "Employee not found"})

        # Get department name
        dept_name = None
        if emp.department_id:
            dept_result = await self.db.execute(
                select(Department).where(Department.id == emp.department_id)
            )
            dept = dept_result.scalar_one_or_none()
            if dept:
                dept_name = dept.name

        return json.dumps({
            "name": emp.full_name,
            "email": emp.email,
            "phone": emp.phone,
            "whatsapp_number": emp.whatsapp_number,
            "job_title": emp.job_title,
            "department": dept_name,
            "hire_date": emp.hire_date.isoformat(),
            "status": emp.status.value,
            "work_mode": emp.work_mode.value if emp.work_mode else None,
            "work_location": emp.work_location,
            "preferred_language": emp.preferred_language,
            "preferred_channel": emp.preferred_channel,
        })

    async def _get_leave_requests(
        self, employee_id: UUID, status: str | None = None
    ) -> str:
        emp = await self._verify_employee(employee_id)
        if not emp:
            return json.dumps({"error": "Employee not found"})

        query = select(LeaveRequest).where(
            LeaveRequest.employee_id == employee_id,
        ).order_by(LeaveRequest.created_at.desc())

        if status:
            query = query.where(LeaveRequest.status == LeaveStatus(status))

        result = await self.db.execute(query)
        requests = result.scalars().all()

        if not requests:
            return json.dumps({"message": "No leave requests found.", "count": 0})

        return json.dumps({
            "count": len(requests),
            "requests": [
                {
                    "id": str(r.id),
                    "leave_type": r.leave_type.value,
                    "start_date": r.start_date.isoformat(),
                    "end_date": r.end_date.isoformat(),
                    "business_days": r.business_days,
                    "status": r.status.value,
                    "reason": r.reason,
                    "created_at": r.created_at.isoformat(),
                }
                for r in requests
            ],
        })

    async def _cancel_leave_request(
        self, employee_id: UUID, request_id: UUID
    ) -> str:
        emp = await self._verify_employee(employee_id)
        if not emp:
            return json.dumps({"error": "Employee not found"})

        result = await svc_cancel_leave(
            db=self.db,
            employee_id=employee_id,
            request_id=request_id,
            tenant_id=self.tenant_id,
        )

        if result["success"]:
            return json.dumps({
                "status": "cancelled",
                "request_id": result["request_id"],
                "leave_type": result["leave_type"],
                "business_days_restored": result["business_days_restored"],
                "remaining_balance": result["remaining_balance"],
                "message": result["message"],
                "message_ar": result["message_ar"],
            })
        else:
            return json.dumps({
                "error": result["message"],
                "error_ar": result["message_ar"],
            })

    async def _search_policy(self, query: str) -> str:
        policy_text = await self.retriever.search(query, top_k=3)

        if not policy_text:
            return json.dumps({
                "found": False,
                "message": "No matching policies found for this query.",
            })

        return json.dumps({
            "found": True,
            "policy_text": policy_text,
        })

    async def _update_employee_info(
        self, employee_id: UUID, data: dict
    ) -> str:
        ALLOWED_FIELDS = {"phone", "whatsapp_number", "work_location", "preferred_language", "preferred_channel"}

        updates = {k: v for k, v in data.items() if k in ALLOWED_FIELDS and v is not None}

        if not updates:
            return json.dumps({
                "error": "No valid fields to update. You can update: phone, whatsapp_number, work_location, preferred_language, preferred_channel.",
            })

        phone_pattern = re.compile(r"^\+\d{10,15}$")
        for field in ("phone", "whatsapp_number"):
            if field in updates and not phone_pattern.match(updates[field]):
                return json.dumps({
                    "error": f"Invalid {field} format. Expected international format like +966501234567.",
                    "provided": updates[field],
                })

        result = await self.db.execute(
            select(Employee).where(
                Employee.id == employee_id,
                Employee.tenant_id == self.tenant_id,
            )
        )
        emp = result.scalar_one_or_none()

        if not emp:
            return json.dumps({"error": "Employee not found."})

        for field, value in updates.items():
            setattr(emp, field, value)

        await self.db.flush()

        return json.dumps({
            "status": "updated",
            "updated_fields": list(updates.keys()),
            "new_values": updates,
        })

    async def _get_team_calendar(
        self, employee_id: UUID, period: str = "this_week"
    ) -> str:
        emp_result = await self.db.execute(
            select(Employee).where(
                Employee.id == employee_id,
                Employee.tenant_id == self.tenant_id,
            )
        )
        emp = emp_result.scalar_one_or_none()

        if not emp:
            return json.dumps({"error": "Employee not found."})

        if not emp.department_id:
            return json.dumps({"error": "Employee is not assigned to a department."})

        today = date.today()

        if period == "this_week":
            days_since_sunday = (today.weekday() + 1) % 7
            period_start = today - timedelta(days=days_since_sunday)
            period_end = period_start + timedelta(days=4)  # Sun-Thu
        elif period == "next_week":
            days_since_sunday = (today.weekday() + 1) % 7
            period_start = today - timedelta(days=days_since_sunday) + timedelta(days=7)
            period_end = period_start + timedelta(days=4)
        elif period == "this_month":
            period_start = today.replace(day=1)
            if today.month == 12:
                period_end = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                period_end = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
        else:
            period_start = today
            period_end = today + timedelta(days=6)

        query = (
            select(LeaveRequest, Employee)
            .join(Employee, LeaveRequest.employee_id == Employee.id)
            .where(
                Employee.department_id == emp.department_id,
                Employee.tenant_id == self.tenant_id,
                LeaveRequest.status == LeaveStatus.approved,
                LeaveRequest.start_date <= period_end,
                LeaveRequest.end_date >= period_start,
            )
            .order_by(LeaveRequest.start_date)
        )

        result = await self.db.execute(query)
        rows = result.all()

        if not rows:
            return json.dumps({
                "period_start": period_start.isoformat(),
                "period_end": period_end.isoformat(),
                "message": "No one in your department is on leave during this period.",
                "on_leave": [],
            })

        # Privacy: show specific leave type only for the requesting employee's own entries;
        # for colleagues, show generic "on leave" to avoid leaking sensitive info (sick, maternity).
        on_leave_entries = []
        for lr, e in rows:
            is_self = str(e.id) == str(employee_id)
            on_leave_entries.append({
                "name": e.full_name,
                "leave_type": lr.leave_type.value if is_self else "leave",
                "start_date": lr.start_date.isoformat(),
                "end_date": lr.end_date.isoformat(),
                "business_days": lr.business_days,
            })

        return json.dumps({
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "on_leave": on_leave_entries,
        })

    async def _get_escalation_status(self, ticket_id: str) -> str:
        """Look up an escalation ticket by ID — only if it belongs to the current employee."""
        try:
            tid = UUID(ticket_id)
        except ValueError:
            return json.dumps({"error": "Invalid ticket ID format."})

        result = await self.db.execute(
            select(EscalationTicket).where(
                EscalationTicket.id == tid,
                EscalationTicket.tenant_id == self.tenant_id,
            )
        )
        ticket = result.scalar_one_or_none()
        if not ticket:
            return json.dumps({
                "error": "Ticket not found.",
                "error_ar": "لم يتم العثور على التذكرة.",
            })

        # Only allow employee to see their own tickets (deny-by-default)
        if not self._employee_id or str(ticket.employee_id) != str(self._employee_id):
            return json.dumps({
                "error": "You can only view your own escalation tickets.",
                "error_ar": "يمكنك فقط عرض تذاكر التصعيد الخاصة بك.",
            })

        return json.dumps({
            "ticket_id": str(ticket.id),
            "status": ticket.status.value,
            "category": ticket.category.value,
            "urgency": ticket.urgency.value,
            "reason": ticket.reason,
            "assigned_to": ticket.assigned_to,
            "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
            "resolved_at": ticket.resolved_at.isoformat() if ticket.resolved_at else None,
        })

    async def _escalate_to_human(self, data: dict) -> str:
        if not self._employee_id:
            return json.dumps({
                "error": "Escalation requires employee context. Cannot escalate without a known employee.",
                "error_ar": "التصعيد يتطلب سياق الموظف. لا يمكن التصعيد بدون موظف معروف.",
            })

        ticket = EscalationTicket(
            tenant_id=self.tenant_id,
            conversation_id=self._conversation_id if self._conversation_id else None,
            employee_id=UUID(self._employee_id) if self._employee_id else None,
            agent_name=self.name.lower(),
            category=EscalationCategory(data["category"]),
            urgency=EscalationUrgency(data.get("urgency", "medium")),
            reason=data["reason"],
            summary=data.get("summary"),
        )
        self.db.add(ticket)

        # Mark conversation as escalated if we have a conversation_id
        if self._conversation_id:
            conv_result = await self.db.execute(
                select(Conversation).where(Conversation.id == self._conversation_id)
            )
            conv = conv_result.scalar_one_or_none()
            if conv:
                conv.status = ConversationStatus.escalated

        await self.db.commit()
        await self.db.refresh(ticket)

        return json.dumps({
            "status": "escalated",
            "ticket_id": str(ticket.id),
            "message": (
                "Your request has been escalated to a human HR specialist. "
                "They will review your case and respond shortly. "
                f"Ticket ID: {ticket.id}"
            ),
            "message_ar": (
                "تم تصعيد طلبك إلى أخصائي موارد بشرية. "
                "سيقومون بمراجعة حالتك والرد عليك قريبا. "
                f"رقم التذكرة: {ticket.id}"
            ),
        })

    # ── C4: Ticket Tracking Tools ──────────────────────────────

    async def _list_my_escalations(
        self, employee_id: UUID, status: str | None = None
    ) -> str:
        """List all escalation tickets belonging to this employee."""
        # Ownership check (deny-by-default)
        if not self._employee_id or str(employee_id) != str(self._employee_id):
            return json.dumps({
                "error": "You can only view your own tickets.",
                "error_ar": "يمكنك فقط عرض تذاكرك الخاصة.",
            })

        emp = await self._verify_employee(employee_id)
        if not emp:
            return json.dumps({"error": "Employee not found"})

        query = (
            select(EscalationTicket)
            .where(
                EscalationTicket.tenant_id == self.tenant_id,
                EscalationTicket.employee_id == employee_id,
            )
            .order_by(EscalationTicket.created_at.desc())
            .limit(20)
        )
        if status:
            query = query.where(
                EscalationTicket.status == EscalationStatus(status)
            )

        result = await self.db.execute(query)
        tickets = result.scalars().all()

        if not tickets:
            return json.dumps({
                "message": "No escalation tickets found.",
                "message_ar": "\u0644\u0645 \u064a\u062a\u0645 \u0627\u0644\u0639\u062b\u0648\u0631 \u0639\u0644\u0649 \u062a\u0630\u0627\u0643\u0631 \u062a\u0635\u0639\u064a\u062f.",
                "count": 0,
            })

        STATUS_AR = {"open": "\u0645\u0641\u062a\u0648\u062d\u0629", "assigned": "\u0642\u064a\u062f \u0627\u0644\u0645\u0639\u0627\u0644\u062c\u0629", "resolved": "\u0645\u062d\u0644\u0648\u0644\u0629"}
        CATEGORY_AR = {
            "employee_request": "\u0637\u0644\u0628 \u0645\u0648\u0638\u0641",
            "agent_failure": "\u062e\u0637\u0623 \u0646\u0638\u0627\u0645",
            "sensitive_topic": "\u0645\u0648\u0636\u0648\u0639 \u062d\u0633\u0627\u0633",
            "policy_gap": "\u0641\u062c\u0648\u0629 \u0641\u064a \u0627\u0644\u0633\u064a\u0627\u0633\u0629",
        }

        return json.dumps({
            "count": len(tickets),
            "tickets": [
                {
                    "ticket_id": str(t.id),
                    "status": t.status.value,
                    "status_ar": STATUS_AR.get(t.status.value, t.status.value),
                    "category": t.category.value,
                    "category_ar": CATEGORY_AR.get(t.category.value, t.category.value),
                    "urgency": t.urgency.value,
                    "reason": t.reason,
                    "summary": t.summary,
                    "assigned_to": t.assigned_to,
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                    "resolved_at": t.resolved_at.isoformat() if t.resolved_at else None,
                }
                for t in tickets
            ],
        })

    async def _list_my_leave_requests(
        self, employee_id: UUID, status: str | None = None
    ) -> str:
        """Enhanced leave request list with approval details."""
        # Ownership check (deny-by-default)
        if not self._employee_id or str(employee_id) != str(self._employee_id):
            return json.dumps({
                "error": "You can only view your own leave requests.",
                "error_ar": "\u064a\u0645\u0643\u0646\u0643 \u0641\u0642\u0637 \u0639\u0631\u0636 \u0637\u0644\u0628\u0627\u062a \u0625\u062c\u0627\u0632\u062a\u0643 \u0627\u0644\u062e\u0627\u0635\u0629.",
            })

        emp = await self._verify_employee(employee_id)
        if not emp:
            return json.dumps({"error": "Employee not found"})

        query = (
            select(LeaveRequest)
            .where(LeaveRequest.employee_id == employee_id)
            .order_by(LeaveRequest.created_at.desc())
            .limit(20)
        )
        if status:
            query = query.where(LeaveRequest.status == LeaveStatus(status))

        result = await self.db.execute(query)
        requests = result.scalars().all()

        if not requests:
            return json.dumps({
                "message": "No leave requests found.",
                "message_ar": "\u0644\u0645 \u064a\u062a\u0645 \u0627\u0644\u0639\u062b\u0648\u0631 \u0639\u0644\u0649 \u0637\u0644\u0628\u0627\u062a \u0625\u062c\u0627\u0632\u0629.",
                "count": 0,
            })

        STATUS_AR = {
            "pending": "\u0645\u0639\u0644\u0642\u0629", "approved": "\u0645\u0648\u0627\u0641\u0642 \u0639\u0644\u064a\u0647\u0627",
            "rejected": "\u0645\u0631\u0641\u0648\u0636\u0629", "cancelled": "\u0645\u0644\u063a\u0627\u0629",
        }
        LEAVE_TYPE_AR = {
            "annual": "\u0633\u0646\u0648\u064a\u0629", "sick": "\u0645\u0631\u0636\u064a\u0629", "emergency": "\u0637\u0648\u0627\u0631\u0626",
            "maternity": "\u0623\u0645\u0648\u0645\u0629", "paternity": "\u0623\u0628\u0648\u0629", "hajj": "\u062d\u062c",
            "bereavement": "\u0648\u0641\u0627\u0629", "unpaid": "\u0628\u062f\u0648\u0646 \u0631\u0627\u062a\u0628",
        }

        # Batch-fetch approver/rejector names
        approver_ids = set()
        for r in requests:
            if r.approved_by:
                approver_ids.add(r.approved_by)
            if r.rejected_by:
                approver_ids.add(r.rejected_by)

        name_map = {}
        if approver_ids:
            names_result = await self.db.execute(
                select(Employee.id, Employee.first_name, Employee.last_name)
                .where(Employee.id.in_(approver_ids), Employee.tenant_id == self.tenant_id)
            )
            for row in names_result:
                name_map[row.id] = f"{row.first_name} {row.last_name}"

        return json.dumps({
            "count": len(requests),
            "requests": [
                {
                    "id": str(r.id),
                    "leave_type": r.leave_type.value,
                    "leave_type_ar": LEAVE_TYPE_AR.get(r.leave_type.value, r.leave_type.value),
                    "start_date": r.start_date.isoformat(),
                    "end_date": r.end_date.isoformat(),
                    "business_days": r.business_days,
                    "status": r.status.value,
                    "status_ar": STATUS_AR.get(r.status.value, r.status.value),
                    "reason": r.reason,
                    "auto_approved": r.auto_approved,
                    "approved_by": name_map.get(r.approved_by) if r.approved_by else None,
                    "approved_at": r.approved_at.isoformat() if r.approved_at else None,
                    "rejected_by": name_map.get(r.rejected_by) if r.rejected_by else None,
                    "rejected_at": r.rejected_at.isoformat() if r.rejected_at else None,
                    "rejection_reason": r.rejection_reason,
                    "created_at": r.created_at.isoformat(),
                }
                for r in requests
            ],
        })

    # ── Self-Service Tools ─────────────────────────────────────

    async def _view_my_profile(self, employee_id: UUID) -> str:
        """Return the employee's full profile."""
        emp = await self._verify_employee(employee_id)
        if not emp:
            return json.dumps({"error": "Employee not found"})

        # Get department name
        dept_name = None
        dept_name_ar = None
        if emp.department_id:
            dept_result = await self.db.execute(
                select(Department).where(Department.id == emp.department_id)
            )
            dept = dept_result.scalar_one_or_none()
            if dept:
                dept_name = dept.name
                dept_name_ar = dept.name_ar

        return json.dumps({
            "name": emp.full_name,
            "name_ar": f"{emp.first_name_ar or ''} {emp.last_name_ar or ''}".strip() or None,
            "email": emp.email,
            "phone": emp.phone,
            "job_title": emp.job_title,
            "job_title_ar": emp.job_title_ar,
            "department": dept_name,
            "department_ar": dept_name_ar,
            "hire_date": emp.hire_date.isoformat(),
            "employee_number": emp.employee_number,
            "work_mode": emp.work_mode.value if emp.work_mode else None,
            "work_mode_ar": {"onsite": "حضوري", "remote": "عن بعد", "hybrid": "هجين"}.get(
                emp.work_mode.value if emp.work_mode else "", None
            ),
            "contract_type": emp.contract_type,
            "status": emp.status.value,
        })

    async def _view_salary_info(self, employee_id: UUID) -> str:
        """Return basic salary info from employee record."""
        emp = await self._verify_employee(employee_id)
        if not emp:
            return json.dumps({"error": "Employee not found"})

        return json.dumps({
            "employee_name": emp.full_name,
            "salary_sar": emp.salary_sar,
            "salary_label": "الراتب الأساسي (ريال سعودي)",
            "salary_label_en": "Basic Salary (SAR)",
            "note": "This is the basic monthly salary. For full payslip details, use view_payslip.",
            "note_ar": "هذا هو الراتب الأساسي الشهري. لتفاصيل كشف الراتب الكامل، استخدم عرض كشف الراتب.",
        })

    async def _view_vacation_balance(self, employee_id: UUID) -> str:
        """Return leave balance breakdown for the current year."""
        emp = await self._verify_employee(employee_id)
        if not emp:
            return json.dumps({"error": "Employee not found"})

        current_year = date.today().year
        result = await self.db.execute(
            select(LeaveBalance).where(
                LeaveBalance.employee_id == employee_id,
                LeaveBalance.year == current_year,
            )
        )
        balances = result.scalars().all()

        if not balances:
            return json.dumps({
                "message": "No leave balances found for the current year.",
                "message_ar": "لم يتم العثور على أرصدة إجازات للسنة الحالية.",
                "year": current_year,
            })

        LEAVE_TYPE_AR = {
            "annual": "سنوية", "sick": "مرضية", "emergency": "طوارئ",
            "maternity": "أمومة", "paternity": "أبوة", "hajj": "حج",
            "bereavement": "وفاة", "unpaid": "بدون راتب",
        }

        return json.dumps({
            "employee_name": emp.full_name,
            "year": current_year,
            "balances": [
                {
                    "type": b.leave_type.value,
                    "type_ar": LEAVE_TYPE_AR.get(b.leave_type.value, b.leave_type.value),
                    "total_days": b.total_days,
                    "used_days": b.used_days,
                    "remaining_days": b.remaining_days,
                }
                for b in balances
            ],
        })

    async def _view_contract_info(self, employee_id: UUID) -> str:
        """Return contract and probation details."""
        emp = await self._verify_employee(employee_id)
        if not emp:
            return json.dumps({"error": "Employee not found"})

        CONTRACT_TYPE_AR = {
            "full_time": "دوام كامل", "part_time": "دوام جزئي",
            "contract": "عقد", "internship": "تدريب",
        }

        return json.dumps({
            "employee_name": emp.full_name,
            "contract_type": emp.contract_type,
            "contract_type_ar": CONTRACT_TYPE_AR.get(emp.contract_type, emp.contract_type),
            "hire_date": emp.hire_date.isoformat(),
            "probation_end_date": emp.probation_end_date.isoformat() if emp.probation_end_date else None,
            "probation_completed": emp.probation_completed,
            "is_on_probation": emp.is_on_probation,
            "work_mode": emp.work_mode.value if emp.work_mode else None,
            "work_mode_ar": {"onsite": "حضوري", "remote": "عن بعد", "hybrid": "هجين"}.get(
                emp.work_mode.value if emp.work_mode else "", None
            ),
            "wfh_days_per_week": emp.wfh_days_per_week,
        })

    async def _view_payslip(
        self, employee_id: UUID, year: int | None = None, month: int | None = None
    ) -> str:
        """Return payslip for a given month. Compute a stub if no record exists."""
        emp = await self._verify_employee(employee_id)
        if not emp:
            return json.dumps({"error": "Employee not found"})

        today = date.today()
        target_year = year or today.year
        target_month = month or today.month

        if target_month < 1 or target_month > 12:
            return json.dumps({"error": "Month must be between 1 and 12."})

        # Try to find an existing payslip record
        result = await self.db.execute(
            select(Payslip).where(
                Payslip.employee_id == employee_id,
                Payslip.tenant_id == self.tenant_id,
                Payslip.year == target_year,
                Payslip.month == target_month,
            )
        )
        payslip = result.scalar_one_or_none()

        if payslip:
            return json.dumps({
                "source": "record",
                "source_ar": "سجل رسمي",
                "employee_name": emp.full_name,
                "year": payslip.year,
                "month": payslip.month,
                "basic_salary": payslip.basic_salary,
                "housing_allowance": payslip.housing_allowance,
                "transport_allowance": payslip.transport_allowance,
                "other_allowances": payslip.other_allowances,
                "gross_salary": payslip.gross_salary,
                "gosi_employee": payslip.gosi_employee,
                "absent_deduction": payslip.absent_deduction,
                "other_deductions": payslip.other_deductions,
                "total_deductions": payslip.total_deductions,
                "net_salary": payslip.net_salary,
                "notes": payslip.notes,
            })

        # No record — compute estimated stub from salary_sar
        basic = emp.salary_sar
        if not basic:
            return json.dumps({
                "error": "No salary information on file for this employee.",
                "error_ar": "لا توجد معلومات راتب مسجلة لهذا الموظف.",
            })

        housing = int(basic * 0.25)
        transport = min(int(basic * 0.10), 1500)
        gross = basic + housing + transport

        # GOSI employee contribution: 9.75% of (basic + housing) for Saudis, 0 for non-Saudis
        if emp.is_saudi:
            gosi = int((basic + housing) * 0.0975)
        else:
            gosi = 0

        total_deductions = gosi
        net = gross - total_deductions

        return json.dumps({
            "source": "estimate",
            "source_ar": "تقدير (لا يوجد كشف راتب رسمي لهذا الشهر)",
            "employee_name": emp.full_name,
            "year": target_year,
            "month": target_month,
            "basic_salary": basic,
            "housing_allowance": housing,
            "housing_allowance_label": "بدل سكن (25%)",
            "transport_allowance": transport,
            "transport_allowance_label": "بدل نقل (10%، حد أقصى 1500)",
            "gross_salary": gross,
            "gosi_employee": gosi,
            "gosi_label": "خصم التأمينات الاجتماعية (9.75%)" if emp.is_saudi else "غير مشمول بالتأمينات",
            "total_deductions": total_deductions,
            "net_salary": net,
            "note": "This is an estimated payslip. Actual payslip may differ based on deductions and allowances.",
            "note_ar": "هذا كشف راتب تقديري. قد يختلف الكشف الفعلي بناءً على الخصومات والبدلات.",
        })

    # ── C4: Proactive Context ──────────────────────────────────

    async def get_proactive_context(self, employee_id: str) -> str | None:
        """Check for open tickets and pending leave requests to mention proactively."""
        if not employee_id:
            return None

        try:
            emp_uuid = UUID(employee_id)
        except ValueError:
            return None

        context_parts = []

        # Open escalation tickets
        ticket_result = await self.db.execute(
            select(EscalationTicket).where(
                EscalationTicket.tenant_id == self.tenant_id,
                EscalationTicket.employee_id == emp_uuid,
                EscalationTicket.status.in_([EscalationStatus.open, EscalationStatus.assigned]),
            ).order_by(EscalationTicket.created_at.desc()).limit(5)
        )
        open_tickets = ticket_result.scalars().all()
        if open_tickets:
            ticket_summaries = ", ".join(
                f"#{str(t.id)[:8]} ({t.status.value}: <user_data>{html.escape((t.summary or t.reason or '')[:80])}</user_data>)"
                for t in open_tickets
            )
            context_parts.append(
                f"This employee has {len(open_tickets)} open escalation ticket(s): {ticket_summaries}. "
                "Proactively mention them if this is a new conversation."
            )

        # Pending leave requests
        pending_result = await self.db.execute(
            select(func.count(LeaveRequest.id)).where(
                LeaveRequest.employee_id == emp_uuid,
                LeaveRequest.status == LeaveStatus.pending,
            )
        )
        pending_count = pending_result.scalar_one()
        if pending_count > 0:
            context_parts.append(
                f"This employee has {pending_count} pending leave request(s) awaiting approval."
            )

        # Onboarding in progress
        try:
            from app.models.onboarding import OnboardingAssignment, OnboardingAssignmentStatus
            onboard_result = await self.db.execute(
                select(OnboardingAssignment).where(
                    OnboardingAssignment.tenant_id == self.tenant_id,
                    OnboardingAssignment.employee_id == emp_uuid,
                    OnboardingAssignment.status == OnboardingAssignmentStatus.in_progress,
                )
            )
            onboarding = onboard_result.scalar_one_or_none()
            if onboarding:
                context_parts.append(
                    "This employee has an onboarding checklist in progress. "
                    "If this appears to be their first conversation, welcome them warmly and offer to guide through pending steps."
                )
        except Exception:
            pass  # Onboarding tables may not exist yet during migration

        if not context_parts:
            return None

        return "\n\nProactive context for this employee:\n" + "\n".join(f"- {p}" for p in context_parts)

    # ── Document Tools ────────────────────────────────────────

    DOCUMENT_TYPE_AR = {
        "national_id": "الهوية الوطنية",
        "iqama": "الإقامة",
        "contract": "العقد",
        "gosi_cert": "شهادة التأمينات",
        "medical_insurance": "التأمين الطبي",
        "education_cert": "الشهادة العلمية",
        "passport": "جواز السفر",
        "bank_letter": "خطاب البنك",
        "driving_license": "رخصة القيادة",
        "other": "مستند آخر",
    }

    VERIFICATION_STATUS_AR = {
        "pending": "قيد المراجعة",
        "verified": "موثق",
        "rejected": "مرفوض",
    }

    async def _list_my_documents(self, employee_id: UUID) -> str:
        """List all HR documents for the employee."""
        emp = await self._verify_employee(employee_id)
        if not emp:
            return json.dumps({"error": "Employee not found"})

        result = await self.db.execute(
            select(EmployeeDocument)
            .where(
                EmployeeDocument.tenant_id == self.tenant_id,
                EmployeeDocument.employee_id == employee_id,
                EmployeeDocument.is_deleted.is_(False),
            )
            .order_by(EmployeeDocument.created_at.desc())
        )
        docs = result.scalars().all()

        if not docs:
            return json.dumps({
                "message": "No HR documents found.",
                "message_ar": "لم يتم العثور على مستندات.",
                "count": 0,
            })

        return json.dumps({
            "count": len(docs),
            "documents": [
                {
                    "id": str(d.id),
                    "document_type": d.document_type.value,
                    "document_type_ar": self.DOCUMENT_TYPE_AR.get(d.document_type.value, d.document_type.value),
                    "label": d.label,
                    "original_filename": d.original_filename,
                    "verification_status": d.verification_status.value,
                    "verification_status_ar": self.VERIFICATION_STATUS_AR.get(d.verification_status.value, d.verification_status.value),
                    "expires_at": d.expires_at.isoformat() if d.expires_at else None,
                    "created_at": d.created_at.isoformat(),
                }
                for d in docs
            ],
        })

    async def _check_expiring_documents(self, employee_id: UUID) -> str:
        """Check for documents expiring within 60 days."""
        emp = await self._verify_employee(employee_id)
        if not emp:
            return json.dumps({"error": "Employee not found"})

        today = date.today()
        deadline = today + timedelta(days=60)

        result = await self.db.execute(
            select(EmployeeDocument)
            .where(
                EmployeeDocument.tenant_id == self.tenant_id,
                EmployeeDocument.employee_id == employee_id,
                EmployeeDocument.is_deleted.is_(False),
                EmployeeDocument.expires_at.isnot(None),
                EmployeeDocument.expires_at >= today,
                EmployeeDocument.expires_at <= deadline,
            )
            .order_by(EmployeeDocument.expires_at.asc())
        )
        docs = result.scalars().all()

        if not docs:
            return json.dumps({
                "message": "No documents expiring in the next 60 days.",
                "message_ar": "لا توجد مستندات تنتهي صلاحيتها خلال الـ 60 يوم القادمة.",
                "count": 0,
            })

        return json.dumps({
            "count": len(docs),
            "expiring_documents": [
                {
                    "id": str(d.id),
                    "document_type": d.document_type.value,
                    "document_type_ar": self.DOCUMENT_TYPE_AR.get(d.document_type.value, d.document_type.value),
                    "label": d.label,
                    "original_filename": d.original_filename,
                    "expires_at": d.expires_at.isoformat(),
                    "days_until_expiry": (d.expires_at - today).days,
                    "verification_status": d.verification_status.value,
                }
                for d in docs
            ],
        })
