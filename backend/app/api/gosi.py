"""GOSI API — social insurance contribution management."""
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.admin_user import AdminUser, AdminRole
from app.auth.dependencies import require_role, require_tenant
from app.services.gosi import GOSIService

router = APIRouter(prefix="/gosi", tags=["gosi"])


@router.get("/summary")
async def get_gosi_summary(
    current_user: AdminUser = Depends(require_role(AdminRole.hr_manager)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Tenant-wide GOSI contribution summary. Requires hr_manager role."""
    svc = GOSIService(db, tenant_id)
    return await svc.get_tenant_summary()


@router.get("/contributions/{employee_id}")
async def get_employee_contributions(
    employee_id: UUID,
    current_user: AdminUser = Depends(require_role(AdminRole.hr_manager)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """GOSI contribution details for a specific employee."""
    svc = GOSIService(db, tenant_id)
    return await svc.calculate_contributions(employee_id)


@router.get("/registration-status/{employee_id}")
async def get_registration_status(
    employee_id: UUID,
    current_user: AdminUser = Depends(require_role(AdminRole.hr_manager)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Check GOSI registration status for an employee."""
    svc = GOSIService(db, tenant_id)
    return await svc.check_registration_status(employee_id)


@router.post("/register/{employee_id}")
async def register_employee(
    employee_id: UUID,
    current_user: AdminUser = Depends(require_role(AdminRole.hr_manager)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Register an employee with GOSI. Sets gosi_registered flag."""
    svc = GOSIService(db, tenant_id)
    result = await svc.register_employee(employee_id)
    await db.commit()
    return result


@router.get("/monthly-report")
async def get_monthly_report(
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
    current_user: AdminUser = Depends(require_role(AdminRole.hr_manager)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Generate monthly GOSI contribution report for all employees."""
    svc = GOSIService(db, tenant_id)
    return await svc.generate_monthly_report(year, month)
