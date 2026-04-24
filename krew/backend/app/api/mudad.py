"""Mudad (Wage Protection System) API — salary payment compliance."""
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.admin_user import AdminUser, AdminRole
from app.auth.dependencies import require_role, require_tenant
from app.services.mudad import MudadService

router = APIRouter(prefix="/mudad", tags=["mudad"])


@router.get("/compliance")
async def get_compliance_status(
    current_user: AdminUser = Depends(require_role(AdminRole.hr_manager)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Mudad wage protection compliance status. Requires hr_manager role."""
    svc = MudadService(db, tenant_id)
    return await svc.check_compliance_status()


@router.get("/wps-file")
async def get_wps_file(
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
    current_user: AdminUser = Depends(require_role(AdminRole.hr_manager)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Generate WPS (Wage Protection System) file data for Mudad submission."""
    svc = MudadService(db, tenant_id)
    return await svc.generate_wps_file(year, month)


@router.post("/submit")
async def submit_payment_report(
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
    current_user: AdminUser = Depends(require_role(AdminRole.hr_manager)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Submit salary payment report to Mudad."""
    svc = MudadService(db, tenant_id)
    return await svc.submit_payment_report(year, month)


@router.get("/payment-history/{employee_id}")
async def get_payment_history(
    employee_id: UUID,
    months: int = Query(6, ge=1, le=24),
    current_user: AdminUser = Depends(require_role(AdminRole.hr_manager)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Get Mudad payment history for a specific employee."""
    svc = MudadService(db, tenant_id)
    return await svc.get_employee_payment_history(employee_id, months)
