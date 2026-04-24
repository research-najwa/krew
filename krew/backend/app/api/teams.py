"""Teams API — department team views with human + AI agent members.

Provides endpoints for the sidebar Team UI where users see their departments,
team members (humans and AI agents), and can start conversations with
department-level AI agents.
"""
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.employee import Employee, Department, EmployeeStatus
from app.models.deployed_agent import DeployedAgent, AgentStatus
from app.models.conversation import Conversation

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/teams", tags=["teams"])


@router.get("")
async def list_teams(
    tenant_id: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """List all departments with human headcount and AI agent count."""
    # For now, get tenant_id from query param (in production: from auth token)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id required")

    try:
        tid = UUID(tenant_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid tenant_id format")

    # Get departments with employee counts
    dept_query = (
        select(
            Department.id,
            Department.name,
            Department.name_ar,
            Department.manager_id,
            func.count(Employee.id).label("human_count"),
        )
        .outerjoin(
            Employee,
            (Employee.department_id == Department.id)
            & (Employee.status == EmployeeStatus.active),
        )
        .where(Department.tenant_id == tid)
        .group_by(Department.id)
        .order_by(Department.name)
    )
    dept_result = await db.execute(dept_query)
    departments = dept_result.all()

    # Get AI agent counts per department
    agent_query = (
        select(
            DeployedAgent.department_id,
            func.count(DeployedAgent.id).label("agent_count"),
        )
        .where(
            DeployedAgent.tenant_id == tid,
            DeployedAgent.status == AgentStatus.active,
        )
        .group_by(DeployedAgent.department_id)
    )
    agent_result = await db.execute(agent_query)
    agent_counts = {str(r.department_id): r.agent_count for r in agent_result.all()}

    teams = []
    for dept in departments:
        ai_count = agent_counts.get(str(dept.id), 0)
        teams.append({
            "department_id": str(dept.id),
            "name": dept.name,
            "name_ar": dept.name_ar,
            "human_count": dept.human_count,
            "ai_agent_count": ai_count,
            "total_members": dept.human_count + ai_count,
            "manager_id": str(dept.manager_id) if dept.manager_id else None,
        })

    return {"teams": teams, "total": len(teams)}


@router.get("/{department_id}/members")
async def get_team_members(
    department_id: str,
    tenant_id: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """List all members (humans + AI agents) in a department."""
    if not tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id required")

    try:
        tid = UUID(tenant_id)
        dept_id = UUID(department_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")

    # Verify department exists and belongs to tenant
    dept_result = await db.execute(
        select(Department).where(
            Department.id == dept_id,
            Department.tenant_id == tid,
        )
    )
    dept = dept_result.scalar_one_or_none()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")

    # Get human employees
    emp_result = await db.execute(
        select(
            Employee.id,
            Employee.first_name,
            Employee.last_name,
            Employee.first_name_ar,
            Employee.last_name_ar,
            Employee.job_title,
            Employee.job_title_ar,
            Employee.email,
            Employee.is_saudi,
            Employee.status,
        )
        .where(
            Employee.department_id == dept_id,
            Employee.tenant_id == tid,
            Employee.status == EmployeeStatus.active,
        )
        .order_by(Employee.first_name)
    )
    employees = emp_result.all()

    humans = [
        {
            "id": str(e.id),
            "type": "human",
            "name": f"{e.first_name} {e.last_name}",
            "name_ar": f"{e.first_name_ar or ''} {e.last_name_ar or ''}".strip() or None,
            "job_title": e.job_title,
            "job_title_ar": e.job_title_ar,
            "email": e.email,
            "is_saudi": e.is_saudi,
            "status": "online",  # placeholder
        }
        for e in employees
    ]

    # Get AI agents
    agent_result = await db.execute(
        select(DeployedAgent)
        .where(
            DeployedAgent.department_id == dept_id,
            DeployedAgent.tenant_id == tid,
            DeployedAgent.status == AgentStatus.active,
        )
        .order_by(DeployedAgent.name)
    )
    agents = agent_result.scalars().all()

    ai_agents = [
        {
            "id": str(a.id),
            "type": "ai_agent",
            "name": a.name,
            "name_ar": a.name_ar,
            "job_title": a.role_title,
            "job_title_ar": a.role_title_ar,
            "status": "online",
            "agent_name": f"dept:{a.id}",  # for chat routing
            "tools_count": len(a.tools_config or []),
            "performance": a.performance_metrics or {},
        }
        for a in agents
    ]

    return {
        "department": {
            "id": str(dept.id),
            "name": dept.name,
            "name_ar": dept.name_ar,
        },
        "members": humans + ai_agents,
        "human_count": len(humans),
        "ai_agent_count": len(ai_agents),
    }


@router.get("/deployed-agents")
async def list_deployed_agents(
    tenant_id: str | None = None,
    department_id: str | None = None,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """List all deployed AI agents across the organization."""
    if not tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id required")

    try:
        tid = UUID(tenant_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid tenant_id format")

    query = select(DeployedAgent).where(DeployedAgent.tenant_id == tid)

    if department_id:
        try:
            query = query.where(DeployedAgent.department_id == UUID(department_id))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid department_id format")
    if status:
        try:
            query = query.where(DeployedAgent.status == AgentStatus(status))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid status value")

    query = query.order_by(DeployedAgent.created_at.desc())
    result = await db.execute(query)
    agents = result.scalars().all()

    return {
        "agents": [
            {
                "id": str(a.id),
                "name": a.name,
                "name_ar": a.name_ar,
                "role_title": a.role_title,
                "role_title_ar": a.role_title_ar,
                "department_id": str(a.department_id),
                "status": a.status.value,
                "agent_name": f"dept:{a.id}",
                "tools_count": len(a.tools_config or []),
                "performance": a.performance_metrics or {},
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in agents
        ],
        "total": len(agents),
    }
