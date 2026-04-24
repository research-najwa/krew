"""Agent orchestrator -- routes incoming messages to the correct agent.

Supports both super agents (hardcoded) and department agents (loaded from DB).
Department agents use the naming convention 'dept:{uuid}'.

Sprint 8 Track 5: @mention routing with access control and sticky mentions.
"""
import logging
import re
from uuid import UUID

import anthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.agents.deema import DeemaAgent
from app.agents.waleed import WaleedAgent
from app.agents.mohammad import MohammadAgent
from app.agents.yara import YaraAgent
from app.agents.ahmad import AhmadAgent
from app.agents.dynamic_agent import DynamicAgent
from app.models.deployed_agent import DeployedAgent, AgentStatus
from app.utils.mention_parser import parse_mention, get_mentioned_raw
from app.utils.agent_access import check_agent_access, get_accessible_agents

logger = logging.getLogger(__name__)
settings = get_settings()


def _normalize_alef(text: str) -> str:
    """Replace all alef variants (إ أ آ ٱ) with bare alef (ا) for fuzzy Arabic matching."""
    return text.replace("إ", "ا").replace("أ", "ا").replace("آ", "ا").replace("ٱ", "ا")

# Agent registry
AGENTS = {
    "deema": DeemaAgent,
    "waleed": WaleedAgent,
    "mohammad": MohammadAgent,
    "yara": YaraAgent,
    "ahmad": AhmadAgent,
}

# Intent-to-agent mapping for automatic routing
INTENT_KEYWORDS = {
    "deema": [
        "leave", "vacation", "pto", "balance", "policy", "benefit", "salary",
        "help", "question", "إجازة", "رصيد", "سياسة", "راتب", "مساعدة",
        "طلباتي", "تذاكري", "my requests", "my tickets", "track",
        "profile", "my info", "contract", "my probation", "بياناتي", "ملفي", "عقد",
        "تجربة",
        # Leave request intent keywords
        "apply", "annual", "take leave", "sick leave",
        # Onboarding (moved from Waleed)
        "onboarding", "new hire", "checklist", "check-in", "checkin",
        "تعيين", "تهيئة", "جديد",
    ],
    "waleed": [
        # HRBP: manager & team tools
        "my team", "team members", "direct reports", "approve leave", "reject leave",
        "pending approval", "pending approvals", "pending leave", "leave approval",
        "فريقي", "موافقة", "رفض إجازة", "الموافقات", "طلبات الإجازة", "الإجازات المعلقة",
        "headcount", "عدد الموظفين",
        # New HRBP keywords
        "attrition", "probation", "team compensation", "salary overview",
        "one on one", "1:1", "pip", "performance improvement", "team compliance",
        "team attendance",
        "تعويضات", "أداء", "حضور",
    ],
    "mohammad": [
        "hire", "recruit", "candidate", "resume", "interview", "job",
        "توظيف", "مرشح", "وظيفة", "مقابلة",
        # M1 additions
        "posting", "pipeline", "screening", "screen", "shortlist",
        "jd", "job description", "applicant", "source", "sourcing", "talent",
        "وصف وظيفي", "مرشحين", "فحص", "تصفية", "إعلان وظيفي", "شاغر",
        "وش وضع التوظيف", "نبي نوظف", "خط التوظيف",
        "مختصرة", "قائمة مختصرة", "ترشيح", "مرشحة", "سيرة ذاتية",
        # M3 additions
        "transcript", "recording", "zoom", "تسجيل", "نص المقابلة",
        "offer", "عرض", "عرض وظيفي", "راتب مقترح",
        "وظّف", "وظفه", "وظفها", "نبي نوظفه", "نبي نوظفها", "تحويل مرشح",
        "evaluation summary", "ملخص التقييم", "تقرير المرشح",
        # Salary benchmarking (recruitment context)
        "benchmark", "benchmarking", "salary range", "market rate", "compensation",
        "مقارنة رواتب", "نطاق الراتب", "راتب السوق",
    ],
    "yara": [
        "automate", "ai ready",
        "workforce mix",
        "ai agent", "department agent", "agent performance",
        "governance report", "drift detection", "activate agent", "deactivate agent",
        "أتمتة", "ذكاء اصطناعي", "وكيل", "نسبة القوى العاملة",
    ],
    "ahmad": [
        "analytics", "compliance", "regulation", "labor law", "audit",
        "budget", "cost", "forecast", "turnover",
        "workforce metrics", "executive",
        "dashboard", "salary distribution", "hr metrics", "chro",
        "تحليلات", "امتثال", "نظام", "قانون", "ميزانية", "تكلفة", "تحليل",
        "دوران وظيفي", "مقاييس", "لوحة المعلومات",
        "توزيع الرواتب",
        # A2 cross-domain analytics keywords
        "recruitment funnel", "time to fill", "hiring analytics",
        "leave trends", "leave analytics", "leave usage",
        "attendance rate", "overtime analytics", "late arrivals",
        "onboarding progress", "onboarding completion", "bottleneck steps",
        "payroll cost", "payroll trend", "gosi breakdown",
        "تحليل التوظيف", "تحليل الإجازات", "تحليل الحضور",
        "تكلفة الرواتب", "تحليل التأهيل",
        # A3 predictive analytics keywords (multi-word to avoid conflicts)
        "attrition risk", "retention risk", "predict attrition",
        "budget forecast", "payroll forecast", "cost projection",
        "gosi audit", "gosi compliance", "contribution audit",
        "policy acknowledgment", "policy compliance", "acknowledgment tracking",
        "custom report", "generate report", "combined report",
        "مخاطر التسرب", "توقعات الميزانية", "تدقيق التأمينات",
        "إقرار السياسات", "تقرير مخصص",
    ],
}


