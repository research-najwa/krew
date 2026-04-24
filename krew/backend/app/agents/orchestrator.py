"""Agent orchestrator — routes incoming messages to the correct agent.

Supports both super agents (hardcoded) and department agents (loaded from DB).
Department agents use the naming convention 'dept:{uuid}'.
"""
import logging
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

logger = logging.getLogger(__name__)
settings = get_settings()

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
        "payslip", "help", "question", "إجازة", "رصيد", "سياسة", "راتب", "مساعدة",
        "طلباتي", "تذاكري", "my requests", "my tickets", "track",
        "profile", "my info", "contract", "probation", "بياناتي", "ملفي", "عقد",
        "كشف راتب", "تجربة",
    ],
    "waleed": [
        "onboarding", "new hire", "first day", "orientation", "buddy",
        "تعيين", "جديد", "تهيئة", "checklist", "check-in", "checkin",
        "my team", "team members", "direct reports", "approve leave", "reject leave",
        "pending approval", "pending approvals", "pending leave", "leave approval",
        "فريقي", "موافقة", "رفض إجازة", "الموافقات", "طلبات الإجازة", "الإجازات المعلقة",
        "headcount", "عدد الموظفين",
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
        "automate", "ai ready", "agent factory", "virtual employee",
        "workforce mix", "workforce plan", "deploy agent", "build agent",
        "design agent", "ai agent", "department agent", "agent performance",
        "governance report", "drift detection", "activate agent", "deactivate agent",
        "أتمتة", "ذكاء اصطناعي", "وكيل", "نسبة القوى العاملة",
    ],
    "ahmad": [
        "analytics", "compliance", "regulation", "labor law", "audit",
        "budget", "cost", "forecast", "turnover",
        "saudization", "nitaqat", "workforce metrics", "executive",
        "dashboard", "salary distribution", "hr metrics", "chro",
        "تحليلات", "امتثال", "نظام", "قانون", "ميزانية", "تكلفة", "تحليل",
        "دوران وظيفي", "سعودة", "نطاقات", "مقاييس", "لوحة المعلومات",
        "توزيع الرواتب",
        # A2 cross-domain analytics keywords
        "recruitment funnel", "time to fill", "hiring analytics",
        "leave trends", "leave analytics", "leave usage",
        "attendance rate", "overtime analytics", "late arrivals",
        "onboarding progress", "onboarding completion", "bottleneck steps",
        "payroll cost", "payroll trend", "gosi breakdown",
        "تحليل التوظيف", "تحليل الإجازات", "تحليل الحضور",
        "تكلفة الرواتب", "تحليل التأهيل",
    ],
}


# Startup check: no keyword appears in multiple agents' lists
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

    # Explicit agent switch phrases — user must name the agent to switch
    SWITCH_PHRASES: dict[str, list[str]] = {
        "deema": ["ديمة", "deema", "حول لديمة", "كلم ديمة", "switch to deema", "talk to deema"],
        "waleed": ["وليد", "waleed", "حول لوليد", "كلم وليد", "switch to waleed", "talk to waleed"],
        "mohammad": ["محمد", "mohammad", "حول لمحمد", "كلم محمد", "switch to mohammad", "talk to mohammad"],
        "yara": ["يارا", "yara", "حول ليارا", "كلم يارا", "switch to yara", "talk to yara"],
        "ahmad": [
            "أحمد", "ahmad", "حول لأحمد", "كلم أحمد", "switch to ahmad", "talk to ahmad",
            "نورة", "norah", "حول لنورة", "كلم نورة", "switch to norah", "talk to norah",
            "سارة", "sarah", "حول لسارة", "كلم سارة", "switch to sarah", "talk to sarah",
        ],
    }

    async def route(self, message: str, current_agent: str | None = None) -> str:
        """Determine which agent should handle this message.

        Sticky routing: once in a conversation with an agent, stay with them.
        Only switch if the user explicitly names another agent.
        """
        message_lower = message.lower()

        # Check for explicit agent switch request (works whether or not there's a current agent)
        for agent_name, phrases in self.SWITCH_PHRASES.items():
            if any(phrase in message_lower for phrase in phrases):
                # Only switch if the named agent is different from current
                if agent_name != current_agent:
                    return agent_name

        # If already in a conversation, stay with that agent (sticky)
        # Supports both super agents and dept:{uuid} dynamic agents
        if current_agent and (current_agent in AGENTS or current_agent.startswith("dept:")):
            return current_agent

        # No active agent — classify intent
        message_lower = message.lower()
        scores: dict[str, int] = {}

        for agent_name, keywords in INTENT_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in message_lower)
            if score > 0:
                scores[agent_name] = score

        if scores:
            return max(scores, key=scores.get)

        # Default to Deema (general employee services)
        return "deema"

    async def handle_message(
        self,
        message: str,
        employee_name: str,
        employee_id: str = "",
        conversation_history: list[dict] | None = None,
        current_agent: str | None = None,
        language: str = "ar",
        conversation_id: "UUID | None" = None,
    ) -> tuple[str, str]:
        """Route and handle a message. Returns (agent_name, response)."""
        if conversation_history is None:
            conversation_history = []

        agent_name = await self.route(message, current_agent)

        # Load agent — dynamic (dept:) or super agent
        dynamic = await self.get_dynamic_agent(agent_name)
        agent = dynamic if dynamic else self.get_agent(agent_name)

        # Handoff detection — trust super agents and dept: agents
        if current_agent and current_agent not in AGENTS and not current_agent.startswith("dept:"):
            current_agent = None
        is_handoff = current_agent is not None and current_agent != agent_name
        is_first_message = current_agent is None and not conversation_history
        agent._handoff_from = current_agent if is_handoff else None
        agent._is_first_message = is_first_message

        conversation_history.append({"role": "user", "content": message})
        response = await agent.respond(
            conversation_history,
            employee_name,
            employee_id,
            language,
            conversation_id=conversation_id,
        )

        # Store agent reference so callers can read _last_suggestions
        self.last_agent = agent

        return agent_name, response
