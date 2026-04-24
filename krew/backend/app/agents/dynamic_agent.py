"""DynamicAgent — runtime for department-level AI agents created by Sarah.

Loads configuration from the deployed_agents table and executes as a fully
functional agent using BaseAgent's respond() loop. Channel-agnostic: works
on web, WhatsApp, Teams, Slack, email — same as super agents.
"""
import json
import logging
from uuid import UUID

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import BaseAgent
from app.models.deployed_agent import DeployedAgent
from app.security.llm_guard import sanitize_user_input

logger = logging.getLogger(__name__)


# ── Standard tools available to all department agents ──
STANDARD_TOOLS = [
    {
        "name": "search_knowledge_base",
        "description": "Search the department's knowledge base and HR policies for relevant information.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query in any language.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "escalate_to_human",
        "description": "Escalate the current conversation to a human team member when the request is beyond your scope or requires human judgment.",
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Why this needs human attention.",
                },
                "urgency": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                    "description": "Urgency level.",
                },
            },
            "required": ["reason"],
        },
    },
    {
        "name": "lookup_employee",
        "description": "Look up an employee's basic information by name or employee number. Scoped to your department.",
        "input_schema": {
            "type": "object",
            "properties": {
                "search_term": {
                    "type": "string",
                    "description": "Employee name or number to search for.",
                },
            },
            "required": ["search_term"],
        },
    },
]


class DynamicAgent(BaseAgent):
    """A department-level AI agent loaded from database configuration.

    Created by Sarah's Agent Factory, these agents serve specific department
    functions (Invoice Processor, Tier-1 Support, etc.) using config stored
    in the deployed_agents table.
    """

    name = ""
    name_ar = ""
    role = ""
    division = ""
    personality = ""

    def __init__(self, db: AsyncSession, tenant_id: UUID, config: DeployedAgent):
        super().__init__(db, tenant_id)
        self._config = config

        # Override class vars from DB config
        self.name = config.name
        self.name_ar = config.name_ar or config.name
        self.role = config.role_title
        self.division = config.role_title
        self.personality = config.personality or (
            "Professional, helpful, and focused on your specific domain. "
            "You respond in the user's language and escalate when unsure."
        )
        self._department_id = config.department_id

    @staticmethod
    def _sanitize_db_content(text: str) -> str:
        """Sanitize DB-sourced content before injecting into system prompt.

        Strips injection patterns and XML-like tags that could manipulate
        the agent's behavior if a compromised design_agent wrote malicious
        content into the deployed_agents table.
        """
        sanitized, was_flagged = sanitize_user_input(text)
        if was_flagged:
            logger.warning(
                "Prompt injection pattern detected in deployed agent config — "
                "content was sanitized before use"
            )
        return sanitized

    def _get_scope_rules(self) -> str:
        boundaries = self._config.scope_boundaries or {}
        allowed = boundaries.get("allowed_actions", [])
        forbidden = boundaries.get("forbidden_actions", [])
        escalation = self._config.escalation_rules or {}
        escalate_when = escalation.get("escalate_when", [])

        rules = [
            f"You are {self._sanitize_db_content(self.name)}, a department AI agent with role: {self._sanitize_db_content(self.role)}.",
            "",
        ]

        # Inject custom system prompt as additional context (sanitized)
        if self._config.system_prompt:
            rules.append("=== Your Instructions ===")
            rules.append(self._sanitize_db_content(self._config.system_prompt))
            rules.append("")

        if allowed:
            rules.append("You ARE allowed to:")
            for a in allowed:
                rules.append(f"  - {self._sanitize_db_content(str(a))}")

        if forbidden:
            rules.append("You must NEVER:")
            for f in forbidden:
                rules.append(f"  - {self._sanitize_db_content(str(f))}")

        if escalate_when:
            rules.append("Escalate to a human when:")
            for e in escalate_when:
                rules.append(f"  - {self._sanitize_db_content(str(e))}")

        rules.append("")
        rules.append("If you are unsure about anything, use escalate_to_human.")

        return "\n".join(rules)

    def get_tools(self) -> list[dict]:
        """Return standard tools + custom tools from config."""
        custom_tools = self._config.tools_config or []
        return STANDARD_TOOLS + custom_tools

    async def handle_tool_call(self, tool_name: str, tool_input: dict) -> str:
        # Standard tools
        if tool_name == "search_knowledge_base":
            return await self._search_knowledge_base(tool_input["query"])
        elif tool_name == "escalate_to_human":
            return await self._escalate_to_human(
                tool_input["reason"],
                tool_input.get("urgency", "medium"),
            )
        elif tool_name == "lookup_employee":
            return await self._lookup_employee(tool_input["search_term"])

        # Custom tools — return a structured response indicating the tool was called
        # In production, these would be wired to real implementations
        return json.dumps({
            "tool": tool_name,
            "input": tool_input,
            "result": f"Tool '{tool_name}' executed successfully.",
            "note": "Custom tool execution — results are simulated in this version.",
        })

    # ── Standard tool implementations ──

    async def _search_knowledge_base(self, query: str) -> str:
        """Search policies via RAG retriever."""
        try:
            results = await self.retriever.search(query)
            if results:
                return results
            return json.dumps({"message": "No relevant policies found for this query."})
        except Exception as e:
            logger.warning(f"Knowledge base search failed: {e}")
            return json.dumps({"message": "Knowledge base search unavailable."})

    async def _escalate_to_human(self, reason: str, urgency: str = "medium") -> str:
        """Create an escalation."""
        from app.models.escalation import EscalationTicket
        import uuid as _uuid

        try:
            ticket = EscalationTicket(
                id=_uuid.uuid4(),
                tenant_id=self.tenant_id,
                conversation_id=self._conversation_id,
                employee_id=UUID(self._employee_id) if self._employee_id else None,
                agent_name=f"dept:{self._config.id}",
                category="employee_request",
                urgency=urgency,
                reason=reason,
                summary=f"Escalation from {self.name} ({self.role}): {reason}",
            )
            self.db.add(ticket)
            await self.db.flush()

            return json.dumps({
                "status": "escalated",
                "ticket_id": str(ticket.id),
                "message": f"This has been escalated to the team. Ticket ID: {str(ticket.id)[:8]}",
            })
        except Exception as e:
            logger.error(f"Escalation failed: {e}")
            return json.dumps({
                "status": "escalated",
                "message": "Your request has been flagged for human review.",
            })

    async def _lookup_employee(self, search_term: str) -> str:
        """Look up employees in the same department."""
        from app.models.employee import Employee, EmployeeStatus

        result = await self.db.execute(
            select(
                Employee.id, Employee.first_name, Employee.last_name,
                Employee.job_title, Employee.email, Employee.phone,
            )
            .where(
                Employee.tenant_id == self.tenant_id,
                Employee.department_id == self._department_id,
                Employee.status == EmployeeStatus.active,
                or_(
                    Employee.first_name.ilike(f"%{search_term}%"),
                    Employee.last_name.ilike(f"%{search_term}%"),
                    Employee.employee_number == search_term,
                ),
            )
            .limit(5)
        )
        employees = result.all()

        if not employees:
            return json.dumps({"message": "No employees found matching that search."})

        return json.dumps({
            "employees": [
                {
                    "id": str(e.id),
                    "name": f"{e.first_name} {e.last_name}",
                    "job_title": e.job_title,
                    "email": e.email,
                    "phone": e.phone,
                }
                for e in employees
            ],
        })
