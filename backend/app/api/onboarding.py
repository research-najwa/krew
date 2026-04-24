"""Onboarding API — template management and employee onboarding tracking."""
import html
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.admin_user import AdminUser, AdminRole
from app.auth.dependencies import require_role, require_tenant
from app.services.onboarding import OnboardingService

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


class StepDefinition(BaseModel):
    name: str
    name_ar: str | None = None
    description: str | None = None
    description_ar: str | None = None
    step_type: Literal["manual", "automatic", "agent_assisted"] = "manual"
    order: int | None = None
    due_days_after_hire: int = 7
    is_required: bool = True
    auto_trigger: str | None = None

    @field_validator("name", "name_ar", "description", "description_ar", mode="before")
    @classmethod
    def sanitize_html(cls, v):
        if isinstance(v, str):
            return html.escape(v)
        return v


class CreateTemplateRequest(BaseModel):
    name: str
    name_ar: str | None = None
    description: str | None = None
    is_default: bool = False
    steps: list[StepDefinition]

    @field_validator("name", "name_ar", "description", mode="before")
    @classmethod
    def sanitize_html(cls, v):
        if isinstance(v, str):
            return html.escape(v)
        return v


class AssignRequest(BaseModel):
    employee_id: UUID
    template_id: UUID | None = None  # None = use default


class CompleteStepRequest(BaseModel):
    step_id: UUID


# ── Templates ───────────────────────────────────────────────

@router.post("/templates")
async def create_template(
    req: CreateTemplateRequest,
    current_user: AdminUser = Depends(require_role(AdminRole.hr_manager)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    svc = OnboardingService(db, tenant_id)
    return await svc.create_template(
        name=req.name, name_ar=req.name_ar, description=req.description,
        is_default=req.is_default, steps=[s.model_dump() for s in req.steps],
    )


@router.get("/templates")
async def list_templates(
    current_user: AdminUser = Depends(require_role(AdminRole.hr_specialist)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    svc = OnboardingService(db, tenant_id)
    return await svc.list_templates()


# ── Assignments ─────────────────────────────────────────────

@router.post("/assign")
async def assign_onboarding(
    req: AssignRequest,
    current_user: AdminUser = Depends(require_role(AdminRole.hr_specialist)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    svc = OnboardingService(db, tenant_id)
    result = await svc.assign_to_employee(req.employee_id, req.template_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/employee/{employee_id}")
async def get_employee_onboarding(
    employee_id: UUID,
    current_user: AdminUser = Depends(require_role(AdminRole.hr_specialist)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    svc = OnboardingService(db, tenant_id)
    result = await svc.get_employee_onboarding(employee_id)
    if not result:
        raise HTTPException(status_code=404, detail="No active onboarding found for this employee")
    return result


@router.post("/assignments/{assignment_id}/complete-step")
async def complete_step(
    assignment_id: UUID,
    req: CompleteStepRequest,
    current_user: AdminUser = Depends(require_role(AdminRole.hr_specialist)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    svc = OnboardingService(db, tenant_id)
    result = await svc.complete_step(assignment_id, req.step_id, f"hr:{current_user.id}")
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/dashboard")
async def onboarding_dashboard(
    current_user: AdminUser = Depends(require_role(AdminRole.hr_specialist)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    svc = OnboardingService(db, tenant_id)
    return await svc.get_onboarding_dashboard()


@router.get("/overdue")
async def overdue_steps(
    current_user: AdminUser = Depends(require_role(AdminRole.hr_specialist)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    svc = OnboardingService(db, tenant_id)
    return await svc.get_overdue_steps()
