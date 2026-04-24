"""Agent access rules API -- admin CRUD for controlling which employees can use which agents."""
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.agent_access_rule import AgentAccessRule, AccessType
from app.auth.dependencies import require_role
from app.models.admin_user import AdminUser
from app.utils.agent_access import invalidate_access_cache, get_accessible_agents
from app.utils.employee_role import derive_employee_role

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent-access", tags=["agent-access"])


# -- Pydantic schemas --

class AgentAccessRuleResponse(BaseModel):
    id: str
    tenant_id: str
    agent_name: str
    access_type: str
    allowed_roles: list[str] | None
    allowed_departments: list[str] | None
    allowed_users: list[str] | None
    is_active: bool
    created_at: str
    updated_at: str


class AgentAccessRuleUpdate(BaseModel):
    access_type: str  # "all" | "role_based" | "department" | "specific_users"
    allowed_roles: list[str] | None = None
    allowed_departments: list[str] | None = None
    allowed_users: list[str] | None = None
    is_active: bool = True


def _rule_to_response(rule: AgentAccessRule) -> AgentAccessRuleResponse:
    return AgentAccessRuleResponse(
        id=str(rule.id),
        tenant_id=str(rule.tenant_id),
        agent_name=rule.agent_name,
        access_type=rule.access_type.value if isinstance(rule.access_type, AccessType) else rule.access_type,
        allowed_roles=rule.allowed_roles,
        allowed_departments=rule.allowed_departments,
        allowed_users=rule.allowed_users,
        is_active=rule.is_active,
        created_at=rule.created_at.isoformat() if rule.created_at else "",
        updated_at=rule.updated_at.isoformat() if rule.updated_at else "",
    )


@router.get("", response_model=list[AgentAccessRuleResponse])
async def list_access_rules(
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_role("hr_specialist")),
):
    """List all agent access rules for the admin's tenant."""
    result = await db.execute(
        select(AgentAccessRule).where(
            AgentAccessRule.tenant_id == admin.tenant_id,
        ).order_by(AgentAccessRule.agent_name)
    )
    rules = result.scalars().all()
    return [_rule_to_response(r) for r in rules]


@router.get("/{agent_name}", response_model=AgentAccessRuleResponse)
async def get_access_rule(
    agent_name: str,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_role("hr_specialist")),
):
    """Get access rule for a specific agent."""
    result = await db.execute(
        select(AgentAccessRule).where(
            AgentAccessRule.tenant_id == admin.tenant_id,
            AgentAccessRule.agent_name == agent_name,
        )
    )
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Access rule not found")
    return _rule_to_response(rule)


@router.put("/{agent_name}", response_model=AgentAccessRuleResponse)
async def upsert_access_rule(
    agent_name: str,
    body: AgentAccessRuleUpdate,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_role("hr_specialist")),
):
    """Create or update an agent access rule."""
    # Validate access_type
    try:
        access_type = AccessType(body.access_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid access_type: {body.access_type}. Must be one of: all, role_based, department, specific_users"
        )

    result = await db.execute(
        select(AgentAccessRule).where(
            AgentAccessRule.tenant_id == admin.tenant_id,
            AgentAccessRule.agent_name == agent_name,
        )
    )
    rule = result.scalar_one_or_none()

    if rule:
        # Update existing
        rule.access_type = access_type
        rule.allowed_roles = body.allowed_roles
        rule.allowed_departments = body.allowed_departments
        rule.allowed_users = body.allowed_users
        rule.is_active = body.is_active
    else:
        # Create new
        rule = AgentAccessRule(
            tenant_id=admin.tenant_id,
            agent_name=agent_name,
            access_type=access_type,
            allowed_roles=body.allowed_roles,
            allowed_departments=body.allowed_departments,
            allowed_users=body.allowed_users,
            is_active=body.is_active,
        )
        db.add(rule)

    await db.commit()
    await db.refresh(rule)

    # Invalidate cache
    invalidate_access_cache(admin.tenant_id, agent_name)

    return _rule_to_response(rule)


@router.delete("/{agent_name}")
async def delete_access_rule(
    agent_name: str,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_role("hr_specialist")),
):
    """Delete an agent access rule (reverts to permissive default)."""
    result = await db.execute(
        select(AgentAccessRule).where(
            AgentAccessRule.tenant_id == admin.tenant_id,
            AgentAccessRule.agent_name == agent_name,
        )
    )
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Access rule not found")

    await db.delete(rule)
    await db.commit()

    # Invalidate cache
    invalidate_access_cache(admin.tenant_id, agent_name)

    return {"status": "deleted"}


@router.get("/employee/{employee_id}")
async def get_employee_accessible_agents(
    employee_id: str,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_role("hr_specialist")),
):
    """List agent names a specific employee can access."""
    try:
        emp_id = UUID(employee_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid employee_id")

    from app.models.employee import Employee
    emp_result = await db.execute(
        select(Employee).where(
            Employee.id == emp_id,
            Employee.tenant_id == admin.tenant_id,
        )
    )
    emp = emp_result.scalar_one_or_none()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    role = await derive_employee_role(db, admin.tenant_id, emp_id)
    accessible = await get_accessible_agents(
        db, admin.tenant_id, emp_id, role, emp.department_id,
    )
    return accessible
