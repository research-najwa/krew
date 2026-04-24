"""Seed default agent access rules for new tenants."""
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_access_rule import AgentAccessRule, AccessType


DEFAULT_ACCESS_RULES = [
    {
        "agent_name": "deema",
        "access_type": AccessType.all,
        "allowed_roles": None,
    },
    {
        "agent_name": "waleed",
        "access_type": AccessType.role_based,
        "allowed_roles": ["manager", "department_head", "hr_specialist", "hr_manager", "hr_admin", "c_suite"],
    },
    {
        "agent_name": "mohammad",
        "access_type": AccessType.role_based,
        "allowed_roles": ["hr_admin", "hr_manager", "hr_specialist", "hiring_manager", "department_head", "c_suite"],
    },
    {
        "agent_name": "ahmad",
        "access_type": AccessType.role_based,
        "allowed_roles": ["hr_admin", "hr_manager", "department_head", "c_suite"],
    },
    {
        "agent_name": "yara",
        "access_type": AccessType.role_based,
        "allowed_roles": ["hr_admin", "hr_manager", "it_admin", "c_suite"],
    },
]


async def seed_agent_access_rules(db: AsyncSession, tenant_id: UUID) -> None:
    """Create default agent access rules for a new tenant.

    Idempotent -- skips rules that already exist (checked by unique index
    on tenant_id + agent_name).
    """
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    for rule_data in DEFAULT_ACCESS_RULES:
        stmt = pg_insert(AgentAccessRule).values(
            tenant_id=tenant_id,
            agent_name=rule_data["agent_name"],
            access_type=rule_data["access_type"],
            allowed_roles=rule_data["allowed_roles"],
        ).on_conflict_do_nothing(
            index_elements=["tenant_id", "agent_name"],
        )
        await db.execute(stmt)
    await db.flush()
