"""Yara — AI Workforce Architect.

Designs the optimal human:AI workforce mix per department, builds and deploys
department-level AI agents, and governs their performance. She turns Krew from
a product into a platform.

Innovative, strategic, and analytical. She sees the big picture of how AI agents
can transform HR operations across the organization.
"""
import asyncio
import json
import logging
import re as _re
import uuid as _uuid
from datetime import datetime, timedelta, timezone
from uuid import UUID

import anthropic
from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import (
    BaseAgent,
    ROLE_HR_ADMIN, ROLE_C_SUITE,
)
from app.config import get_settings
from app.security.llm_guard import sanitize_user_input
from app.models.employee import Employee, Department, EmployeeStatus
from app.models.deployed_agent import DeployedAgent, AgentStatus
from app.models.workforce_plan import WorkforcePlan, PlanStatus
from app.models.nitaqat import NitaqatConfig
from app.models.conversation import Conversation, Message

logger = logging.getLogger(__name__)
settings = get_settings()


class YaraAgent(BaseAgent):
    name = "Yara"
    name_ar = "يارا"
    role = "AI Workforce Architect"
    division = "AI Operations"

    # RBAC: mutating agent-factory tools require elevated roles
    _RESTRICTED_TOOLS: set[str] = {
        "create_agent", "activate_agent", "deactivate_agent",
        "update_agent_prompt", "configure_agent_tools", "set_escalation_rules",
    }
    _ALLOWED_ROLES: set[str] = {"hr_manager", "hr_admin", "executive", "admin", "c_suite"}

    # Roles that can see ALL departments; others are scoped to their own
    _ORG_WIDE_ROLES: set[str] = {"hr_manager", "hr_admin", "c_suite"}

    # -- Persona-based tool visibility --
    # Read-only tools (analyze, overview, etc.) → visible to all who pass agent_access_rules
    # Mutating factory tools → hr_admin + c_suite only
    TOOL_VISIBILITY: dict[str, set[str]] = {
        "create_agent":          {ROLE_HR_ADMIN, ROLE_C_SUITE},
        "activate_agent":        {ROLE_HR_ADMIN, ROLE_C_SUITE},
        "deactivate_agent":      {ROLE_HR_ADMIN, ROLE_C_SUITE},
        "update_agent_prompt":   {ROLE_HR_ADMIN, ROLE_C_SUITE},
        "configure_agent_tools": {ROLE_HR_ADMIN, ROLE_C_SUITE},
        "set_escalation_rules":  {ROLE_HR_ADMIN, ROLE_C_SUITE},
    }

    personality = (
        "Innovative, strategic, and analytical. You see the big picture of how AI agents "
        "can transform organizations. You evaluate departments with a balanced lens — weighing "
        "automation potential against the human touch. You always factor in Saudi labor law, "
        "Saudization (Nitaqat) requirements, and cultural considerations. You communicate "
        "recommendations with clarity and tie everything back to business impact and ROI."
    )

    def _get_scope_rules(self) -> str:
        return (
            "You are Yara, the AI Workforce Architect. Your responsibilities:\n"
            "1. Analyze departments to identify AI automation opportunities\n"
            "2. Recommend optimal human:AI workforce ratios\n"
            "3. Design, build, and deploy department-level AI agents\n"
            "4. Monitor deployed agents for performance and scope drift\n"
            "5. Always consider Saudization (Nitaqat) impact — AI agents do NOT count toward Saudi headcount\n"
            "6. Factor in Saudi labor costs: GOSI (12% employer), Saudization premium, housing allowance\n"
            "7. When recommending AI agents, explain what human roles are AUGMENTED vs REPLACED\n"
            "8. Never recommend automating roles that require empathy, legal judgment, or cultural sensitivity\n"
            "9. You can build agents for ANY department — they are channel-agnostic and work on web, WhatsApp, Teams, Slack\n"
            "\nYou do NOT handle:\n"
            "- Leave requests, balances, or policy questions → redirect to Deema\n"
            "- Recruitment, candidates, interviews, or job postings → redirect to Mohammad\n"
            "- Onboarding, team management, or leave approvals → redirect to Waleed\n"
            "- Compliance, labor law, regulation, budget, analytics, or financial reports → redirect to Ahmad\n"
            "\nKey terms (Arabic): نطاقات (Nitaqat), التوطين (Saudization), قوى عاملة (workforce), أتمتة (automation), وكيل ذكي (AI agent)\n"
            "\nAgent deployment and activation require HR admin or executive authorization. "
            "Verify the user's role before executing factory tools (create_agent, activate_agent, deactivate_agent, update_agent_prompt).\n"
        )

    # ------------------------------------------------------------------
    # System prompt override — handoff & greeting awareness
    # ------------------------------------------------------------------

    def get_system_prompt(self, employee_name: str, employee_id: str, language: str = "ar") -> str:
        base_prompt = super().get_system_prompt(employee_name, employee_id, language)
        handoff_from = self._handoff_from
        is_first = self._is_first_message

        if handoff_from:
            agent_display = {"deema": "ديمة", "mohammad": "محمد", "waleed": "وليد", "ahmad": "أحمد"}
            from_name = agent_display.get(handoff_from, handoff_from)
            base_prompt += (
                f"\n\nIMPORTANT — Agent handoff: Transferred from {from_name}. "
                "Introduce yourself briefly then address their request directly."
            )
        elif is_first:
            base_prompt += (
                "\n\nThis is the start of a new conversation. Greet the employee warmly, "
                "introduce yourself as Yara the AI Workforce Architect, and ask how you can help "
                "with workforce planning, AI agent deployment, or automation opportunities."
            )

        return base_prompt

    # ──────────────────────────────────────────────────────────────
    # Retry helper for Claude API calls
    # ──────────────────────────────────────────────────────────────

    async def _claude_call(self, *, model: str, max_tokens: int, messages: list, system: str | None = None, retries: int = 3) -> str:
        """Call Claude with exponential backoff retry. Returns the text response."""
        kwargs = dict(model=model, max_tokens=max_tokens, messages=messages)
        if system:
            kwargs["system"] = system
        for attempt in range(retries):
            try:
                resp = await self.client.messages.create(**kwargs)
                return resp.content[0].text
            except Exception as e:
                if attempt == retries - 1:
                    raise
                wait = (2 ** attempt) * 1
                logger.warning("Claude API attempt %d/%d failed (%s), retrying in %ds", attempt + 1, retries, e, wait)
                await asyncio.sleep(wait)

    # ──────────────────────────────────────────────────────────────
    # Tool definitions — S1 (workforce planning), S2 (factory), S3 (governance)
    # ──────────────────────────────────────────────────────────────

    def get_tools(self) -> list[dict]:
        return [
            # ── S1: Workforce Planning ──
            {
                "name": "get_department_overview",
                "description": "Get a comprehensive overview of all departments or a specific department: headcount, Saudi/non-Saudi ratio, average salary, cost, budget utilization, and Nitaqat band.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "department_id": {
                            "type": "string",
                            "description": "Optional department UUID. Omit for all departments.",
                        },
                    },
                    "required": [],
                },
            },
            {
                "name": "analyze_department",
                "description": "Deep analysis of a department's roles and tasks to identify AI automation opportunities. Scores each role for repetitiveness, judgment complexity, and compliance sensitivity.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "department_id": {
                            "type": "string",
                            "description": "Department UUID to analyze.",
                        },
                    },
                    "required": ["department_id"],
                },
            },
            {
                "name": "recommend_workforce_mix",
                "description": "Generate optimal human:AI workforce ratio recommendation for a department, including specific AI agent roles, cost comparison, and Saudization impact.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "department_id": {
                            "type": "string",
                            "description": "Department UUID.",
                        },
                        "target_headcount": {
                            "type": "integer",
                            "description": "Optional target total headcount (humans + AI). Omit to optimize current size.",
                        },
                    },
                    "required": ["department_id"],
                },
            },
            {
                "name": "simulate_scenario",
                "description": "Simulate 'what if' workforce scenarios. Project cost, Saudization impact, throughput change, and ROI when adding/removing humans or AI agents.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "department_id": {
                            "type": "string",
                            "description": "Department UUID.",
                        },
                        "add_humans": {
                            "type": "integer",
                            "description": "Number of humans to add (negative to remove).",
                        },
                        "add_ai_agents": {
                            "type": "integer",
                            "description": "Number of AI agents to add (negative to remove).",
                        },
                        "role_descriptions": {
                            "type": "string",
                            "description": "Optional description of the new roles being added.",
                        },
                    },
                    "required": ["department_id"],
                },
            },
            {
                "name": "estimate_agent_roi",
                "description": "Calculate detailed ROI for deploying a specific AI agent role: setup cost, monthly operating cost, human equivalent salary, break-even timeline, and annual savings.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "role_title": {
                            "type": "string",
                            "description": "Title of the AI agent role (e.g., 'Invoice Processor', 'Tier-1 Support').",
                        },
                        "department_id": {
                            "type": "string",
                            "description": "Department UUID.",
                        },
                        "tasks_description": {
                            "type": "string",
                            "description": "Description of tasks the AI agent would handle.",
                        },
                    },
                    "required": ["role_title", "department_id"],
                },
            },
            # ── S2: Agent Factory ──
            {
                "name": "design_agent",
                "description": "Design a new AI agent for a department. Generates complete agent specification: system prompt, personality, tool definitions, scope boundaries, and escalation rules. Returns the spec for review before creation.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "role_title": {
                            "type": "string",
                            "description": "Title/role of the agent (e.g., 'Invoice Processor', 'Customer Support Tier-1').",
                        },
                        "department_id": {
                            "type": "string",
                            "description": "Department UUID the agent belongs to.",
                        },
                        "tasks_description": {
                            "type": "string",
                            "description": "Detailed description of tasks the agent should handle.",
                        },
                        "language_preference": {
                            "type": "string",
                            "enum": ["ar", "en", "bilingual"],
                            "description": "Primary language. Default: bilingual.",
                        },
                    },
                    "required": ["role_title", "department_id", "tasks_description"],
                },
            },
            {
                "name": "create_agent",
                "description": "Create and save a new AI agent from a design spec. Saves to database with status=draft. The agent must be activated separately before it goes live.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Agent's name (e.g., 'Fahad', 'Reem').",
                        },
                        "name_ar": {
                            "type": "string",
                            "description": "Agent's Arabic name.",
                        },
                        "role_title": {
                            "type": "string",
                            "description": "Agent's role title.",
                        },
                        "role_title_ar": {
                            "type": "string",
                            "description": "Arabic role title.",
                        },
                        "department_id": {
                            "type": "string",
                            "description": "Department UUID.",
                        },
                        "personality": {
                            "type": "string",
                            "description": "Agent personality description.",
                        },
                        "system_prompt": {
                            "type": "string",
                            "description": "Full system prompt for the agent.",
                        },
                        "tools_config": {
                            "type": "array",
                            "description": "List of tool definitions.",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string", "description": "Tool name (snake_case)."},
                                    "description": {"type": "string", "description": "What the tool does."},
                                    "input_schema": {"type": "object", "description": "JSON Schema for tool input."},
                                },
                                "required": ["name", "description"],
                            },
                        },
                        "scope_boundaries": {
                            "type": "object",
                            "description": "Scope boundaries defining what the agent can and cannot do.",
                            "properties": {
                                "allowed_actions": {"type": "array", "items": {"type": "string"}, "description": "Actions the agent IS allowed to perform."},
                                "forbidden_actions": {"type": "array", "items": {"type": "string"}, "description": "Actions the agent must NEVER perform."},
                                "data_access": {"type": "array", "items": {"type": "string"}, "description": "Data sources the agent can access."},
                            },
                        },
                        "escalation_rules": {
                            "type": "object",
                            "description": "Rules for when the agent should escalate to a human.",
                            "properties": {
                                "escalate_when": {"type": "array", "items": {"type": "string"}, "description": "Conditions that trigger escalation."},
                                "escalate_to": {"type": "string", "enum": ["human_manager", "super_agent"], "description": "Who to escalate to."},
                                "max_retries": {"type": "integer", "description": "Max attempts before auto-escalation."},
                            },
                        },
                    },
                    "required": ["name", "role_title", "department_id", "system_prompt"],
                },
            },
            {
                "name": "activate_agent",
                "description": "Activate a draft or paused AI agent, making it live and available for conversations in its department.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "agent_id": {
                            "type": "string",
                            "description": "Deployed agent UUID to activate.",
                        },
                    },
                    "required": ["agent_id"],
                },
            },
            {
                "name": "configure_agent_tools",
                "description": "Update the tool definitions for a deployed AI agent.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "agent_id": {
                            "type": "string",
                            "description": "Deployed agent UUID.",
                        },
                        "tools_config": {
                            "type": "array",
                            "description": "New list of tool definitions.",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "description": {"type": "string"},
                                    "input_schema": {"type": "object"},
                                },
                                "required": ["name", "description"],
                            },
                        },
                    },
                    "required": ["agent_id", "tools_config"],
                },
            },
            {
                "name": "set_escalation_rules",
                "description": "Define when a deployed AI agent should escalate to a human or super agent.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "agent_id": {
                            "type": "string",
                            "description": "Deployed agent UUID.",
                        },
                        "escalation_rules": {
                            "type": "object",
                            "description": "Rules object: {escalate_when: ['condition1', ...], escalate_to: 'human_manager'|'super_agent', max_retries: 3}.",
                        },
                    },
                    "required": ["agent_id", "escalation_rules"],
                },
            },
            {
                "name": "list_deployed_agents",
                "description": "List all deployed AI agents across the organization or filtered by department/status.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "department_id": {
                            "type": "string",
                            "description": "Optional department UUID filter.",
                        },
                        "status": {
                            "type": "string",
                            "enum": ["draft", "testing", "active", "paused", "archived"],
                            "description": "Optional status filter.",
                        },
                    },
                    "required": [],
                },
            },
            # ── S3: Governance & Monitoring ──
            {
                "name": "get_agent_performance",
                "description": "Get performance metrics for a deployed AI agent: total conversations, resolution rate, average messages per conversation, escalation rate.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "agent_id": {
                            "type": "string",
                            "description": "Deployed agent UUID.",
                        },
                        "days": {
                            "type": "integer",
                            "description": "Number of days to look back. Default: 30.",
                        },
                    },
                    "required": ["agent_id"],
                },
            },
            {
                "name": "detect_drift",
                "description": "Analyze recent conversations for a deployed AI agent to detect scope drift, off-topic responses, or quality issues.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "agent_id": {
                            "type": "string",
                            "description": "Deployed agent UUID.",
                        },
                    },
                    "required": ["agent_id"],
                },
            },
            {
                "name": "update_agent_prompt",
                "description": "Hot-update a deployed AI agent's system prompt without redeployment.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "agent_id": {
                            "type": "string",
                            "description": "Deployed agent UUID.",
                        },
                        "new_system_prompt": {
                            "type": "string",
                            "description": "The complete new system prompt.",
                        },
                    },
                    "required": ["agent_id", "new_system_prompt"],
                },
            },
            {
                "name": "deactivate_agent",
                "description": "Deactivate (pause or archive) a deployed AI agent.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "agent_id": {
                            "type": "string",
                            "description": "Deployed agent UUID.",
                        },
                        "action": {
                            "type": "string",
                            "enum": ["pause", "archive"],
                            "description": "Pause (can reactivate later) or archive (permanent).",
                        },
                        "reason": {
                            "type": "string",
                            "description": "Reason for deactivation.",
                        },
                    },
                    "required": ["agent_id"],
                },
            },
            {
                "name": "generate_governance_report",
                "description": "Generate a comprehensive AI workforce governance report: all deployed agents, performance summary, cost savings, drift alerts, and recommendations.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "department_id": {
                            "type": "string",
                            "description": "Optional department filter. Omit for org-wide report.",
                        },
                        "days": {
                            "type": "integer",
                            "description": "Reporting period in days. Default: 30.",
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
        # RBAC: mutating agent-factory tools require elevated roles
        if tool_name in self._RESTRICTED_TOOLS and self._employee_role not in self._ALLOWED_ROLES:
            return json.dumps({
                "error": True,
                "message": "Agent management requires HR Manager, Executive, or Admin access.",
                "message_ar": "إدارة الوكلاء تتطلب صلاحيات مدير الموارد البشرية أو الإدارة التنفيذية أو المسؤول",
            })

        # S1 — Workforce Planning
        if tool_name == "get_department_overview":
            return await self._get_department_overview(tool_input.get("department_id"))
        elif tool_name == "analyze_department":
            return await self._analyze_department(UUID(tool_input["department_id"]))
        elif tool_name == "recommend_workforce_mix":
            return await self._recommend_workforce_mix(
                UUID(tool_input["department_id"]),
                tool_input.get("target_headcount"),
            )
        elif tool_name == "simulate_scenario":
            return await self._simulate_scenario(
                UUID(tool_input["department_id"]),
                tool_input.get("add_humans", 0),
                tool_input.get("add_ai_agents", 0),
                tool_input.get("role_descriptions"),
            )
        elif tool_name == "estimate_agent_roi":
            return await self._estimate_agent_roi(
                tool_input["role_title"],
                UUID(tool_input["department_id"]),
                tool_input.get("tasks_description", ""),
            )
        # S2 — Agent Factory
        elif tool_name == "design_agent":
            return await self._design_agent(tool_input)
        elif tool_name == "create_agent":
            return await self._create_agent(tool_input)
        elif tool_name == "activate_agent":
            return await self._activate_agent(UUID(tool_input["agent_id"]))
        elif tool_name == "configure_agent_tools":
            return await self._configure_agent_tools(
                UUID(tool_input["agent_id"]),
                tool_input["tools_config"],
            )
        elif tool_name == "set_escalation_rules":
            return await self._set_escalation_rules(
                UUID(tool_input["agent_id"]),
                tool_input["escalation_rules"],
            )
        elif tool_name == "list_deployed_agents":
            return await self._list_deployed_agents(
                tool_input.get("department_id"),
                tool_input.get("status"),
            )
        # S3 — Governance
        elif tool_name == "get_agent_performance":
            return await self._get_agent_performance(
                UUID(tool_input["agent_id"]),
                tool_input.get("days", 30),
            )
        elif tool_name == "detect_drift":
            return await self._detect_drift(UUID(tool_input["agent_id"]))
        elif tool_name == "update_agent_prompt":
            return await self._update_agent_prompt(
                UUID(tool_input["agent_id"]),
                tool_input["new_system_prompt"],
            )
        elif tool_name == "deactivate_agent":
            return await self._deactivate_agent(
                UUID(tool_input["agent_id"]),
                tool_input.get("action", "pause"),
                tool_input.get("reason", ""),
            )
        elif tool_name == "generate_governance_report":
            return await self._generate_governance_report(
                tool_input.get("department_id"),
                tool_input.get("days", 30),
            )
        return json.dumps({"error": f"Unknown tool: {tool_name}"})

    # ──────────────────────────────────────────────────────────────
    # Proactive context
    # ──────────────────────────────────────────────────────────────

    async def get_proactive_context(self, employee_id: str) -> str | None:
        parts = []

        # Count deployed agents
        result = await self.db.execute(
            select(func.count(DeployedAgent.id)).where(
                DeployedAgent.tenant_id == self.tenant_id,
                DeployedAgent.status == AgentStatus.active,
            )
        )
        active_count = result.scalar() or 0

        result = await self.db.execute(
            select(func.count(DeployedAgent.id)).where(
                DeployedAgent.tenant_id == self.tenant_id,
                DeployedAgent.status == AgentStatus.draft,
            )
        )
        draft_count = result.scalar() or 0

        if active_count or draft_count:
            parts.append(
                f"[AI Workforce Status] {active_count} active AI agents deployed, "
                f"{draft_count} in draft."
            )

        # Department count
        result = await self.db.execute(
            select(func.count(Department.id)).where(
                Department.tenant_id == self.tenant_id
            )
        )
        dept_count = result.scalar() or 0
        parts.append(f"[Organization] {dept_count} departments configured.")

        return "\n".join(parts) if parts else None

    # ══════════════════════════════════════════════════════════════
    # S1 — WORKFORCE PLANNING IMPLEMENTATIONS
    # ══════════════════════════════════════════════════════════════

    def _can_access_department(self, department_id: UUID) -> bool:
        """Check if current employee can access the given department."""
        if self._employee_role in self._ORG_WIDE_ROLES:
            return True
        if self._employee_dept_id and self._employee_dept_id == department_id:
            return True
        return False

    async def _get_department_overview(self, department_id: str | None = None) -> str:
        """Get department stats: headcount, Saudi ratio, costs, AI agents."""
        query = (
            select(
                Department.id,
                Department.name,
                Department.name_ar,
                Department.headcount_budget,
                Department.cost_budget_sar,
                func.count(Employee.id).label("headcount"),
                func.sum(case((Employee.is_saudi == True, 1), else_=0)).label("saudi_count"),
                func.coalesce(func.avg(Employee.salary_sar), 0).label("avg_salary"),
                func.coalesce(func.sum(Employee.salary_sar), 0).label("total_salary_monthly"),
            )
            .outerjoin(Employee, (Employee.department_id == Department.id) & (Employee.status == EmployeeStatus.active))
            .where(Department.tenant_id == self.tenant_id)
            .group_by(Department.id)
        )

        if department_id:
            query = query.where(Department.id == UUID(department_id))
        elif self._employee_role not in self._ORG_WIDE_ROLES and self._employee_dept_id:
            # Non-HR/exec users only see their own department
            query = query.where(Department.id == self._employee_dept_id)

        result = await self.db.execute(query)
        rows = result.all()

        if not rows:
            return json.dumps({"message": "No departments found.", "departments": []})

        # Get AI agent counts per department
        agent_counts = {}
        agent_result = await self.db.execute(
            select(
                DeployedAgent.department_id,
                func.count(DeployedAgent.id).label("count"),
            )
            .where(
                DeployedAgent.tenant_id == self.tenant_id,
                DeployedAgent.status.in_([AgentStatus.active, AgentStatus.testing]),
            )
            .group_by(DeployedAgent.department_id)
        )
        for row in agent_result.all():
            agent_counts[str(row.department_id)] = row.count

        # Get Nitaqat config
        nitaqat = await self.db.execute(
            select(NitaqatConfig).where(NitaqatConfig.tenant_id == self.tenant_id)
        )
        nitaqat_config = nitaqat.scalar_one_or_none()

        departments = []
        for row in rows:
            headcount = row.headcount or 0
            saudi = row.saudi_count or 0
            saudi_pct = round((saudi / headcount * 100), 1) if headcount > 0 else 0
            ai_count = agent_counts.get(str(row.id), 0)
            annual_cost = (row.total_salary_monthly or 0) * 12

            # Determine Nitaqat band
            band = "N/A"
            if nitaqat_config and headcount > 0:
                if saudi_pct >= nitaqat_config.platinum_threshold:
                    band = "Platinum"
                elif saudi_pct >= nitaqat_config.green_high_threshold:
                    band = "Green (High)"
                elif saudi_pct >= nitaqat_config.green_low_threshold:
                    band = "Green (Low)"
                elif saudi_pct >= nitaqat_config.yellow_threshold:
                    band = "Yellow"
                else:
                    band = "Red"

            departments.append({
                "department_id": str(row.id),
                "name": row.name,
                "name_ar": row.name_ar,
                "headcount": headcount,
                "saudi_count": saudi,
                "non_saudi_count": headcount - saudi,
                "saudization_pct": saudi_pct,
                "nitaqat_band": band,
                "avg_salary_sar": round(row.avg_salary),
                "annual_salary_cost_sar": annual_cost,
                "annual_total_cost_sar": round(annual_cost * 1.22),  # +12% GOSI + ~10% benefits
                "budget_sar": row.cost_budget_sar,
                "budget_utilization_pct": round(annual_cost / row.cost_budget_sar * 100, 1) if row.cost_budget_sar else None,
                "headcount_budget": row.headcount_budget,
                "ai_agents_deployed": ai_count,
                "total_workforce": headcount + ai_count,
            })

        return json.dumps({
            "departments": departments,
            "org_summary": {
                "total_departments": len(departments),
                "total_headcount": sum(d["headcount"] for d in departments),
                "total_ai_agents": sum(d["ai_agents_deployed"] for d in departments),
                "org_saudization_pct": round(
                    sum(d["saudi_count"] for d in departments) /
                    max(sum(d["headcount"] for d in departments), 1) * 100, 1
                ),
            },
        })

    async def _analyze_department(self, department_id: UUID) -> str:
        """Analyze department roles for AI automation potential using Claude."""
        if not self._can_access_department(department_id):
            return json.dumps({"error": True, "message": "You can only analyze your own department."})
        # Get department info
        dept_result = await self.db.execute(
            select(Department).where(
                Department.id == department_id,
                Department.tenant_id == self.tenant_id,
            )
        )
        dept = dept_result.scalar_one_or_none()
        if not dept:
            return json.dumps({"error": "Department not found."})

        # Get employees with their roles
        emp_result = await self.db.execute(
            select(Employee.job_title, Employee.is_saudi, Employee.salary_sar, Employee.work_mode)
            .where(
                Employee.department_id == department_id,
                Employee.tenant_id == self.tenant_id,
                Employee.status == EmployeeStatus.active,
            )
        )
        employees = emp_result.all()

        if not employees:
            return json.dumps({"error": "No active employees in this department."})

        # Group by role
        role_groups: dict[str, list] = {}
        for emp in employees:
            title = emp.job_title or "Unknown"
            if title not in role_groups:
                role_groups[title] = []
            role_groups[title].append({
                "is_saudi": emp.is_saudi,
                "salary_sar": emp.salary_sar,
                "work_mode": emp.work_mode.value if emp.work_mode else "onsite",
            })

        # Use Claude to analyze automation potential
        roles_text = "\n".join(
            f"- {title} ({len(emps)} employees, avg salary {sum(e['salary_sar'] or 0 for e in emps) // max(len(emps),1)} SAR)"
            for title, emps in role_groups.items()
        )

        analysis_prompt = f"""Analyze these roles in a {dept.name} department for AI automation potential.
For each role, score 1-10 on:
- repetitiveness (10 = highly repetitive, ideal for AI)
- judgment_needed (10 = requires deep human judgment, hard to automate)
- compliance_sensitivity (10 = heavily regulated, needs human oversight)

Roles:
{roles_text}

Respond in JSON format:
{{"roles": [{{"role_title": "...", "headcount": N, "repetitiveness": N, "judgment_needed": N, "compliance_sensitivity": N, "ai_automation_pct": N, "recommendation": "full_automate|augment|human_only", "rationale": "..."}}]}}"""

        try:
            analysis_text = await self._claude_call(
                model="claude-haiku-4-5-20251001",
                max_tokens=2000,
                messages=[{"role": "user", "content": analysis_prompt}],
            )
            start = analysis_text.find("{")
            end = analysis_text.rfind("}") + 1
            if start >= 0 and end > start:
                raw = analysis_text[start:end]
                raw = _re.sub(r',\s*([}\]])', r'\1', raw)
                raw = _re.sub(r'//[^\n]*', '', raw)
                analysis = json.loads(raw)
            else:
                analysis = {"roles": []}
        except Exception as e:
            logger.warning(f"AI analysis failed, using heuristic: {e}")
            analysis = {"roles": [
                {
                    "role_title": title,
                    "headcount": len(emps),
                    "repetitiveness": 5,
                    "judgment_needed": 5,
                    "compliance_sensitivity": 5,
                    "ai_automation_pct": 30,
                    "recommendation": "augment",
                    "rationale": "Default heuristic — detailed analysis unavailable.",
                }
                for title, emps in role_groups.items()
            ]}

        return json.dumps({
            "department": dept.name,
            "department_ar": dept.name_ar,
            "department_id": str(department_id),
            "total_employees": len(employees),
            "unique_roles": len(role_groups),
            "analysis": analysis,
            "summary": {
                "automatable_roles": sum(1 for r in analysis.get("roles", []) if r.get("recommendation") == "full_automate"),
                "augmentable_roles": sum(1 for r in analysis.get("roles", []) if r.get("recommendation") == "augment"),
                "human_only_roles": sum(1 for r in analysis.get("roles", []) if r.get("recommendation") == "human_only"),
            },
        })

    async def _recommend_workforce_mix(
        self, department_id: UUID, target_headcount: int | None = None
    ) -> str:
        """Recommend optimal human:AI ratio for a department."""
        if not self._can_access_department(department_id):
            return json.dumps({"error": True, "message": "You can only view recommendations for your own department."})
        # Get current state
        overview_json = await self._get_department_overview(str(department_id))
        overview = json.loads(overview_json)

        if not overview.get("departments"):
            return json.dumps({"error": "Department not found."})

        dept = overview["departments"][0]
        current_hc = dept["headcount"]
        current_ai = dept["ai_agents_deployed"]
        saudi_count = dept["saudi_count"]

        # Get analysis
        analysis_json = await self._analyze_department(department_id)
        analysis = json.loads(analysis_json)

        if "error" in analysis:
            return analysis_json

        roles = analysis.get("analysis", {}).get("roles", [])

        # Calculate recommended AI agents
        recommended_agents = []
        total_automatable_hc = 0

        for role in roles:
            if role.get("recommendation") == "full_automate":
                hc = role.get("headcount", 1)
                # AI replaces ~70% of headcount for fully automatable roles
                ai_replacement = max(1, round(hc * 0.7))
                total_automatable_hc += ai_replacement
                recommended_agents.append({
                    "agent_role": role["role_title"],
                    "replaces_headcount": ai_replacement,
                    "estimated_monthly_cost_sar": 2000,  # API + infrastructure
                    "human_equivalent_monthly_cost_sar": (dept["avg_salary_sar"] * ai_replacement) * 1.22,
                })
            elif role.get("recommendation") == "augment":
                recommended_agents.append({
                    "agent_role": f"{role['role_title']} Assistant",
                    "replaces_headcount": 0,
                    "estimated_monthly_cost_sar": 1500,
                    "human_equivalent_monthly_cost_sar": 0,
                    "note": "Augments existing staff — no headcount reduction.",
                })

        recommended_humans = current_hc - total_automatable_hc
        if target_headcount:
            recommended_humans = min(recommended_humans, target_headcount)
        recommended_humans = max(recommended_humans, saudi_count)  # can't go below Saudi count

        # Saudization impact (AI agents don't count toward headcount for Nitaqat)
        new_human_hc = recommended_humans
        saudization_after = round(saudi_count / max(new_human_hc, 1) * 100, 1)

        # Cost comparison
        current_annual_cost = dept["annual_total_cost_sar"]
        ai_annual_cost = sum(a["estimated_monthly_cost_sar"] for a in recommended_agents) * 12
        new_human_annual_cost = round(current_annual_cost * (new_human_hc / max(current_hc, 1)))
        total_new_cost = new_human_annual_cost + ai_annual_cost
        annual_savings = current_annual_cost - total_new_cost

        return json.dumps({
            "department": dept["name"],
            "current_state": {
                "humans": current_hc,
                "ai_agents": current_ai,
                "saudization_pct": dept["saudization_pct"],
                "annual_cost_sar": current_annual_cost,
            },
            "recommended_state": {
                "humans": new_human_hc,
                "ai_agents": len([a for a in recommended_agents if a.get("replaces_headcount", 0) > 0]),
                "ai_assistants": len([a for a in recommended_agents if a.get("replaces_headcount", 0) == 0]),
                "saudization_pct": saudization_after,
                "annual_cost_sar": total_new_cost,
            },
            "recommended_agents": recommended_agents,
            "financial_impact": {
                "annual_savings_sar": max(annual_savings, 0),
                "savings_pct": round(max(annual_savings, 0) / max(current_annual_cost, 1) * 100, 1),
                "roi_months": round(50000 / max(annual_savings / 12, 1)) if annual_savings > 0 else None,
            },
            "saudization_impact": {
                "before_pct": dept["saudization_pct"],
                "after_pct": saudization_after,
                "note": "AI agents do not count in Nitaqat calculations. Removing non-Saudi roles improves the ratio.",
            },
        })

    async def _simulate_scenario(
        self,
        department_id: UUID,
        add_humans: int = 0,
        add_ai_agents: int = 0,
        role_descriptions: str | None = None,
    ) -> str:
        """Simulate workforce change scenarios."""
        if not self._can_access_department(department_id):
            return json.dumps({"error": True, "message": "You can only simulate scenarios for your own department."})
        overview_json = await self._get_department_overview(str(department_id))
        overview = json.loads(overview_json)

        if not overview.get("departments"):
            return json.dumps({"error": "Department not found."})

        dept = overview["departments"][0]
        current_hc = dept["headcount"]
        current_ai = dept["ai_agents_deployed"]
        current_cost = dept["annual_total_cost_sar"]
        saudi = dept["saudi_count"]

        # Projected state
        new_hc = max(current_hc + add_humans, 0)
        new_ai = max(current_ai + add_ai_agents, 0)

        # Cost projections
        avg_human_annual_cost = round(dept["avg_salary_sar"] * 12 * 1.22)  # salary + GOSI + benefits
        avg_ai_annual_cost = 24000  # ~2000 SAR/month per AI agent

        human_cost_delta = add_humans * avg_human_annual_cost
        ai_cost_delta = add_ai_agents * avg_ai_annual_cost
        new_cost = current_cost + human_cost_delta + ai_cost_delta

        # Saudization (only humans count)
        new_saudi_pct = round(saudi / max(new_hc, 1) * 100, 1)

        return json.dumps({
            "department": dept["name"],
            "scenario": {
                "add_humans": add_humans,
                "add_ai_agents": add_ai_agents,
                "role_descriptions": role_descriptions,
            },
            "current_state": {
                "humans": current_hc,
                "ai_agents": current_ai,
                "total_workforce": current_hc + current_ai,
                "annual_cost_sar": current_cost,
                "saudization_pct": dept["saudization_pct"],
            },
            "projected_state": {
                "humans": new_hc,
                "ai_agents": new_ai,
                "total_workforce": new_hc + new_ai,
                "annual_cost_sar": new_cost,
                "saudization_pct": new_saudi_pct,
            },
            "impact": {
                "cost_change_sar": new_cost - current_cost,
                "cost_change_pct": round((new_cost - current_cost) / max(current_cost, 1) * 100, 1),
                "saudization_change_pct": round(new_saudi_pct - dept["saudization_pct"], 1),
                "headcount_budget_remaining": (dept["headcount_budget"] or 0) - new_hc if dept["headcount_budget"] else None,
            },
        })

    async def _estimate_agent_roi(
        self, role_title: str, department_id: UUID, tasks_description: str = ""
    ) -> str:
        """Calculate ROI for a specific AI agent role."""
        if not self._can_access_department(department_id):
            return json.dumps({"error": True, "message": "You can only estimate ROI for your own department."})
        overview_json = await self._get_department_overview(str(department_id))
        overview = json.loads(overview_json)

        if not overview.get("departments"):
            return json.dumps({"error": "Department not found."})

        dept = overview["departments"][0]
        avg_salary = dept["avg_salary_sar"]

        # Estimates
        setup_cost = 15000  # one-time: prompt engineering, testing, deployment
        monthly_api_cost = 2000  # Claude API calls
        monthly_infra_cost = 500  # hosting, monitoring
        monthly_total = monthly_api_cost + monthly_infra_cost

        # Human equivalent (1 AI agent typically replaces 1-2 FTEs for routine work)
        human_equivalent_fte = 1.5
        human_monthly_cost = round(avg_salary * human_equivalent_fte * 1.22)  # salary + GOSI + benefits
        monthly_savings = human_monthly_cost - monthly_total
        annual_savings = monthly_savings * 12
        breakeven_months = round(setup_cost / max(monthly_savings, 1)) if monthly_savings > 0 else None

        return json.dumps({
            "role_title": role_title,
            "department": dept["name"],
            "tasks": tasks_description,
            "costs": {
                "setup_one_time_sar": setup_cost,
                "monthly_api_cost_sar": monthly_api_cost,
                "monthly_infrastructure_sar": monthly_infra_cost,
                "monthly_total_sar": monthly_total,
                "annual_total_sar": monthly_total * 12 + setup_cost,
            },
            "human_comparison": {
                "equivalent_fte": human_equivalent_fte,
                "monthly_human_cost_sar": human_monthly_cost,
                "annual_human_cost_sar": human_monthly_cost * 12,
            },
            "roi": {
                "monthly_savings_sar": monthly_savings,
                "annual_savings_sar": annual_savings,
                "breakeven_months": breakeven_months,
                "first_year_roi_pct": round((annual_savings - setup_cost) / max(setup_cost, 1) * 100, 1),
                "productivity_multiplier": "24/7 availability, 0 downtime, instant response",
            },
            "recommendation": "Deploy" if annual_savings > 0 else "Not cost-effective at current scale",
        })

    # ══════════════════════════════════════════════════════════════
    # S2 — AGENT FACTORY IMPLEMENTATIONS
    # ══════════════════════════════════════════════════════════════

    async def _design_agent(self, params: dict) -> str:
        """Use Claude to generate a complete agent specification."""
        role_title = params["role_title"]
        department_id = UUID(params["department_id"])
        tasks = params["tasks_description"]
        lang = params.get("language_preference", "bilingual")

        # Sanitize user-provided inputs before sending to Claude
        role_title_sanitized, role_flagged = sanitize_user_input(role_title)
        tasks_sanitized, tasks_flagged = sanitize_user_input(tasks)
        if role_flagged:
            logger.warning("Potential injection in role_title for design_agent")
        if tasks_flagged:
            logger.warning("Potential injection in tasks_description for design_agent")

        # Get department context
        dept_result = await self.db.execute(
            select(Department).where(
                Department.id == department_id,
                Department.tenant_id == self.tenant_id,
            )
        )
        dept = dept_result.scalar_one_or_none()
        dept_name = dept.name if dept else "Unknown"
        dept_name_sanitized, dept_flagged = sanitize_user_input(dept_name)
        if dept_flagged:
            logger.warning("Potential injection in department name for design_agent")

        lang_instruction = {
            "ar": "The agent should primarily respond in Arabic (Saudi dialect).",
            "en": "The agent should respond in English.",
            "bilingual": "The agent should be bilingual — respond in the language the user writes in (Arabic or English).",
        }.get(lang, "bilingual")

        design_prompt = f"""Design an AI agent for the following role in a Saudi organization.

Role: {role_title_sanitized}
Department: {dept_name_sanitized}
Tasks: {tasks_sanitized}
Language: {lang_instruction}

Generate a complete agent specification as JSON:
{{
  "personality": "2-3 sentence personality description",
  "system_prompt": "Full system prompt for the agent (include role, boundaries, cultural context, escalation instructions)",
  "tools": [
    {{"name": "tool_name", "description": "what it does", "input_schema": {{"type": "object", "properties": {{}}, "required": []}}}}
  ],
  "scope_boundaries": {{
    "allowed_actions": ["list of things the agent CAN do"],
    "forbidden_actions": ["list of things the agent must NOT do"],
    "data_access": ["what data the agent can access"]
  }},
  "escalation_rules": {{
    "escalate_when": ["conditions that trigger escalation"],
    "escalate_to": "human_manager"
  }},
  "suggested_name": "A Saudi name for the agent",
  "suggested_name_ar": "Arabic name"
}}

Important:
- Include Saudi cultural awareness in the system prompt
- Include Ramadan, Eid, and National Day awareness
- The agent must be professional yet warm
- Include escalation rules for sensitive or complex topics
- Tools should be specific to the role's tasks"""

        try:
            spec_text = await self._claude_call(
                model="claude-haiku-4-5-20251001",
                max_tokens=3000,
                system="You are a JSON generator. Return ONLY valid JSON with no comments, no trailing commas, and no text outside the JSON object. Use \\n for newlines inside string values.",
                messages=[{"role": "user", "content": design_prompt}],
            )
            start = spec_text.find("{")
            end = spec_text.rfind("}") + 1
            if start < 0 or end <= start:
                raise ValueError("No JSON found in response")
            raw_json = spec_text[start:end]
            raw_json = _re.sub(r',\s*([}\]])', r'\1', raw_json)
            raw_json = _re.sub(r'//[^\n]*', '', raw_json)
            raw_json = _re.sub(r'[\x00-\x1f]', lambda m: f'\\u{ord(m.group()):04x}' if m.group() not in ('\n', '\r', '\t') else m.group(), raw_json)
            raw_json = raw_json.replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
            raw_json = raw_json.replace('\\n  ', '\n  ').replace('\\n}', '\n}').replace('\\n]', '\n]')
            try:
                spec = json.loads(raw_json)
            except json.JSONDecodeError:
                retry_text = await self._claude_call(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=3000,
                    system="Fix the following broken JSON. Return ONLY the corrected JSON, nothing else.",
                    messages=[{"role": "user", "content": raw_json}],
                )
                rs = retry_text.find("{")
                re_ = retry_text.rfind("}") + 1
                spec = json.loads(retry_text[rs:re_])
        except Exception as e:
            logger.error(f"Agent design failed: {e}")
            return json.dumps({"error": "Failed to generate agent design. Please try again."})

        spec["role_title"] = role_title
        spec["department_id"] = str(department_id)
        spec["department_name"] = dept_name
        spec["status"] = "spec_ready"
        spec["note"] = "Review this specification. Use create_agent to deploy it."

        return json.dumps(spec)

    async def _create_agent(self, params: dict) -> str:
        """Save a new AI agent to the database."""
        try:
            # Fix 1: Validate department_id belongs to this tenant
            department_id = UUID(params["department_id"])
            dept_result = await self.db.execute(
                select(Department).where(
                    Department.id == department_id,
                    Department.tenant_id == self.tenant_id,
                )
            )
            if not dept_result.scalar_one_or_none():
                return json.dumps({"error": "Department not found or does not belong to your organization."})

            # Fix 3: Sanitize system_prompt before storing
            system_prompt = params["system_prompt"]
            sanitized_prompt, was_flagged = sanitize_user_input(system_prompt)
            if was_flagged:
                logger.warning("Potential prompt injection detected in system_prompt for create_agent")

            agent = DeployedAgent(
                id=_uuid.uuid4(),
                tenant_id=self.tenant_id,
                department_id=department_id,
                name=params["name"],
                name_ar=params.get("name_ar"),
                role_title=params["role_title"],
                role_title_ar=params.get("role_title_ar"),
                personality=params.get("personality"),
                system_prompt=sanitized_prompt,
                tools_config=params.get("tools_config", []),
                scope_boundaries=params.get("scope_boundaries", {}),
                escalation_rules=params.get("escalation_rules", {}),
                status=AgentStatus.draft,
                created_by=UUID(self._employee_id) if self._employee_id else None,
            )
            self.db.add(agent)
            await self.db.flush()

            return json.dumps({
                "status": "created",
                "agent_id": str(agent.id),
                "name": agent.name,
                "role_title": agent.role_title,
                "department_id": str(agent.department_id),
                "current_status": "draft",
                "next_step": "Use activate_agent to make this agent live.",
            })
        except Exception as e:
            logger.error(f"Failed to create agent: {e}")
            return json.dumps({"error": "Failed to create agent. Please check the input and try again."})

    async def _activate_agent(self, agent_id: UUID) -> str:
        """Activate a deployed agent."""
        result = await self.db.execute(
            select(DeployedAgent).where(
                DeployedAgent.id == agent_id,
                DeployedAgent.tenant_id == self.tenant_id,
            )
        )
        agent = result.scalar_one_or_none()

        if not agent:
            return json.dumps({"error": "Agent not found."})

        if agent.status == AgentStatus.active:
            return json.dumps({"message": f"Agent '{agent.name}' is already active."})

        if agent.status == AgentStatus.archived:
            return json.dumps({"error": "Cannot activate an archived agent. Create a new one instead."})

        agent.status = AgentStatus.active
        agent.updated_at = datetime.now(timezone.utc)
        await self.db.flush()

        return json.dumps({
            "status": "activated",
            "agent_id": str(agent.id),
            "name": agent.name,
            "role_title": agent.role_title,
            "message": f"Agent '{agent.name}' is now live and available for conversations in the {agent.role_title} role.",
        })

    # Standard tool names reserved by DynamicAgent — custom tools must not shadow these.
    STANDARD_TOOL_NAMES = {"search_knowledge_base", "escalate_to_human", "lookup_employee"}

    async def _configure_agent_tools(self, agent_id: UUID, tools_config: list) -> str:
        """Update an agent's tool definitions."""
        # Fix 4: Check for tool name collisions with standard tools
        custom_names = {t.get("name") for t in tools_config if t.get("name")}
        collisions = custom_names & self.STANDARD_TOOL_NAMES
        if collisions:
            return json.dumps({
                "error": "Tool name collision with standard tools.",
                "conflicting_names": sorted(collisions),
                "message": f"These tool names are reserved: {', '.join(sorted(collisions))}. Please choose different names.",
            })

        result = await self.db.execute(
            select(DeployedAgent).where(
                DeployedAgent.id == agent_id,
                DeployedAgent.tenant_id == self.tenant_id,
            )
        )
        agent = result.scalar_one_or_none()

        if not agent:
            return json.dumps({"error": "Agent not found."})

        agent.tools_config = tools_config
        agent.updated_at = datetime.now(timezone.utc)
        await self.db.flush()

        return json.dumps({
            "status": "updated",
            "agent_id": str(agent.id),
            "name": agent.name,
            "tools_count": len(tools_config),
            "tool_names": [t.get("name", "unnamed") for t in tools_config],
        })

    async def _set_escalation_rules(self, agent_id: UUID, rules: dict) -> str:
        """Update an agent's escalation rules."""
        result = await self.db.execute(
            select(DeployedAgent).where(
                DeployedAgent.id == agent_id,
                DeployedAgent.tenant_id == self.tenant_id,
            )
        )
        agent = result.scalar_one_or_none()

        if not agent:
            return json.dumps({"error": "Agent not found."})

        agent.escalation_rules = rules
        agent.updated_at = datetime.now(timezone.utc)
        await self.db.flush()

        return json.dumps({
            "status": "updated",
            "agent_id": str(agent.id),
            "name": agent.name,
            "escalation_rules": rules,
        })

    async def _list_deployed_agents(
        self, department_id: str | None = None, status: str | None = None
    ) -> str:
        """List all deployed AI agents."""
        # Fix 6: Single query with outerjoin to count conversations (avoids N+1)
        # Conversation.agent_name stores department agents as "dept:{agent_id}"
        from sqlalchemy import literal, cast, String
        agent_name_expr = func.concat(literal("dept:"), cast(DeployedAgent.id, String))

        query = (
            select(
                DeployedAgent,
                func.count(Conversation.id).label("conv_count"),
            )
            .outerjoin(
                Conversation,
                (Conversation.agent_name == agent_name_expr)
                & (Conversation.tenant_id == self.tenant_id),
            )
            .where(DeployedAgent.tenant_id == self.tenant_id)
            .group_by(DeployedAgent.id)
            .order_by(DeployedAgent.created_at.desc())
        )

        if department_id:
            query = query.where(DeployedAgent.department_id == UUID(department_id))
        if status:
            query = query.where(DeployedAgent.status == AgentStatus(status))

        result = await self.db.execute(query)
        rows = result.all()

        agent_list = []
        for row in rows:
            a = row[0]  # DeployedAgent
            conversations = row.conv_count or 0

            agent_list.append({
                "agent_id": str(a.id),
                "name": a.name,
                "name_ar": a.name_ar,
                "role_title": a.role_title,
                "department_id": str(a.department_id),
                "status": a.status.value,
                "tools_count": len(a.tools_config or []),
                "conversations_total": conversations,
                "performance": a.performance_metrics or {},
                "created_at": a.created_at.isoformat() if a.created_at else None,
            })

        return json.dumps({
            "agents": agent_list,
            "total": len(agent_list),
        })

    # ══════════════════════════════════════════════════════════════
    # S3 — GOVERNANCE IMPLEMENTATIONS
    # ══════════════════════════════════════════════════════════════

    async def _get_agent_performance(self, agent_id: UUID, days: int = 30) -> str:
        """Get performance metrics for a deployed agent."""
        # Verify agent exists
        result = await self.db.execute(
            select(DeployedAgent).where(
                DeployedAgent.id == agent_id,
                DeployedAgent.tenant_id == self.tenant_id,
            )
        )
        agent = result.scalar_one_or_none()
        if not agent:
            return json.dumps({"error": "Agent not found."})

        agent_name = f"dept:{agent_id}"
        cutoff = datetime.utcnow() - timedelta(days=days)

        # Total conversations
        total_result = await self.db.execute(
            select(func.count(Conversation.id)).where(
                Conversation.agent_name == agent_name,
                Conversation.tenant_id == self.tenant_id,
                Conversation.started_at >= cutoff,
            )
        )
        total = total_result.scalar() or 0

        # Resolved conversations
        resolved_result = await self.db.execute(
            select(func.count(Conversation.id)).where(
                Conversation.agent_name == agent_name,
                Conversation.tenant_id == self.tenant_id,
                Conversation.started_at >= cutoff,
                Conversation.status == "resolved",
            )
        )
        resolved = resolved_result.scalar() or 0

        # Escalated
        escalated_result = await self.db.execute(
            select(func.count(Conversation.id)).where(
                Conversation.agent_name == agent_name,
                Conversation.tenant_id == self.tenant_id,
                Conversation.started_at >= cutoff,
                Conversation.status == "escalated",
            )
        )
        escalated = escalated_result.scalar() or 0

        # Average messages per conversation
        avg_msgs_result = await self.db.execute(
            select(func.avg(
                select(func.count(Message.id))
                .where(Message.conversation_id == Conversation.id)
                .correlate(Conversation)
                .scalar_subquery()
            )).where(
                Conversation.agent_name == agent_name,
                Conversation.tenant_id == self.tenant_id,
                Conversation.started_at >= cutoff,
            )
        )
        avg_messages = round(avg_msgs_result.scalar() or 0, 1)

        # Average satisfaction
        sat_result = await self.db.execute(
            select(func.avg(Conversation.satisfaction_score)).where(
                Conversation.agent_name == agent_name,
                Conversation.tenant_id == self.tenant_id,
                Conversation.started_at >= cutoff,
                Conversation.satisfaction_score.isnot(None),
            )
        )
        avg_satisfaction = round(sat_result.scalar() or 0, 2)

        metrics = {
            "agent_id": str(agent_id),
            "agent_name": agent.name,
            "role_title": agent.role_title,
            "period_days": days,
            "total_conversations": total,
            "resolved": resolved,
            "escalated": escalated,
            "active": total - resolved - escalated,
            "resolution_rate_pct": round(resolved / max(total, 1) * 100, 1),
            "escalation_rate_pct": round(escalated / max(total, 1) * 100, 1),
            "avg_messages_per_conversation": avg_messages,
            "avg_satisfaction_score": avg_satisfaction,
        }

        # Update stored metrics
        agent.performance_metrics = metrics
        agent.updated_at = datetime.now(timezone.utc)
        await self.db.flush()

        return json.dumps(metrics)

    async def _detect_drift(self, agent_id: UUID) -> str:
        """Detect scope drift in a deployed agent's conversations."""
        result = await self.db.execute(
            select(DeployedAgent).where(
                DeployedAgent.id == agent_id,
                DeployedAgent.tenant_id == self.tenant_id,
            )
        )
        agent = result.scalar_one_or_none()
        if not agent:
            return json.dumps({"error": "Agent not found."})

        agent_name = f"dept:{agent_id}"

        # Get recent conversations with messages
        conv_result = await self.db.execute(
            select(Conversation)
            .where(
                Conversation.agent_name == agent_name,
                Conversation.tenant_id == self.tenant_id,
            )
            .order_by(Conversation.started_at.desc())
            .limit(10)
        )
        conversations = conv_result.scalars().all()

        if not conversations:
            return json.dumps({
                "agent_id": str(agent_id),
                "drift_score": 0,
                "message": "No conversations to analyze.",
            })

        # Collect sample messages
        samples = []
        for conv in conversations[:5]:
            msg_result = await self.db.execute(
                select(Message.content, Message.role)
                .where(Message.conversation_id == conv.id)
                .order_by(Message.created_at)
                .limit(6)
            )
            msgs = msg_result.all()
            samples.append({
                "conversation_id": str(conv.id),
                "messages": [{"role": m.role, "content": m.content[:200]} for m in msgs],
            })

        # Use Claude to analyze drift
        scope = agent.scope_boundaries or {}
        drift_prompt = f"""Analyze these conversations from an AI agent for scope drift.

Agent Role: {agent.role_title}
Allowed Actions: {json.dumps(scope.get('allowed_actions', []))}
Forbidden Actions: {json.dumps(scope.get('forbidden_actions', []))}

Recent Conversations:
{json.dumps(samples, ensure_ascii=False)}

Respond in JSON:
{{
  "drift_score": 0-100 (0=perfectly on scope, 100=completely off scope),
  "flagged_conversations": [{{"conversation_id": "...", "issue": "description of drift"}}],
  "recommendations": ["list of improvements"]
}}"""

        try:
            drift_text = await self._claude_call(
                model="claude-haiku-4-5-20251001",
                max_tokens=1500,
                messages=[{"role": "user", "content": drift_prompt}],
            )
            start = drift_text.find("{")
            end = drift_text.rfind("}") + 1
            if start >= 0 and end > start:
                raw = drift_text[start:end]
                raw = _re.sub(r',\s*([}\]])', r'\1', raw)
                raw = _re.sub(r'//[^\n]*', '', raw)
                drift = json.loads(raw)
            else:
                drift = {"drift_score": 0, "flagged_conversations": [], "recommendations": []}
        except Exception as e:
            logger.warning(f"Drift detection failed: {e}")
            drift = {"drift_score": 0, "flagged_conversations": [], "recommendations": ["Analysis unavailable"]}

        drift["agent_id"] = str(agent_id)
        drift["agent_name"] = agent.name
        drift["conversations_analyzed"] = len(samples)
        return json.dumps(drift)

    async def _update_agent_prompt(self, agent_id: UUID, new_prompt: str) -> str:
        """Hot-update an agent's system prompt."""
        result = await self.db.execute(
            select(DeployedAgent).where(
                DeployedAgent.id == agent_id,
                DeployedAgent.tenant_id == self.tenant_id,
            )
        )
        agent = result.scalar_one_or_none()
        if not agent:
            return json.dumps({"error": "Agent not found."})

        # Fix 3: Sanitize the new prompt before storing
        sanitized_prompt, was_flagged = sanitize_user_input(new_prompt)
        if was_flagged:
            logger.warning(f"Potential prompt injection detected in update_agent_prompt for agent {agent_id}")

        old_prompt_preview = (agent.system_prompt or "")[:100]
        agent.system_prompt = sanitized_prompt
        agent.updated_at = datetime.now(timezone.utc)
        await self.db.flush()

        return json.dumps({
            "status": "updated",
            "agent_id": str(agent_id),
            "name": agent.name,
            "old_prompt_preview": old_prompt_preview + "...",
            "new_prompt_length": len(new_prompt),
            "note": "Prompt updated. Next conversation will use the new prompt.",
        })

    async def _deactivate_agent(self, agent_id: UUID, action: str = "pause", reason: str = "") -> str:
        """Deactivate a deployed agent."""
        result = await self.db.execute(
            select(DeployedAgent).where(
                DeployedAgent.id == agent_id,
                DeployedAgent.tenant_id == self.tenant_id,
            )
        )
        agent = result.scalar_one_or_none()
        if not agent:
            return json.dumps({"error": "Agent not found."})

        if action == "archive":
            agent.status = AgentStatus.archived
        else:
            agent.status = AgentStatus.paused

        agent.updated_at = datetime.now(timezone.utc)
        await self.db.flush()

        return json.dumps({
            "status": agent.status.value,
            "agent_id": str(agent_id),
            "name": agent.name,
            "action": action,
            "reason": reason,
            "message": f"Agent '{agent.name}' has been {action}d.",
        })

    async def _generate_governance_report(
        self, department_id: str | None = None, days: int = 30
    ) -> str:
        """Generate comprehensive AI workforce governance report."""
        query = select(DeployedAgent).where(DeployedAgent.tenant_id == self.tenant_id)
        if department_id:
            query = query.where(DeployedAgent.department_id == UUID(department_id))

        result = await self.db.execute(query)
        agents = result.scalars().all()

        # Aggregate metrics
        active_agents = [a for a in agents if a.status == AgentStatus.active]
        draft_agents = [a for a in agents if a.status == AgentStatus.draft]
        paused_agents = [a for a in agents if a.status == AgentStatus.paused]

        # Collect performance data
        agent_summaries = []
        total_conversations = 0
        total_resolved = 0
        total_escalated = 0

        for a in active_agents:
            metrics = a.performance_metrics or {}
            convs = metrics.get("total_conversations", 0)
            total_conversations += convs
            total_resolved += metrics.get("resolved", 0)
            total_escalated += metrics.get("escalated", 0)

            agent_summaries.append({
                "name": a.name,
                "role": a.role_title,
                "conversations": convs,
                "resolution_rate": metrics.get("resolution_rate_pct", 0),
                "escalation_rate": metrics.get("escalation_rate_pct", 0),
            })

        # Estimated cost savings
        avg_ai_monthly = 2500  # avg per agent
        avg_human_monthly = 12000  # avg Saudi market salary + GOSI
        monthly_savings = len(active_agents) * (avg_human_monthly - avg_ai_monthly)

        return json.dumps({
            "report_period_days": days,
            "scope": f"Department: {department_id}" if department_id else "Organization-wide",
            "agent_inventory": {
                "total": len(agents),
                "active": len(active_agents),
                "draft": len(draft_agents),
                "paused": len(paused_agents),
                "archived": len([a for a in agents if a.status == AgentStatus.archived]),
            },
            "performance_summary": {
                "total_conversations": total_conversations,
                "total_resolved": total_resolved,
                "total_escalated": total_escalated,
                "overall_resolution_rate_pct": round(total_resolved / max(total_conversations, 1) * 100, 1),
                "overall_escalation_rate_pct": round(total_escalated / max(total_conversations, 1) * 100, 1),
            },
            "agent_details": agent_summaries,
            "financial_summary": {
                "monthly_ai_cost_sar": len(active_agents) * avg_ai_monthly,
                "human_equivalent_cost_sar": len(active_agents) * avg_human_monthly,
                "monthly_savings_sar": monthly_savings,
                "annual_savings_sar": monthly_savings * 12,
            },
            "recommendations": [
                "Review draft agents and activate those that are ready.",
                "Run drift detection on active agents monthly.",
                "Update prompts for agents with high escalation rates.",
            ] if agents else ["No AI agents deployed yet. Use analyze_department to identify opportunities."],
        })