# High-signal keywords: each match contributes 2 points (vs 1 for INTENT_KEYWORDS).
# These are short, unambiguous verbs/nouns that should reliably trigger the
# strong-override threshold (>= 2) on their own, even for punchy messages like
# "build agent" or "hire someone". Keep these strictly unique across agents and
# disjoint from the 1-point INTENT_KEYWORDS lists.
HIGH_SIGNAL_KEYWORDS: dict[str, list[str]] = {
    "deema": [
        "leave balance", "apply for leave", "payslip", "request leave",
        "كشف راتب", "تقديم إجازة", "طلب إجازة",
        "onboard me", "onboard new", "first day", "orientation",
    ],
    "waleed": [
        "team dashboard", "flight risk", "probation tracker", "compensation overview",
        "prepare one on one", "action items", "generate pip",
        "لوحة الفريق", "مخاطر الاستقالة",
    ],
    "mohammad": [
        "hire someone", "schedule interview", "job opening", "new candidate",
        "وظّف شخص",
    ],
    "yara": [
        "build agent", "design agent", "deploy agent", "agent factory",
        "virtual employee", "workforce plan", "ai workforce",
        "أنشئ وكيل", "صمم وكيل",
    ],
    "ahmad": [
        "saudization", "nitaqat", "compliance audit", "executive report",
        "سعودة", "نطاقات",
    ],
}


# Startup check: no keyword appears in multiple agents' lists, and HIGH_SIGNAL
# keywords never collide with another agent's INTENT keywords.
def _validate_keyword_uniqueness() -> None:
    seen: dict[str, str] = {}
    for agent_name, keywords in INTENT_KEYWORDS.items():
        for kw in keywords:
            if kw in seen:
                raise RuntimeError(
                    f"Keyword '{kw}' is assigned to both '{seen[kw]}' and '{agent_name}'. "
                    "Each keyword must belong to exactly one agent."
                )
            seen[kw] = agent_name

    # HIGH_SIGNAL must be unique across agents, and must not appear in ANOTHER
    # agent's INTENT_KEYWORDS (same-agent overlap is forbidden too to avoid
    # accidental 1+2=3 double-counting from a single occurrence).
    high_seen: dict[str, str] = {}
    for agent_name, keywords in HIGH_SIGNAL_KEYWORDS.items():
        for kw in keywords:
            if kw in high_seen:
                raise RuntimeError(
                    f"HIGH_SIGNAL keyword '{kw}' is assigned to both "
                    f"'{high_seen[kw]}' and '{agent_name}'."
                )
            if kw in seen:
                raise RuntimeError(
                    f"HIGH_SIGNAL keyword '{kw}' for agent '{agent_name}' "
                    f"also appears in INTENT_KEYWORDS for agent '{seen[kw]}'. "
                    "HIGH_SIGNAL keywords must be disjoint from all INTENT_KEYWORDS."
                )
            high_seen[kw] = agent_name

_validate_keyword_uniqueness()


