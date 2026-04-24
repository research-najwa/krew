"""Agent access control -- checks if an employee can interact with an agent."""
import logging
import time
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_access_rule import AgentAccessRule, AccessType

logger = logging.getLogger(__name__)

# In-process cache: (tenant_id, agent_name) -> (timestamp, AgentAccessRule | None)
# TTL managed by simple timestamp check. Invalidated on rule update via API.
_access_cache: dict[tuple[UUID, str], tuple[float, AgentAccessRule | None]] = {}
_CACHE_TTL_SECONDS = 300  # 5 minutes


async def check_agent_access(
    db: AsyncSession,
    tenant_id: UUID,
    employee_id: UUID,
    employee_role: str,
    employee_dept_id: UUID | None,
    agent_name: str,
) -> bool:
    """Check if an employee can access a specific agent.

    Logic:
    1. Query agent_access_rules for (tenant_id, agent_name, is_active=True)
    2. If no rule found -> ALLOW (permissive default for new/dynamic agents)
    3. access_type = 'all' -> ALLOW
    4. access_type = 'role_based' -> employee_role in allowed_roles
    5. access_type = 'department' -> str(employee_dept_id) in allowed_departments
    6. access_type = 'specific_users' -> str(employee_id) in allowed_users

    For deployed agents (dept:{uuid}), first checks agent_access_rules, then falls
    back to DeployedAgent.scope_boundaries visibility settings if no explicit rule.
    """
    cache_key = (tenant_id, agent_name)
    now = time.time()

    # Check cache
    if cache_key in _access_cache:
        cached_time, cached_rule = _access_cache[cache_key]
        if now - cached_time < _CACHE_TTL_SECONDS:
            result = _evaluate_rule(cached_rule, employee_id, employee_role, employee_dept_id)
            # If rule was None and it's a dept: agent, fall through to deployed agent check
            if cached_rule is not None or not agent_name.startswith("dept:"):
                return result

    # Query DB
    result = await db.execute(
        select(AgentAccessRule).where(
            AgentAccessRule.tenant_id == tenant_id,
            AgentAccessRule.agent_name == agent_name,
            AgentAccessRule.is_active == True,  # noqa: E712
        )
    )
    rule = result.scalar_one_or_none()

    # Cache result (including None)
    _access_cache[cache_key] = (now, rule)

    # For deployed agents with no explicit rule, fall back to scope_boundaries
    if agent_name.startswith("dept:") and rule is None:
        return await _check_deployed_agent_access(
            db, tenant_id, employee_id, employee_dept_id, agent_name
        )

    return _evaluate_rule(rule, employee_id, employee_role, employee_dept_id)


async def _check_deployed_agent_access(
    db: AsyncSession,
    tenant_id: UUID,
    employee_id: UUID,
    employee_dept_id: UUID | None,
    agent_name: str,
) -> bool:
    """Fall back to deployed agent's own visibility settings."""
    from app.models.deployed_agent import DeployedAgent

    try:
        agent_uuid = UUID(agent_name[5:])
    except ValueError:
        return False

    da_result = await db.execute(
        select(DeployedAgent).where(
            DeployedAgent.id == agent_uuid,
            DeployedAgent.tenant_id == tenant_id,
        )
    )
    da = da_result.scalar_one_or_none()
    if not da:
        return False

    scope = da.scope_boundaries or {}
    visibility = scope.get("visibility", "all")
    if visibility == "all":
        return True
    if visibility == "department_only":
        return employee_dept_id is not None and employee_dept_id == da.department_id
    if visibility == "custom":
        return str(employee_id) in scope.get("allowed_users", [])
    return True


def _evaluate_rule(
    rule: AgentAccessRule | None,
    employee_id: UUID,
    employee_role: str,
    employee_dept_id: UUID | None,
) -> bool:
    """Evaluate a single access rule. Returns True if access is allowed."""
    if rule is None:
        return True  # Permissive default: no rule = allow

    if rule.access_type == AccessType.all:
        return True

    if rule.access_type == AccessType.role_based:
        return employee_role in (rule.allowed_roles or [])

    if rule.access_type == AccessType.department:
        if employee_dept_id is None:
            return False
        return str(employee_dept_id) in (rule.allowed_departments or [])

    if rule.access_type == AccessType.specific_users:
        return str(employee_id) in (rule.allowed_users or [])

    return False  # Unknown access_type -- deny


def invalidate_access_cache(tenant_id: UUID, agent_name: str | None = None) -> None:
    """Invalidate cached access rules. Called when admin updates rules via API.

    If agent_name is None, invalidates ALL rules for the tenant.
    """
    if agent_name:
        _access_cache.pop((tenant_id, agent_name), None)
    else:
        keys_to_remove = [k for k in _access_cache if k[0] == tenant_id]
        for k in keys_to_remove:
            del _access_cache[k]


async def get_accessible_agents(
    db: AsyncSession,
    tenant_id: UUID,
    employee_id: UUID | None,
    employee_role: str | None,
    employee_dept_id: UUID | None,
) -> list[str]:
    """Return list of agent names this employee can access.

    Used for: (a) @mention autocomplete filtering, (b) error messages listing available agents.
    """
    from app.agents.orchestrator import AGENTS

    if employee_id is None:
        return list(AGENTS.keys())

    role = employee_role or "employee"
    accessible = []
    for agent_name in AGENTS:
        if await check_agent_access(db, tenant_id, employee_id, role, employee_dept_id, agent_name):
            accessible.append(agent_name)

    # Also check deployed agents the employee can access
    from app.models.deployed_agent import DeployedAgent, AgentStatus
    dept_result = await db.execute(
        select(DeployedAgent).where(
            DeployedAgent.tenant_id == tenant_id,
            DeployedAgent.status == AgentStatus.active,
        )
    )
    for da in dept_result.scalars().all():
        da_name = f"dept:{da.id}"
        if await check_agent_access(db, tenant_id, employee_id, role, employee_dept_id, da_name):
            accessible.append(da_name)

    return accessible
