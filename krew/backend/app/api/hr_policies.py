"""HR Policy CRUD API — create, publish, archive, version, and acknowledge policies."""
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.admin_user import AdminUser, AdminRole
from app.auth.dependencies import get_current_user, has_minimum_role, require_role, require_tenant
from app.api.helpers import resolve_employee_id
from app.services.policy import PolicyService
from app.models.hr_policy import PolicyStatus
from app.security.rate_limiter import _get_client_ip

router = APIRouter(prefix="/hr-policies", tags=["hr-policies"])


# -- Request / Response schemas ----------------------------------------------


class PolicyCreate(BaseModel):
    title: str = Field(..., max_length=500)
    title_ar: str | None = Field(None, max_length=500)
    content: str = Field(..., max_length=100000)
    content_ar: str | None = Field(None, max_length=100000)
    category: str
    effective_date: date  # Finding 11: proper date type


class PolicyUpdate(BaseModel):
    title: str | None = Field(None, max_length=500)
    title_ar: str | None = Field(None, max_length=500)
    content: str | None = Field(None, max_length=100000)
    content_ar: str | None = Field(None, max_length=100000)
    category: str | None = None
    effective_date: date | None = None  # Finding 11: proper date type


class PolicyOut(BaseModel):
    id: str
    title: str
    title_ar: str | None
    content: str
    content_ar: str | None
    category: str
    status: str
    version: int
    parent_id: str | None
    effective_date: str
    published_at: str | None
    archived_at: str | None
    created_at: str
    updated_at: str


class AcknowledgmentStatusOut(BaseModel):
    policy_id: str
    acknowledged: int
    total_active_employees: int
    pending: int


class PendingPolicyOut(BaseModel):
    id: str
    title: str
    title_ar: str | None
    category: str
    effective_date: str
    published_at: str | None


# -- Helpers -----------------------------------------------------------------


def _policy_to_out(p) -> PolicyOut:
    return PolicyOut(
        id=str(p.id),
        title=p.title,
        title_ar=p.title_ar,
        content=p.content,
        content_ar=p.content_ar,
        category=p.category.value,
        status=p.status.value,
        version=p.version,
        parent_id=str(p.parent_id) if p.parent_id else None,
        effective_date=p.effective_date.isoformat(),
        published_at=p.published_at.isoformat() if p.published_at else None,
        archived_at=p.archived_at.isoformat() if p.archived_at else None,
        created_at=p.created_at.isoformat(),
        updated_at=p.updated_at.isoformat(),
    )


# -- Endpoints ---------------------------------------------------------------


