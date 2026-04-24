"""Admin panel API — tenant settings, employee/department CRUD, leave management."""
from datetime import date, datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy import select, func, case, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.employee import Employee, EmployeeStatus, Department
from app.models.leave import LeaveRequest, LeaveBalance, LeaveStatus, LeaveType
from app.models.tenant import Tenant, PlanTier
from app.models.admin_user import AdminUser, AdminRole
from app.auth.dependencies import require_role, require_tenant
from app.services.admin import AdminService
from app.security.audit import emit_audit_event

router = APIRouter(prefix="/admin", tags=["admin"])


# ── Pydantic schemas ──────────────────────────────────────────────


class TenantOut(BaseModel):
    id: str
    name: str
    name_ar: str | None
    domain: str | None
    plan: str
    employee_count: int
    cr_number: str | None
    gosi_number: str | None
    created_at: str


class TenantUpdate(BaseModel):
    name: str | None = None
    name_ar: str | None = None
    plan: str | None = None
    cr_number: str | None = None
    gosi_number: str | None = None


class EmployeeCreateIn(BaseModel):
    employee_number: str
    first_name: str
    last_name: str
    first_name_ar: str | None = None
    last_name_ar: str | None = None
    email: str
    phone: str | None = None
    national_id: str
    job_title: str = "Employee"
    job_title_ar: str | None = None
    hire_date: date
    is_saudi: bool = True
    salary_sar: int | None = None
    gender: str | None = None
    contract_type: str = "full_time"
    work_mode: str = "onsite"
    department_id: UUID | None = None
    manager_id: UUID | None = None
    whatsapp_number: str | None = None
    preferred_language: str = "ar"
    preferred_channel: str = "whatsapp"


class EmployeeUpdateIn(BaseModel):
    employee_number: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    first_name_ar: str | None = None
    last_name_ar: str | None = None
    email: str | None = None
    phone: str | None = None
    national_id: str | None = None
    job_title: str | None = None
    job_title_ar: str | None = None
    hire_date: date | None = None
    is_saudi: bool | None = None
    salary_sar: int | None = None
    gender: str | None = None
    contract_type: str | None = None
    work_mode: str | None = None
    status: str | None = None
    department_id: UUID | None = None
    manager_id: UUID | None = None
    whatsapp_number: str | None = None
    preferred_language: str | None = None
    preferred_channel: str | None = None


class EmployeeOut(BaseModel):
    id: str
    employee_number: str | None
    first_name: str
    last_name: str
    first_name_ar: str | None
    last_name_ar: str | None
    full_name: str
    email: str
    phone: str | None
    national_id: str | None
    job_title: str
    job_title_ar: str | None
    hire_date: str
    end_date: str | None
    status: str
    is_saudi: bool
    salary_sar: int | None
    gender: str | None
    contract_type: str
    work_mode: str
    department_id: str | None
    manager_id: str | None
    whatsapp_number: str | None
    preferred_language: str
    preferred_channel: str
    created_at: str
    updated_at: str


class EmployeeListResponse(BaseModel):
    items: list[EmployeeOut]
    total: int
    page: int
    per_page: int
    pages: int


class DepartmentCreateIn(BaseModel):
    name: str
    name_ar: str | None = None
    manager_id: UUID | None = None
    headcount_budget: int | None = None
    cost_budget_sar: int | None = None


class DepartmentUpdateIn(BaseModel):
    name: str | None = None
    name_ar: str | None = None
    manager_id: UUID | None = None
    headcount_budget: int | None = None
    cost_budget_sar: int | None = None


class DepartmentOut(BaseModel):
    id: str
    name: str
    name_ar: str | None
    manager_id: str | None
    headcount_budget: int | None
    cost_budget_sar: int | None
    active_employee_count: int


class ImportResult(BaseModel):
    created: int
    errors: list[dict]


class LeaveRequestOut(BaseModel):
    id: str
    employee_name: str
    employee_number: str | None
    department: str | None
    leave_type: str
    start_date: str
    end_date: str
    business_days: int
    status: str
    reason: str | None
    created_at: str


class LeaveSummary(BaseModel):
    pending: int
    approved_this_month: int
    rejected_this_month: int
    total_this_month: int


# ── Helpers ────────────────────────────────────────────────────────


