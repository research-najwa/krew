"""Audit log API — read-only access for HR managers."""
from datetime import date, datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.audit_log import AuditLog
from app.models.admin_user import AdminUser, AdminRole
from app.auth.dependencies import require_role, require_tenant

router = APIRouter(prefix="/audit", tags=["audit"])

# PII fields that hr_manager should not see in audit detail
_PII_FIELDS = {"email", "ip", "user_agent", "ip_address"}


def _sanitize_detail(detail: dict | None, role: AdminRole) -> dict | None:
    """Remove PII fields from audit detail for lower-privilege roles.

    tenant_admin and super_admin see the full detail. hr_manager and below
    get PII fields stripped out.
    """
    if detail is None:
        return None
    if role in (AdminRole.tenant_admin, AdminRole.super_admin):
        return detail
    return {k: v for k, v in detail.items() if k not in _PII_FIELDS}


# ── Response schemas ─────────────────────────────────────────────


class AuditLogOut(BaseModel):
    id: str
    tenant_id: str | None
    actor_id: str | None
    actor_email: str | None
    action: str
    resource_type: str | None
    resource_id: str | None
    detail: dict | None
    ip_address: str | None
    user_agent: str | None
    created_at: str


class AuditLogPage(BaseModel):
    items: list[AuditLogOut]
    total: int
    page: int
    page_size: int


# ── Endpoints ────────────────────────────────────────────────────


@router.get("/logs", response_model=AuditLogPage)
async def list_audit_logs(
    action: Optional[str] = Query(None),
    actor_email: Optional[str] = Query(None),
    resource_type: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: AdminUser = Depends(require_role(AdminRole.hr_manager)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """List audit logs scoped to tenant, with optional filters and pagination."""
    # super_admin can also see system-level events (tenant_id IS NULL)
    if current_user.role == AdminRole.super_admin:
        base_filter = or_(AuditLog.tenant_id == tenant_id, AuditLog.tenant_id.is_(None))
    else:
        base_filter = AuditLog.tenant_id == tenant_id

    query = select(AuditLog).where(base_filter)
    count_query = select(func.count(AuditLog.id)).where(base_filter)

    if action:
        query = query.where(AuditLog.action == action)
        count_query = count_query.where(AuditLog.action == action)

    if actor_email:
        query = query.where(AuditLog.actor_email == actor_email)
        count_query = count_query.where(AuditLog.actor_email == actor_email)

    if resource_type:
        query = query.where(AuditLog.resource_type == resource_type)
        count_query = count_query.where(AuditLog.resource_type == resource_type)

    if date_from:
        dt_from = datetime(date_from.year, date_from.month, date_from.day, tzinfo=timezone.utc)
        query = query.where(AuditLog.created_at >= dt_from)
        count_query = count_query.where(AuditLog.created_at >= dt_from)

    if date_to:
        dt_to = datetime(date_to.year, date_to.month, date_to.day, 23, 59, 59, tzinfo=timezone.utc)
        query = query.where(AuditLog.created_at <= dt_to)
        count_query = count_query.where(AuditLog.created_at <= dt_to)

    # Get total count
    total = (await db.execute(count_query)).scalar_one()

    # Paginate
    offset = (page - 1) * page_size
    query = query.order_by(AuditLog.created_at.desc()).offset(offset).limit(page_size)

    result = await db.execute(query)
    logs = result.scalars().all()

    # Sanitize PII based on the caller's role
    is_privileged = current_user.role in (AdminRole.tenant_admin, AdminRole.super_admin)

    return AuditLogPage(
        items=[
            AuditLogOut(
                id=str(log.id),
                tenant_id=str(log.tenant_id) if log.tenant_id else None,
                actor_id=str(log.actor_id) if log.actor_id else None,
                actor_email=log.actor_email,
                action=log.action,
                resource_type=log.resource_type,
                resource_id=log.resource_id,
                detail=_sanitize_detail(log.detail, current_user.role),
                ip_address=log.ip_address if is_privileged else None,
                user_agent=log.user_agent if is_privileged else None,
                created_at=log.created_at.isoformat(),
            )
            for log in logs
        ],
        total=total,
        page=page,
        page_size=page_size,
    )
