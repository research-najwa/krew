"""Shared API helper functions — extracted to avoid duplication across routers."""
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee
from app.models.admin_user import AdminUser


async def resolve_employee_id(
    current_user: AdminUser, tenant_id: UUID, db: AsyncSession,
) -> UUID:
    """Resolve the employee ID for the current admin user.

    Looks up the Employee record matching the admin user's email within
    the given tenant. Raises 400 if no linked employee found.
    """
    result = await db.execute(
        select(Employee).where(
            Employee.tenant_id == tenant_id,
            Employee.email == current_user.email,
        )
    )
    emp = result.scalar_one_or_none()
    if not emp:
        raise HTTPException(
            status_code=400,
            detail="Your admin account is not linked to an employee record.",
        )
    return emp.id