def _employee_to_out(emp: Employee) -> EmployeeOut:
    return EmployeeOut(
        id=str(emp.id),
        employee_number=emp.employee_number,
        first_name=emp.first_name,
        last_name=emp.last_name,
        first_name_ar=emp.first_name_ar,
        last_name_ar=emp.last_name_ar,
        full_name=emp.full_name,
        email=emp.email,
        phone=emp.phone,
        national_id=emp.national_id,
        job_title=emp.job_title,
        job_title_ar=emp.job_title_ar,
        hire_date=emp.hire_date.isoformat(),
        end_date=emp.end_date.isoformat() if emp.end_date else None,
        status=emp.status.value,
        is_saudi=emp.is_saudi,
        salary_sar=emp.salary_sar,
        gender=emp.gender.value if emp.gender else None,
        contract_type=emp.contract_type,
        work_mode=emp.work_mode.value,
        department_id=str(emp.department_id) if emp.department_id else None,
        manager_id=str(emp.manager_id) if emp.manager_id else None,
        whatsapp_number=emp.whatsapp_number,
        preferred_language=emp.preferred_language,
        preferred_channel=emp.preferred_channel,
        created_at=emp.created_at.isoformat(),
        updated_at=emp.updated_at.isoformat(),
    )


# ── Tenant Settings ───────────────────────────────────────────────


