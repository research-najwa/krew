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
from app.auth.chat_dependencies import get_chat_employee, ChatEmployee

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/teams", tags=["teams"])


@router.get("/my")
async def my_teams(
    db: AsyncSession = Depends(get_db),
    chat_emp: ChatEmployee = Depends(get_chat_employee),
):
    """List only the current user's own department, with member counts."""
    tid = chat_emp.tenant_id

    emp_result = await db.execute(
        select(Employee.department_id).where(Employee.id == chat_emp.employee_id)
    )
    my_dept_id = emp_result.scalar_one_or_none()
    if not my_dept_id:
        return []

    dept_query = (
        select(
            Department.id,
            Department.name,
            Department.name_ar,
            func.count(Employee.id).label("human_count"),
        )
        .outerjoin(
            Employee,
            (Employee.department_id == Department.id)
            & (Employee.status == EmployeeStatus.active),
        )
        .where(Department.id == my_dept_id)
        .group_by(Department.id)
    )
    dept_result = await db.execute(dept_query)
    departments = dept_result.all()

    agent_query = (
        select(func.count(DeployedAgent.id))
        .where(
            DeployedAgent.department_id == my_dept_id,
            DeployedAgent.tenant_id == tid,
            DeployedAgent.status == AgentStatus.active,
        )
    )
    ai_count = (await db.execute(agent_query)).scalar() or 0

    teams = []
    for dept in departments:
        others = max(dept.human_count - 1, 0)
        teams.append({
            "department_id": str(dept.id),
            "name": dept.name,
            "name_ar": dept.name_ar,
            "human_count": others,
            "ai_agent_count": ai_count,
            "total_members": others + ai_count,
        })

    return teams


@router.get("/my/{department_id}/members")
async def my_team_members(
    department_id: str,
    db: AsyncSession = Depends(get_db),
    chat_emp: ChatEmployee = Depends(get_chat_employee),
):
    """List all members (humans + AI agents) in a department."""
    tid = chat_emp.tenant_id
    try:
        dept_id = UUID(department_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid department_id")

    dept_result = await db.execute(
        select(Department).where(Department.id == dept_id, Department.tenant_id == tid)
    )
    dept = dept_result.scalar_one_or_none()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")

    emp_result = await db.execute(
        select(
            Employee.id, Employee.first_name, Employee.last_name,
            Employee.first_name_ar, Employee.last_name_ar,
            Employee.job_title, Employee.job_title_ar,
        )
        .where(
            Employee.department_id == dept_id,
            Employee.tenant_id == tid,
            Employee.status == EmployeeStatus.active,
            Employee.id != chat_emp.employee_id,
        )
        .order_by(Employee.first_name)
    )

    members = []
    for e in emp_result.all():
        members.append({
            "id": str(e.id),
            "type": "human",
            "name": f"{e.first_name} {e.last_name}",
            "name_ar": f"{e.first_name_ar or ''} {e.last_name_ar or ''}".strip() or None,
            "job_title": e.job_title,
            "job_title_ar": e.job_title_ar,
        })

    agent_result = await db.execute(
        select(DeployedAgent)
        .where(
            DeployedAgent.department_id == dept_id,
            DeployedAgent.tenant_id == tid,
            DeployedAgent.status == AgentStatus.active,
        )
        .order_by(DeployedAgent.name)
    )
    for a in agent_result.scalars().all():
        members.append({
            "id": str(a.id),
            "type": "ai_agent",
            "name": a.name,
            "name_ar": a.name_ar,
            "job_title": a.role_title,
            "job_title_ar": a.role_title_ar,
        })

    return members
