"""Nitaqat/Saudization compliance API."""
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.admin_user import AdminUser, AdminRole
from app.auth.dependencies import require_role, require_tenant
from app.services.nitaqat import NitaqatService
from app.models.nitaqat import NitaqatConfig, CompanySizeCategory

router = APIRouter(prefix="/nitaqat", tags=["nitaqat"])


class NitaqatConfigUpdate(BaseModel):
    industry: str | None = None
    industry_ar: str | None = None
    size_category: str | None = None
    platinum_threshold: float | None = Field(None, ge=0, le=100)
    green_high_threshold: float | None = Field(None, ge=0, le=100)
    green_low_threshold: float | None = Field(None, ge=0, le=100)
    yellow_threshold: float | None = Field(None, ge=0, le=100)
    target_saudization_pct: float | None = Field(None, ge=0, le=100)
    alert_when_below_target: bool | None = None
    alert_buffer_pct: float | None = Field(None, ge=0, le=50)


class SimulationRequest(BaseModel):
    hire_saudi: int = Field(0, ge=0, le=100000)
    hire_non_saudi: int = Field(0, ge=0, le=100000)
    terminate_saudi: int = Field(0, ge=0, le=100000)
    terminate_non_saudi: int = Field(0, ge=0, le=100000)


@router.get("/status")
async def get_nitaqat_status(
    current_user: AdminUser = Depends(require_role(AdminRole.hr_manager)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Current Nitaqat status: ratio, band, gap analysis, thresholds."""
    svc = NitaqatService(db, tenant_id)
    return await svc.get_current_status()


@router.post("/simulate")
async def simulate_nitaqat(
    req: SimulationRequest,
    current_user: AdminUser = Depends(require_role(AdminRole.hr_manager)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """What-if simulator: project Nitaqat band after hypothetical hire/terminate changes."""
    svc = NitaqatService(db, tenant_id)
    return await svc.simulate(
        hire_saudi=req.hire_saudi,
        hire_non_saudi=req.hire_non_saudi,
        terminate_saudi=req.terminate_saudi,
        terminate_non_saudi=req.terminate_non_saudi,
    )


@router.get("/termination-impact/{employee_id}")
async def check_termination_impact(
    employee_id: UUID,
    current_user: AdminUser = Depends(require_role(AdminRole.hr_manager)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Check if terminating a specific employee would cause a Nitaqat band drop."""
    svc = NitaqatService(db, tenant_id)
    return await svc.check_termination_impact(employee_id)


@router.put("/config")
async def update_nitaqat_config(
    data: NitaqatConfigUpdate,
    current_user: AdminUser = Depends(require_role(AdminRole.tenant_admin)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Create or update Nitaqat configuration for the tenant."""
    from sqlalchemy import select
    result = await db.execute(
        select(NitaqatConfig).where(NitaqatConfig.tenant_id == tenant_id).with_for_update()
    )
    config = result.scalar_one_or_none()

    if not config:
        config = NitaqatConfig(tenant_id=tenant_id)
        db.add(config)

    update_fields = data.model_dump(exclude_unset=True)
    if "size_category" in update_fields and update_fields["size_category"]:
        update_fields["size_category"] = CompanySizeCategory(update_fields["size_category"])

    for field, value in update_fields.items():
        setattr(config, field, value)

    # Finding 5: Validate threshold ordering before commit
    if not (config.yellow_threshold < config.green_low_threshold < config.green_high_threshold < config.platinum_threshold):
        raise HTTPException(status_code=400, detail="Thresholds must satisfy: yellow < green_low < green_high < platinum")

    config.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(config)

    return {
        "status": "updated",
        "config": {
            "industry": config.industry,
            "industry_ar": config.industry_ar,
            "size_category": config.size_category.value,
            "platinum_threshold": config.platinum_threshold,
            "green_high_threshold": config.green_high_threshold,
            "green_low_threshold": config.green_low_threshold,
            "yellow_threshold": config.yellow_threshold,
            "target_saudization_pct": config.target_saudization_pct,
            "alert_when_below_target": config.alert_when_below_target,
            "alert_buffer_pct": config.alert_buffer_pct,
        },
    }