@router.get("/tenant", response_model=TenantOut)
async def get_tenant(
    current_user: AdminUser = Depends(require_role(AdminRole.hr_specialist)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Get current tenant settings."""
    svc = AdminService(db, tenant_id)
    tenant = await svc.get_tenant()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return TenantOut(
        id=str(tenant.id),
        name=tenant.name,
        name_ar=tenant.name_ar,
        domain=tenant.domain,
        plan=tenant.plan.value,
        employee_count=tenant.employee_count,
        cr_number=tenant.cr_number,
        gosi_number=tenant.gosi_number,
        created_at=tenant.created_at.isoformat(),
    )


@router.put("/tenant", response_model=TenantOut)
async def update_tenant(
    data: TenantUpdate,
    request: Request,
    current_user: AdminUser = Depends(require_role(AdminRole.tenant_admin)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Update tenant settings. Requires admin role minimum."""
    update_data = data.model_dump(exclude_none=True)

    # Validate plan if provided
    if "plan" in update_data:
        try:
            update_data["plan"] = PlanTier(update_data["plan"])
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid plan. Must be one of: {[p.value for p in PlanTier]}",
            )

    svc = AdminService(db, tenant_id)
    try:
        tenant = await svc.update_tenant(update_data)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    await emit_audit_event(
        db, action="tenant.updated", actor_id=str(current_user.id),
        actor_email=current_user.email, tenant_id=str(tenant_id),
        resource_type="tenant", resource_id=str(tenant_id),
        detail={"updated_fields": list(update_data.keys())},
        request=request,
    )

    return TenantOut(
        id=str(tenant.id),
        name=tenant.name,
        name_ar=tenant.name_ar,
        domain=tenant.domain,
        plan=tenant.plan.value,
        employee_count=tenant.employee_count,
        cr_number=tenant.cr_number,
        gosi_number=tenant.gosi_number,
        created_at=tenant.created_at.isoformat(),
    )


# ── Employee CRUD ─────────────────────────────────────────────────


@router.get("/employees", response_model=EmployeeListResponse)
async def list_employees(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
    department_id: UUID | None = Query(None),
    is_saudi: bool | None = Query(None),
    search: str | None = Query(None),
    current_user: AdminUser = Depends(require_role(AdminRole.hr_specialist)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """List employees with pagination and filters."""
    # Validate status if provided
    if status:
        try:
            EmployeeStatus(status)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status. Must be one of: {[s.value for s in EmployeeStatus]}",
            )

    svc = AdminService(db, tenant_id)
    result = await svc.list_employees(
        page=page,
        per_page=per_page,
        status=status,
        department_id=department_id,
        is_saudi=is_saudi,
        search=search,
    )

    return EmployeeListResponse(
        items=[_employee_to_out(e) for e in result["items"]],
        total=result["total"],
        page=result["page"],
        per_page=result["per_page"],
        pages=result["pages"],
    )


@router.post("/employees", response_model=EmployeeOut, status_code=201)
async def create_employee(
    data: EmployeeCreateIn,
    request: Request,
    current_user: AdminUser = Depends(require_role(AdminRole.hr_manager)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Create a new employee."""
    svc = AdminService(db, tenant_id)
    try:
        employee = await svc.create_employee(data.model_dump(exclude_none=True))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    await emit_audit_event(
        db, action="employee.created", actor_id=str(current_user.id),
        actor_email=current_user.email, tenant_id=str(tenant_id),
        resource_type="employee", resource_id=str(employee.id),
        detail={"employee_number": employee.employee_number},
        request=request,
    )

    return _employee_to_out(employee)


@router.get("/employees/export")
async def export_employees(
    request: Request,
    current_user: AdminUser = Depends(require_role(AdminRole.hr_manager)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Export all employees as CSV."""
    svc = AdminService(db, tenant_id)
    csv_content = await svc.export_employees_csv()

    await emit_audit_event(
        db, action="employee.exported", actor_id=str(current_user.id),
        actor_email=current_user.email, tenant_id=str(tenant_id),
        resource_type="employee", resource_id=None,
        request=request,
    )

    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=employees.csv"},
    )


@router.post("/employees/import", response_model=ImportResult)
async def import_employees(
    request: Request,
    file: UploadFile = File(...),
    current_user: AdminUser = Depends(require_role(AdminRole.hr_manager)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Import employees from a CSV file."""
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a CSV")

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="CSV file too large (max 10 MB)")
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise HTTPException(status_code=400, detail="File must be UTF-8 encoded")

    svc = AdminService(db, tenant_id)
    result = await svc.import_employees_csv(text)

    await emit_audit_event(
        db, action="employee.bulk_import", actor_id=str(current_user.id),
        actor_email=current_user.email, tenant_id=str(tenant_id),
        resource_type="employee", resource_id=None,
        detail={"created": result["created"], "errors": len(result["errors"]), "filename": file.filename},
        request=request,
    )

    return ImportResult(**result)


@router.get("/employees/{employee_id}", response_model=EmployeeOut)
async def get_employee(
    employee_id: UUID,
    current_user: AdminUser = Depends(require_role(AdminRole.hr_specialist)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Get full employee details."""
    svc = AdminService(db, tenant_id)
    employee = await svc.get_employee(employee_id)
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    return _employee_to_out(employee)


@router.put("/employees/{employee_id}", response_model=EmployeeOut)
async def update_employee(
    employee_id: UUID,
    data: EmployeeUpdateIn,
    request: Request,
    current_user: AdminUser = Depends(require_role(AdminRole.hr_manager)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Update employee (partial update — only provided fields)."""
    update_data = data.model_dump(exclude_none=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    # Validate status if provided
    if "status" in update_data:
        try:
            update_data["status"] = EmployeeStatus(update_data["status"])
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status. Must be one of: {[s.value for s in EmployeeStatus]}",
            )

    svc = AdminService(db, tenant_id)
    try:
        employee = await svc.update_employee(employee_id, update_data)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    await emit_audit_event(
        db, action="employee.updated", actor_id=str(current_user.id),
        actor_email=current_user.email, tenant_id=str(tenant_id),
        resource_type="employee", resource_id=str(employee_id),
        detail={"updated_fields": list(update_data.keys())},
        request=request,
    )

    return _employee_to_out(employee)


@router.delete("/employees/{employee_id}", response_model=EmployeeOut)
async def delete_employee(
    employee_id: UUID,
    request: Request,
    current_user: AdminUser = Depends(require_role(AdminRole.hr_manager)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Soft delete employee (set status=terminated, set end_date=now)."""
    svc = AdminService(db, tenant_id)
    try:
        employee = await svc.soft_delete_employee(employee_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    await emit_audit_event(
        db, action="employee.terminated", actor_id=str(current_user.id),
        actor_email=current_user.email, tenant_id=str(tenant_id),
        resource_type="employee", resource_id=str(employee_id),
        request=request,
    )

    return _employee_to_out(employee)


# ── Department CRUD ────────────────────────────────────────────────


@router.get("/departments", response_model=list[DepartmentOut])
async def list_departments(
    current_user: AdminUser = Depends(require_role(AdminRole.hr_specialist)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """List departments with active employee counts."""
    svc = AdminService(db, tenant_id)
    departments = await svc.list_departments_with_counts()
    return [DepartmentOut(**d) for d in departments]


@router.post("/departments", response_model=DepartmentOut, status_code=201)
async def create_department(
    data: DepartmentCreateIn,
    request: Request,
    current_user: AdminUser = Depends(require_role(AdminRole.hr_manager)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Create a new department."""
    svc = AdminService(db, tenant_id)
    dept = await svc.create_department(data.model_dump(exclude_none=True))

    await emit_audit_event(
        db, action="department.created", actor_id=str(current_user.id),
        actor_email=current_user.email, tenant_id=str(tenant_id),
        resource_type="department", resource_id=str(dept.id),
        detail={"name": dept.name},
        request=request,
    )

    return DepartmentOut(
        id=str(dept.id),
        name=dept.name,
        name_ar=dept.name_ar,
        manager_id=str(dept.manager_id) if dept.manager_id else None,
        headcount_budget=dept.headcount_budget,
        cost_budget_sar=dept.cost_budget_sar,
        active_employee_count=0,
    )


@router.put("/departments/{department_id}", response_model=DepartmentOut)
async def update_department(
    department_id: UUID,
    data: DepartmentUpdateIn,
    request: Request,
    current_user: AdminUser = Depends(require_role(AdminRole.hr_manager)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Update department."""
    update_data = data.model_dump(exclude_none=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    svc = AdminService(db, tenant_id)
    try:
        dept = await svc.update_department(department_id, update_data)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    await emit_audit_event(
        db, action="department.updated", actor_id=str(current_user.id),
        actor_email=current_user.email, tenant_id=str(tenant_id),
        resource_type="department", resource_id=str(department_id),
        detail={"updated_fields": list(update_data.keys())},
        request=request,
    )

    # Get fresh count
    departments = await svc.list_departments_with_counts()
    dept_data = next((d for d in departments if d["id"] == str(department_id)), None)
    count = dept_data["active_employee_count"] if dept_data else 0

    return DepartmentOut(
        id=str(dept.id),
        name=dept.name,
        name_ar=dept.name_ar,
        manager_id=str(dept.manager_id) if dept.manager_id else None,
        headcount_budget=dept.headcount_budget,
        cost_budget_sar=dept.cost_budget_sar,
        active_employee_count=count,
    )


@router.delete("/departments/{department_id}", status_code=204)
async def delete_department(
    department_id: UUID,
    request: Request,
    current_user: AdminUser = Depends(require_role(AdminRole.hr_manager)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Delete department. Returns 409 if it has active employees."""
    svc = AdminService(db, tenant_id)
    try:
        await svc.delete_department(department_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=409, detail=str(e))

    await emit_audit_event(
        db, action="department.deleted", actor_id=str(current_user.id),
        actor_email=current_user.email, tenant_id=str(tenant_id),
        resource_type="department", resource_id=str(department_id),
        request=request,
    )


# ── Leave Management (existing) ───────────────────────────────────


@router.get("/leave-requests", response_model=list[LeaveRequestOut])
async def list_leave_requests(
    status: Optional[str] = Query(None),
    department_id: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    current_user: AdminUser = Depends(require_role(AdminRole.hr_specialist)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """List leave requests with optional filters."""
    query = (
        select(LeaveRequest, Employee, Department)
        .join(Employee, LeaveRequest.employee_id == Employee.id)
        .outerjoin(Department, Employee.department_id == Department.id)
        .where(Employee.tenant_id == tenant_id)
    )

    if status:
        try:
            leave_status = LeaveStatus(status)
            query = query.where(LeaveRequest.status == leave_status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    if department_id:
        try:
            dept_uuid = UUID(department_id)
            query = query.where(Employee.department_id == dept_uuid)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid department_id")

    if date_from:
        try:
            df = date.fromisoformat(date_from)
            query = query.where(LeaveRequest.start_date >= df)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date_from format")

    if date_to:
        try:
            dt = date.fromisoformat(date_to)
            query = query.where(LeaveRequest.end_date <= dt)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date_to format")

    # Pending first, then by created_at DESC
    query = query.order_by(
        case(
            (LeaveRequest.status == LeaveStatus.pending, 0),
            else_=1,
        ),
        LeaveRequest.created_at.desc(),
    )

    result = await db.execute(query)
    rows = result.all()

    return [
        LeaveRequestOut(
            id=str(req.id),
            employee_name=emp.full_name,
            employee_number=emp.employee_number,
            department=dept.name if dept else None,
            leave_type=req.leave_type.value,
            start_date=req.start_date.isoformat(),
            end_date=req.end_date.isoformat(),
            business_days=req.business_days,
            status=req.status.value,
            reason=req.reason,
            created_at=req.created_at.isoformat(),
        )
        for req, emp, dept in rows
    ]


class RejectBody(BaseModel):
    reason: str = "Rejected by HR"


@router.patch("/leave-requests/{request_id}/approve")
async def approve_leave_request(
    request_id: UUID,
    current_user: AdminUser = Depends(require_role(AdminRole.hr_manager)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Approve a pending leave request."""
    result = await db.execute(
        select(LeaveRequest)
        .join(Employee, LeaveRequest.employee_id == Employee.id)
        .where(LeaveRequest.id == request_id, Employee.tenant_id == tenant_id)
    )
    req = result.scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="Leave request not found.")
    if req.status != LeaveStatus.pending:
        raise HTTPException(status_code=409, detail=f"Request is already {req.status.value}.")

    # Resolve approver's employee record
    emp_result = await db.execute(
        select(Employee).where(Employee.email == current_user.email, Employee.tenant_id == tenant_id)
    )
    approver = emp_result.scalar_one_or_none()

    req.status = LeaveStatus.approved
    req.approved_by = approver.id if approver else None
    req.approved_at = datetime.now(timezone.utc)
    await db.commit()

    return {"status": "approved", "request_id": str(request_id)}


@router.patch("/leave-requests/{request_id}/reject")
async def reject_leave_request(
    request_id: UUID,
    body: RejectBody,
    current_user: AdminUser = Depends(require_role(AdminRole.hr_manager)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Reject a pending leave request."""
    result = await db.execute(
        select(LeaveRequest)
        .join(Employee, LeaveRequest.employee_id == Employee.id)
        .where(LeaveRequest.id == request_id, Employee.tenant_id == tenant_id)
    )
    req = result.scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="Leave request not found.")
    if req.status != LeaveStatus.pending:
        raise HTTPException(status_code=409, detail=f"Request is already {req.status.value}.")

    emp_result = await db.execute(
        select(Employee).where(Employee.email == current_user.email, Employee.tenant_id == tenant_id)
    )
    rejector = emp_result.scalar_one_or_none()

    req.status = LeaveStatus.rejected
    req.rejected_by = rejector.id if rejector else None
    req.rejected_at = datetime.now(timezone.utc)
    req.rejection_reason = body.reason
    await db.commit()

    return {"status": "rejected", "request_id": str(request_id)}


@router.get("/leave-summary", response_model=LeaveSummary)
async def leave_summary(
    current_user: AdminUser = Depends(require_role(AdminRole.hr_specialist)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Summary stats for dashboard cards."""
    now = datetime.now(timezone.utc)
    month_start = date(now.year, now.month, 1)

    # Pending count (all time, filtered by tenant)
    pending = (
        await db.execute(
            select(func.count(LeaveRequest.id))
            .join(Employee, LeaveRequest.employee_id == Employee.id)
            .where(
                Employee.tenant_id == tenant_id,
                LeaveRequest.status == LeaveStatus.pending,
            )
        )
    ).scalar_one()

    # Approved this month
    approved = (
        await db.execute(
            select(func.count(LeaveRequest.id))
            .join(Employee, LeaveRequest.employee_id == Employee.id)
            .where(
                Employee.tenant_id == tenant_id,
                LeaveRequest.status == LeaveStatus.approved,
                LeaveRequest.created_at >= month_start,
            )
        )
    ).scalar_one()

    # Rejected this month
    rejected = (
        await db.execute(
            select(func.count(LeaveRequest.id))
            .join(Employee, LeaveRequest.employee_id == Employee.id)
            .where(
                Employee.tenant_id == tenant_id,
                LeaveRequest.status == LeaveStatus.rejected,
                LeaveRequest.created_at >= month_start,
            )
        )
    ).scalar_one()

    # Total this month
    total = (
        await db.execute(
            select(func.count(LeaveRequest.id))
            .join(Employee, LeaveRequest.employee_id == Employee.id)
            .where(
                Employee.tenant_id == tenant_id,
                LeaveRequest.created_at >= month_start,
            )
        )
    ).scalar_one()

    return LeaveSummary(
        pending=pending,
        approved_this_month=approved,
        rejected_this_month=rejected,
        total_this_month=total,
    )
