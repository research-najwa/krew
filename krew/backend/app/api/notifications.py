"""Notification API — list, read, and manage notification preferences."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.admin_user import AdminUser
from app.auth.dependencies import get_current_user, require_tenant
from app.api.helpers import resolve_employee_id
from app.services.notification import NotificationService

router = APIRouter(prefix="/notifications", tags=["notifications"])


# -- Response schemas --------------------------------------------------------


class NotificationOut(BaseModel):
    id: str
    title: str
    title_ar: str | None
    body: str
    body_ar: str | None
    category: str
    priority: str
    is_read: bool
    read_at: str | None
    resource_type: str | None
    resource_id: str | None
    created_at: str


class UnreadCountOut(BaseModel):
    count: int


class PreferencesOut(BaseModel):
    leave_notifications: bool
    policy_notifications: bool
    escalation_notifications: bool
    document_notifications: bool


class PreferencesUpdate(BaseModel):
    leave_notifications: bool | None = None
    policy_notifications: bool | None = None
    escalation_notifications: bool | None = None
    document_notifications: bool | None = None


# -- Endpoints ---------------------------------------------------------------


@router.get("/", response_model=list[NotificationOut])
async def list_notifications(
    unread_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: AdminUser = Depends(get_current_user),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """List notifications for the current employee."""
    employee_id = await resolve_employee_id(current_user, tenant_id, db)
    svc = NotificationService(db, tenant_id)
    notifications = await svc.get_notifications(
        employee_id=employee_id,
        unread_only=unread_only,
        limit=limit,
        offset=offset,
    )

    return [
        NotificationOut(
            id=str(n.id),
            title=n.title,
            title_ar=n.title_ar,
            body=n.body,
            body_ar=n.body_ar,
            category=n.category.value,
            priority=n.priority.value,
            is_read=n.is_read,
            read_at=n.read_at.isoformat() if n.read_at else None,
            resource_type=n.resource_type,
            resource_id=str(n.resource_id) if n.resource_id else None,
            created_at=n.created_at.isoformat(),
        )
        for n in notifications
    ]


@router.get("/unread-count", response_model=UnreadCountOut)
async def unread_count(
    current_user: AdminUser = Depends(get_current_user),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Get unread notification count for the current employee."""
    employee_id = await resolve_employee_id(current_user, tenant_id, db)
    svc = NotificationService(db, tenant_id)
    count = await svc.get_unread_count(employee_id)
    return UnreadCountOut(count=count)


@router.post("/{notification_id}/read")
async def mark_read(
    notification_id: UUID,  # Finding 13: UUID path param
    current_user: AdminUser = Depends(get_current_user),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Mark a single notification as read."""
    employee_id = await resolve_employee_id(current_user, tenant_id, db)
    svc = NotificationService(db, tenant_id)
    updated = await svc.mark_read(notification_id, employee_id)
    if not updated:
        raise HTTPException(
            status_code=404,
            detail="Notification not found or already read.",
        )
    await db.commit()
    return {"status": "read"}


@router.post("/read-all")
async def mark_all_read(
    current_user: AdminUser = Depends(get_current_user),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Mark all notifications as read for the current employee."""
    employee_id = await resolve_employee_id(current_user, tenant_id, db)
    svc = NotificationService(db, tenant_id)
    count = await svc.mark_all_read(employee_id)
    await db.commit()
    return {"status": "ok", "marked_read": count}


@router.get("/preferences", response_model=PreferencesOut)
async def get_preferences(
    current_user: AdminUser = Depends(get_current_user),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Get notification preferences for the current employee.

    Finding 19: Returns defaults without persisting if no preferences exist.
    """
    employee_id = await resolve_employee_id(current_user, tenant_id, db)
    svc = NotificationService(db, tenant_id)
    prefs = await svc.get_preferences(employee_id)

    if prefs is None:
        # Return defaults without creating a DB record
        return PreferencesOut(
            leave_notifications=True,
            policy_notifications=True,
            escalation_notifications=True,
            document_notifications=True,
        )

    return PreferencesOut(
        leave_notifications=prefs.leave_notifications,
        policy_notifications=prefs.policy_notifications,
        escalation_notifications=prefs.escalation_notifications,
        document_notifications=prefs.document_notifications,
    )


@router.put("/preferences", response_model=PreferencesOut)
async def update_preferences(
    body: PreferencesUpdate,
    current_user: AdminUser = Depends(get_current_user),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Update notification preferences for the current employee."""
    employee_id = await resolve_employee_id(current_user, tenant_id, db)
    svc = NotificationService(db, tenant_id)
    kwargs = body.model_dump(exclude_unset=True)
    prefs = await svc.update_preferences(employee_id, **kwargs)
    await db.commit()
    return PreferencesOut(
        leave_notifications=prefs.leave_notifications,
        policy_notifications=prefs.policy_notifications,
        escalation_notifications=prefs.escalation_notifications,
        document_notifications=prefs.document_notifications,
    )
