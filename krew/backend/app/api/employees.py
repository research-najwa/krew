"""Employee management API."""
from uuid import UUID
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.database import get_db
from app.models.employee import Employee, EmployeeStatus
from app.models.admin_user import AdminUser, AdminRole
from app.auth.dependencies import require_role, require_tenant

router = APIRouter(prefix="/employees", tags=["employees"])


class EmployeeCreate(BaseModel):
    first_name: str
    last_name: str
    first_name_ar: str | None = None
    last_name_ar: str | None = None
    email: str
    phone: str | None = None
    national_id: str | None = None
    job_title: str
    hire_date: date
    is_saudi: bool = True
    salary_sar: int | None = None
    whatsapp_number: str | None = None
    preferred_language: str = "ar"
    preferred_channel: str = "whatsapp"
    department_id: UUID | None = None


class EmployeeResponse(BaseModel):
    id: UUID
    full_name: str
    email: str
    job_title: str
    status: str
    hire_date: date
    preferred_channel: str

    model_config = {"from_attributes": True}


@router.post("/", response_model=EmployeeResponse)
async def create_employee(
    data: EmployeeCreate,
    current_user: AdminUser = Depends(require_role(AdminRole.hr_manager)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Register a new employee in the system."""
    employee = Employee(tenant_id=tenant_id, **data.model_dump())
    db.add(employee)
    await db.commit()
    await db.refresh(employee)

    return EmployeeResponse(
        id=employee.id,
        full_name=employee.full_name,
        email=employee.email,
        job_title=employee.job_title,
        status=employee.status.value,
        hire_date=employee.hire_date,
        preferred_channel=employee.preferred_channel,
    )


@router.get("/{employee_id}", response_model=EmployeeResponse)
async def get_employee(
    employee_id: UUID,
    current_user: AdminUser = Depends(require_role(AdminRole.hr_specialist)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Get employee details."""
    result = await db.execute(
        select(Employee).where(
            Employee.id == employee_id,
            Employee.tenant_id == tenant_id,
        )
    )
    employee = result.scalar_one_or_none()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    return EmployeeResponse(
        id=employee.id,
        full_name=employee.full_name,
        email=employee.email,
        job_title=employee.job_title,
        status=employee.status.value,
        hire_date=employee.hire_date,
        preferred_channel=employee.preferred_channel,
    )


@router.get("/")
async def list_employees(
    current_user: AdminUser = Depends(require_role(AdminRole.hr_specialist)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """List all employees for the authenticated user's tenant."""
    result = await db.execute(
        select(Employee)
        .where(Employee.tenant_id == tenant_id, Employee.status != EmployeeStatus.terminated)
        .order_by(Employee.first_name)
    )
    employees = result.scalars().all()

    return [
        EmployeeResponse(
            id=e.id,
            full_name=e.full_name,
            email=e.email,
            job_title=e.job_title,
            status=e.status.value,
            hire_date=e.hire_date,
            preferred_channel=e.preferred_channel,
        )
        for e in employees
    ]