class AgentOrchestrator:
    """Routes messages to the appropriate Krew agent."""

    def __init__(self, db: AsyncSession, tenant_id: UUID):
        self.db = db
        self.tenant_id = tenant_id
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.last_agent = None  # Expose the last agent instance for suggestion extraction

    def get_agent(self, agent_name: str):
        """Get an agent instance by name. Supports 'dept:{uuid}' for dynamic agents."""
        agent_class = AGENTS.get(agent_name, DeemaAgent)  # default to Deema
        return agent_class(self.db, self.tenant_id)

    async def get_dynamic_agent(self, agent_name: str) -> DynamicAgent | None:
        """Load a department agent from DB. Returns None if not found or not active."""
        if not agent_name.startswith("dept:"):
            return None
        try:
            agent_id = UUID(agent_name[5:])
        except ValueError:
            return None

        result = await self.db.execute(
            select(DeployedAgent).where(
                DeployedAgent.id == agent_id,
                DeployedAgent.tenant_id == self.tenant_id,
                DeployedAgent.status == AgentStatus.active,
            )
        )
        config = result.scalar_one_or_none()
        if not config:
            return None

        return DynamicAgent(self.db, self.tenant_id, config)

    async def _resolve_deployed_agent_mention(self, raw_name: str) -> str | None:
        """Try to match a raw mention name to a deployed agent. Returns UUID string or None."""
        from sqlalchemy import or_, func
        name_lower = raw_name.lower().strip()
        result = await self.db.execute(
            select(DeployedAgent.id).where(
                DeployedAgent.tenant_id == self.tenant_id,
                DeployedAgent.status == AgentStatus.active,
                or_(
                    func.lower(DeployedAgent.name) == name_lower,
                    func.lower(DeployedAgent.name_ar) == name_lower,
                ),
            ).limit(1)
        )
        row = result.scalar_one_or_none()
        return str(row) if row else None

    async def _get_deployed_agent_names(self) -> list[str]:
        """Get names of all active deployed agents for error messages."""
        result = await self.db.execute(
            select(DeployedAgent.name).where(
                DeployedAgent.tenant_id == self.tenant_id,
                DeployedAgent.status == AgentStatus.active,
            )
        )
        return [row[0] for row in result.all()]

    # Explicit agent switch phrases -- user must name the agent to switch
    SWITCH_PHRASES: dict[str, list[str]] = {
        "deema": ["حول لديمة", "كلم ديمة", "switch to deema", "talk to deema"],
        "waleed": ["حول لوليد", "كلم وليد", "switch to waleed", "talk to waleed"],
        "mohammad": ["حول لمحمد", "كلم محمد", "switch to mohammad", "talk to mohammad"],
        "yara": [
            "حول ليارا", "كلم يارا", "switch to yara", "talk to yara",
            "حول لسارة", "كلم سارة", "switch to sarah", "talk to sarah",
        ],
        "ahmad": [
            "حول لاحمد", "كلم احمد", "switch to ahmad", "talk to ahmad",
            "حول لنورة", "كلم نورة", "switch to norah", "talk to norah",
        ],
    }

    # Minimum keyword score required to override an explicit current_agent
    # selection (e.g., user picked Ahmad in the sidebar but asked about leave).
    STRONG_OVERRIDE_THRESHOLD = 2

    HIGH_SIGNAL_KEYWORDS = HIGH_SIGNAL_KEYWORDS

    def _score_intents(self, message_lower: str) -> dict[str, int]:
        """Score each agent by keyword matches. HIGH_SIGNAL keywords contribute
        2 points per match; regular INTENT_KEYWORDS contribute 1 point each.

        Alef normalization is applied so that إجازة, أجازة, اجازة all match.
        """
        scores: dict[str, int] = {}
        msg_normalized = _normalize_alef(message_lower)
        for agent, keywords in self.HIGH_SIGNAL_KEYWORDS.items():
            for kw in keywords:
                if _normalize_alef(kw) in msg_normalized:
                    scores[agent] = scores.get(agent, 0) + 2
        for agent, keywords in INTENT_KEYWORDS.items():
            for kw in keywords:
                if _normalize_alef(kw) in msg_normalized:
                    scores[agent] = scores.get(agent, 0) + 1
        return scores

    async def route(
        self,
        message: str,
        current_agent: str | None = None,
        employee_id: UUID | None = None,
        employee_role: str | None = None,
        employee_dept_id: UUID | None = None,
        last_mentioned_agent: str | None = None,
    ) -> tuple[str, str, str | None]:
        """Determine which agent should handle this message.

        Returns:
            (agent_name, cleaned_message, error_message)
            - error_message is None on success, or a user-facing string on failure.
            - When error_message is set, agent_name is "system" and the orchestrator
              should return the error directly instead of calling an agent.

        Priority:
            1. @mention (explicit) -- highest priority
            2. last_mentioned_agent (sticky @mention per conversation)
            3. SWITCH_PHRASES (explicit agent switch)
            4. Strong keyword override -- if the message has a clear,
               unambiguous intent for a DIFFERENT agent than the one the user
               currently has selected, route to that agent. This prevents
               sidebar stickiness from trapping messages like "apply for annual
               leave" inside Ahmad's context.
            5. current_agent (sticky conversation agent)
            6. INTENT_KEYWORDS (keyword scoring fallback)
            7. Default to "deema"
        """
        message_lower = message.lower()

        # -- 1. @mention routing (highest priority) --
        mentioned_agent, cleaned_message = parse_mention(message)

        if mentioned_agent is not None:
            # Valid recognized agent
            if mentioned_agent in AGENTS or mentioned_agent.startswith("dept:"):
                # Access check
                if employee_id and employee_role is not None:
                    has_access = await check_agent_access(
                        self.db, self.tenant_id, employee_id,
                        employee_role, employee_dept_id, mentioned_agent,
                    )
                    if not has_access:
                        accessible = await get_accessible_agents(
                            self.db, self.tenant_id, employee_id,
                            employee_role, employee_dept_id,
                        )
                        agent_list = ", ".join(f"@{a}" for a in accessible)
                        raw = get_mentioned_raw(message) or f"@{mentioned_agent}"
                        error = (
                            f"You don't have access to {raw}. "
                            f"Available agents: {agent_list}\n\n"
                            f"ليس لديك صلاحية الوصول إلى {raw}. "
                            f"الوكلاء المتاحون: {agent_list}"
                        )
                        return "system", message, error
                return mentioned_agent, cleaned_message, None

        # Check if user typed an unrecognized @mention — try deployed agents first
        raw_mention = get_mentioned_raw(message)
        if raw_mention is not None and mentioned_agent is None:
            # Try to match against deployed agent names in the DB
            deployed = await self._resolve_deployed_agent_mention(raw_mention.lstrip("@"))
            if deployed is not None:
                agent_key = f"dept:{deployed}"
                cleaned = re.sub(r'(?:^|\s)@\S+', '', message, count=1).strip()
                cleaned = re.sub(r'\s{2,}', ' ', cleaned)
                return agent_key, cleaned, None

            # Truly unrecognized @mention -- return helpful error
            if employee_id:
                accessible = await get_accessible_agents(
                    self.db, self.tenant_id, employee_id,
                    employee_role, employee_dept_id,
                )
            else:
                accessible = list(AGENTS.keys())
            # Also include deployed agent names
            deployed_names = await self._get_deployed_agent_names()
            all_agents = [f"@{a}" for a in accessible] + [f"@{n}" for n in deployed_names]
            agent_list = ", ".join(all_agents)
            error = (
                f"I don't recognize {raw_mention}. "
                f"Available agents: {agent_list}\n\n"
                f"لا أعرف {raw_mention}. "
                f"الوكلاء المتاحون: {agent_list}"
            )
            return "system", message, error

        # -- 2. Sticky @mention routing --
        if last_mentioned_agent and (last_mentioned_agent in AGENTS or last_mentioned_agent.startswith("dept:")):
            return last_mentioned_agent, message, None

        # -- 3. Explicit switch phrases (existing) --
        message_lower_normalized = _normalize_alef(message_lower)
        for agent_name, phrases in self.SWITCH_PHRASES.items():
            if any(_normalize_alef(phrase) in message_lower_normalized for phrase in phrases):
                if agent_name != current_agent:
                    # Access check for switch phrase
                    if employee_id and employee_role is not None:
                        has_access = await check_agent_access(
                            self.db, self.tenant_id, employee_id,
                            employee_role, employee_dept_id, agent_name,
                        )
                        if not has_access:
                            return "deema", message, None  # Silent fallback
                    return agent_name, message, None

        # -- 4. Strong keyword override (new) --
        # If the user picked an agent in the sidebar but the message has a
        # clear intent for a DIFFERENT agent, route to the best match.
        scores = self._score_intents(message_lower)
        best_agent: str | None = None
        best_score = 0
        if scores:
            best_agent = max(scores, key=scores.get)
            best_score = scores[best_agent]

        if (
            current_agent
            and best_agent is not None
            and best_agent != current_agent
            and best_score >= self.STRONG_OVERRIDE_THRESHOLD
        ):
            # Access check for keyword-routed agent
            if employee_id and employee_role is not None:
                has_access = await check_agent_access(
                    self.db, self.tenant_id, employee_id,
                    employee_role, employee_dept_id, best_agent,
                )
                if not has_access:
                    # Access denied -- fall back to sticky current_agent
                    if current_agent in AGENTS or current_agent.startswith("dept:"):
                        return current_agent, message, None
                    return "deema", message, None
            return best_agent, message, None

        # -- 5. Sticky current agent (existing) --
        if current_agent and (current_agent in AGENTS or current_agent.startswith("dept:")):
            return current_agent, message, None

        # -- 6. Keyword scoring fallback (existing) --
        if scores and best_agent is not None:
            # Access check for keyword-routed agent
            if employee_id and employee_role is not None:
                has_access = await check_agent_access(
                    self.db, self.tenant_id, employee_id,
                    employee_role, employee_dept_id, best_agent,
                )
                if not has_access:
                    return "deema", message, None  # Silent fallback to Deema
            return best_agent, message, None

        # -- 7. Default --
        return "deema", message, None

    async def handle_message(
        self,
        message: str,
        employee_name: str,
        employee_id: str = "",
        conversation_history: list[dict] | None = None,
        current_agent: str | None = None,
        language: str = "ar",
        conversation_id: "UUID | None" = None,
        # New parameters for @mention routing
        last_mentioned_agent: str | None = None,
        employee_role: str | None = None,
        employee_dept_id: "UUID | None" = None,
    ) -> tuple[str, str, str | None]:
        """Route and handle a message.

        Returns:
            (agent_name, response, last_mentioned_agent)
            - last_mentioned_agent: updated value to store on conversation.
              Set when user uses @mention, preserved when sticky, cleared on explicit switch.
        """
        if conversation_history is None:
            conversation_history = []

        emp_uuid = UUID(employee_id) if employee_id else None

        agent_name, cleaned_message, error = await self.route(
            message,
            current_agent=current_agent,
            employee_id=emp_uuid,
            employee_role=employee_role,
            employee_dept_id=employee_dept_id,
            last_mentioned_agent=last_mentioned_agent,
        )

        # If routing produced an error (access denied / unknown agent), return it directly
        if error is not None:
            return "system", error, last_mentioned_agent

        # Track @mention stickiness
        mentioned_agent, _ = parse_mention(message)
        new_last_mentioned = last_mentioned_agent
        if mentioned_agent is not None:
            # User explicitly @mentioned -- update sticky
            new_last_mentioned = agent_name
        # If user used a switch phrase, clear the @mention sticky
        msg_lower_norm = _normalize_alef(message.lower())
        for switch_agent, phrases in self.SWITCH_PHRASES.items():
            if any(_normalize_alef(phrase) in msg_lower_norm for phrase in phrases):
                new_last_mentioned = None
                break

        # Load agent -- dynamic (dept:) or super agent
        dynamic = await self.get_dynamic_agent(agent_name)
        agent = dynamic if dynamic else self.get_agent(agent_name)

        # Handoff detection -- trust super agents and dept: agents
        if current_agent and current_agent not in AGENTS and not current_agent.startswith("dept:"):
            current_agent = None
        is_handoff = current_agent is not None and current_agent != agent_name
        is_first_message = current_agent is None and not conversation_history
        agent._handoff_from = current_agent if is_handoff else None
        agent._is_first_message = is_first_message
        agent._employee_role = employee_role or "employee"
        agent._employee_dept_id = employee_dept_id

        # Use cleaned message (without @mention) for the agent
        conversation_history.append({"role": "user", "content": cleaned_message})
        response = await agent.respond(
            conversation_history,
            employee_name,
            employee_id,
            language,
            conversation_id=conversation_id,
        )

        # Store agent reference so callers can read _last_suggestions
        self.last_agent = agent

        return agent_name, response, new_last_mentioned