@router.post("/", response_model=PolicyOut)
async def create_policy(
    body: PolicyCreate,
    current_user: AdminUser = Depends(require_role(AdminRole.hr_manager)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Create a new draft policy (hr_manager+)."""
    # Finding 11: effective_date is already a date object from Pydantic
    employee_id = await resolve_employee_id(current_user, tenant_id, db)
    svc = PolicyService(db, tenant_id)
    policy = await svc.create_draft(
        title=body.title,
        title_ar=body.title_ar,
        content=body.content,
        content_ar=body.content_ar,
        category=body.category,
        effective_date=body.effective_date,
        created_by=employee_id,
    )
    await db.commit()
    await db.refresh(policy)
    return _policy_to_out(policy)


@router.get("/", response_model=list[PolicyOut])
async def list_policies(
    category: str | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: AdminUser = Depends(get_current_user),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """List policies. Employees see published only; HR sees all."""
    # Finding 12: Use has_minimum_role instead of _ROLE_RANK
    if not has_minimum_role(current_user, AdminRole.hr_manager):
        status = "published"

    svc = PolicyService(db, tenant_id)
    policies = await svc.list_policies(
        category=category,
        status=status,
        limit=limit,
        offset=offset,
    )
    return [_policy_to_out(p) for p in policies]


@router.get("/pending-acknowledgments", response_model=list[PendingPolicyOut])
async def pending_acknowledgments(
    current_user: AdminUser = Depends(get_current_user),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Get policies the current employee hasn't acknowledged yet."""
    employee_id = await resolve_employee_id(current_user, tenant_id, db)
    svc = PolicyService(db, tenant_id)
    policies = await svc.get_pending_acknowledgments(employee_id)
    return [
        PendingPolicyOut(
            id=str(p.id),
            title=p.title,
            title_ar=p.title_ar,
            category=p.category.value,
            effective_date=p.effective_date.isoformat(),
            published_at=p.published_at.isoformat() if p.published_at else None,
        )
        for p in policies
    ]


@router.get("/{policy_id}", response_model=PolicyOut)
async def get_policy(
    policy_id: UUID,  # Finding 13: UUID path param
    current_user: AdminUser = Depends(get_current_user),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Get a single policy."""
    svc = PolicyService(db, tenant_id)
    policy = await svc.get_policy(policy_id)

    # Finding 12: Use has_minimum_role
    if not has_minimum_role(current_user, AdminRole.hr_manager) and policy.status != PolicyStatus.published:
        raise HTTPException(status_code=404, detail="Policy not found.")

    return _policy_to_out(policy)


@router.put("/{policy_id}", response_model=PolicyOut)
async def update_policy(
    policy_id: UUID,  # Finding 13
    body: PolicyUpdate,
    current_user: AdminUser = Depends(require_role(AdminRole.hr_manager)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Update a draft policy (hr_manager+)."""
    # Finding 11: effective_date is already a date object from Pydantic
    updates = body.model_dump(exclude_unset=True)

    svc = PolicyService(db, tenant_id)
    policy = await svc.update_draft(policy_id, **updates)
    await db.commit()
    await db.refresh(policy)
    return _policy_to_out(policy)


@router.post("/{policy_id}/publish", response_model=PolicyOut)
async def publish_policy(
    policy_id: UUID,  # Finding 13
    current_user: AdminUser = Depends(require_role(AdminRole.hr_manager)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Publish a draft policy (hr_manager+)."""
    svc = PolicyService(db, tenant_id)
    policy = await svc.publish(policy_id)
    await db.commit()
    await db.refresh(policy)
    return _policy_to_out(policy)


@router.post("/{policy_id}/archive", response_model=PolicyOut)
async def archive_policy(
    policy_id: UUID,  # Finding 13
    current_user: AdminUser = Depends(require_role(AdminRole.hr_manager)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Archive a policy (hr_manager+)."""
    svc = PolicyService(db, tenant_id)
    policy = await svc.archive(policy_id)
    await db.commit()
    await db.refresh(policy)
    return _policy_to_out(policy)


@router.post("/{policy_id}/new-version", response_model=PolicyOut)
async def new_version(
    policy_id: UUID,  # Finding 13
    current_user: AdminUser = Depends(require_role(AdminRole.hr_manager)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Create a new draft version from a published policy (hr_manager+)."""
    svc = PolicyService(db, tenant_id)
    policy = await svc.create_new_version(policy_id)
    await db.commit()
    await db.refresh(policy)
    return _policy_to_out(policy)


@router.post("/{policy_id}/acknowledge")
async def acknowledge_policy(
    policy_id: UUID,  # Finding 13
    request: Request,
    current_user: AdminUser = Depends(get_current_user),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Employee acknowledges a published policy."""
    employee_id = await resolve_employee_id(current_user, tenant_id, db)

    # Finding 18: Use proxy-aware IP extraction
    ip_address = _get_client_ip(request)

    svc = PolicyService(db, tenant_id)
    ack = await svc.acknowledge(policy_id, employee_id, ip_address=ip_address)
    await db.commit()
    return {
        "status": "acknowledged",
        "policy_id": str(policy_id),
        "acknowledged_at": ack.acknowledged_at.isoformat(),
    }


@router.get("/{policy_id}/acknowledgments", response_model=AcknowledgmentStatusOut)
async def acknowledgment_status(
    policy_id: UUID,  # Finding 13
    current_user: AdminUser = Depends(require_role(AdminRole.hr_manager)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Get acknowledgment status for a policy (hr_manager+)."""
    svc = PolicyService(db, tenant_id)
    status = await svc.get_acknowledgment_status(policy_id)
    return AcknowledgmentStatusOut(**status)
