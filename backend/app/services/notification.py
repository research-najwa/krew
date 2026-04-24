"""Notification service — create, list, and manage in-app notifications."""
import html
import logging
import uuid
from datetime import datetime, timezone

from starlette.background import BackgroundTasks
from sqlalchemy import select, func, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import (
    Notification,
    NotificationPreference,
    NotificationCategory,
    NotificationPriority,
    NotificationChannel,
)

logger = logging.getLogger(__name__)


class NotificationService:
    """Handles notification creation, retrieval, and preference management."""

    def __init__(self, db: AsyncSession, tenant_id: uuid.UUID):
        self.db = db
        self.tenant_id = tenant_id
        self._background_tasks: BackgroundTasks | None = None

    def set_background_tasks(self, background_tasks: BackgroundTasks) -> "NotificationService":
        """Attach BackgroundTasks so dispatch runs after response.

        Returns self for chaining.
        """
        self._background_tasks = background_tasks
        return self

    async def send(
        self,
        employee_id: uuid.UUID,
        title: str,
        title_ar: str | None = None,
        body: str = "",
        body_ar: str | None = None,
        category: str | NotificationCategory = NotificationCategory.general,
        priority: str | NotificationPriority = NotificationPriority.normal,
        channel: str | NotificationChannel = NotificationChannel.in_app,
        resource_type: str | None = None,
        resource_id: uuid.UUID | None = None,
        _prefs_cache: dict[uuid.UUID, NotificationPreference | None] | None = None,
    ) -> Notification | None:
        """Create a notification for a single employee, respecting preferences.

        Returns the Notification object if created, or None if suppressed by preferences.
        If a BackgroundTasks instance is attached, delivery is dispatched asynchronously.
        The optional _prefs_cache is used by send_bulk to avoid N+1 queries.
        """
        # Normalize enums
        if isinstance(category, str):
            category = NotificationCategory(category)
        if isinstance(priority, str):
            priority = NotificationPriority(priority)
        if isinstance(channel, str):
            channel = NotificationChannel(channel)

        # Check preferences — use cache if provided (Finding 5)
        if _prefs_cache is not None:
            prefs = _prefs_cache.get(employee_id)
            if not self._check_category_from_prefs(prefs, category):
                logger.debug(
                    "Notification suppressed by preference: employee=%s category=%s",
                    employee_id, category.value,
                )
                return None
        else:
            if not await self._is_category_enabled(employee_id, category):
                logger.debug(
                    "Notification suppressed by preference: employee=%s category=%s",
                    employee_id, category.value,
                )
                return None

        # Finding 6: Escape HTML entities to prevent stored XSS
        title = html.escape(title)
        if title_ar:
            title_ar = html.escape(title_ar)
        body = html.escape(body)
        if body_ar:
            body_ar = html.escape(body_ar)

        notification = Notification(
            tenant_id=self.tenant_id,
            employee_id=employee_id,
            title=title,
            title_ar=title_ar,
            body=body,
            body_ar=body_ar,
            category=category,
            priority=priority,
            channel=channel,
            resource_type=resource_type,
            resource_id=resource_id,
        )
        self.db.add(notification)
        await self.db.flush()

        # Schedule delivery in background if BackgroundTasks attached
        self._schedule_dispatch(notification.id)

        return notification

    def _schedule_dispatch(self, notification_id: uuid.UUID) -> None:
        """Schedule background delivery for a notification."""
        from app.services.notification_dispatcher import dispatch_notification

        if self._background_tasks is not None:
            self._background_tasks.add_task(dispatch_notification, notification_id)
        else:
            logger.debug(
                "No BackgroundTasks attached — skipping dispatch for notification %s",
                notification_id,
            )

    async def send_bulk(
        self,
        employee_ids: list[uuid.UUID],
        title: str,
        title_ar: str | None = None,
        body: str = "",
        body_ar: str | None = None,
        category: str | NotificationCategory = NotificationCategory.general,
        priority: str | NotificationPriority = NotificationPriority.normal,
        channel: str | NotificationChannel = NotificationChannel.in_app,
        resource_type: str | None = None,
        resource_id: uuid.UUID | None = None,
    ) -> list[Notification]:
        """Create notifications for multiple employees, respecting individual preferences."""
        if isinstance(category, str):
            category = NotificationCategory(category)
        if isinstance(priority, str):
            priority = NotificationPriority(priority)

        # Finding 5: Batch-fetch all preferences in a single query
        prefs_cache = await self._batch_fetch_preferences(employee_ids)

        created = []
        for emp_id in employee_ids:
            notif = await self.send(
                employee_id=emp_id,
                title=title,
                title_ar=title_ar,
                body=body,
                body_ar=body_ar,
                category=category,
                priority=priority,
                channel=channel,
                resource_type=resource_type,
                resource_id=resource_id,
                _prefs_cache=prefs_cache,
            )
            if notif:
                created.append(notif)
        return created

    async def get_notifications(
        self,
        employee_id: uuid.UUID,
        unread_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Notification]:
        """List notifications for an employee with pagination."""
        query = (
            select(Notification)
            .where(
                Notification.tenant_id == self.tenant_id,
                Notification.employee_id == employee_id,
            )
            .order_by(Notification.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        if unread_only:
            query = query.where(Notification.is_read.is_(False))  # Finding 15

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def mark_read(
        self,
        notification_id: uuid.UUID,
        employee_id: uuid.UUID,
    ) -> bool:
        """Mark a single notification as read. Returns True if updated."""
        result = await self.db.execute(
            select(Notification).where(
                Notification.id == notification_id,
                Notification.tenant_id == self.tenant_id,
                Notification.employee_id == employee_id,
                Notification.is_read.is_(False),  # Finding 15
            )
        )
        notification = result.scalar_one_or_none()
        if not notification:
            return False

        notification.is_read = True
        notification.read_at = datetime.now(timezone.utc)  # Finding 21
        await self.db.flush()
        return True

    async def mark_all_read(self, employee_id: uuid.UUID) -> int:
        """Mark all unread notifications as read. Returns count updated."""
        now = datetime.now(timezone.utc)  # Finding 21
        result = await self.db.execute(
            update(Notification)
            .where(
                Notification.tenant_id == self.tenant_id,
                Notification.employee_id == employee_id,
                Notification.is_read.is_(False),  # Finding 15
            )
            .values(is_read=True, read_at=now)
        )
        await self.db.flush()
        return result.rowcount

    async def get_unread_count(self, employee_id: uuid.UUID) -> int:
        """Count unread notifications for an employee."""
        result = await self.db.execute(
            select(func.count(Notification.id)).where(
                Notification.tenant_id == self.tenant_id,
                Notification.employee_id == employee_id,
                Notification.is_read.is_(False),  # Finding 15
            )
        )
        return result.scalar_one()

    async def get_preferences(self, employee_id: uuid.UUID) -> NotificationPreference | None:
        """Get notification preferences for an employee, or None if not set.

        Finding 19: GET should not create preferences. Returns None if none exist,
        and callers use defaults.
        """
        result = await self.db.execute(
            select(NotificationPreference).where(
                NotificationPreference.tenant_id == self.tenant_id,
                NotificationPreference.employee_id == employee_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_or_create_preferences(self, employee_id: uuid.UUID) -> NotificationPreference:
        """Get or create default notification preferences for an employee.

        Finding 4: Wraps INSERT in try/except IntegrityError for race condition safety.
        """
        prefs = await self.get_preferences(employee_id)
        if prefs:
            return prefs

        # Create default preferences
        prefs = NotificationPreference(
            tenant_id=self.tenant_id,
            employee_id=employee_id,
        )
        self.db.add(prefs)
        try:
            await self.db.flush()
        except IntegrityError:
            await self.db.rollback()
            # Re-fetch — the other concurrent request already created it
            result = await self.db.execute(
                select(NotificationPreference).where(
                    NotificationPreference.tenant_id == self.tenant_id,
                    NotificationPreference.employee_id == employee_id,
                )
            )
            prefs = result.scalar_one()
        return prefs

    async def update_preferences(self, employee_id: uuid.UUID, **kwargs) -> NotificationPreference:
        """Update notification preferences for an employee.

        Finding 19: Creates preferences on first PUT, not on GET.
        """
        prefs = await self.get_or_create_preferences(employee_id)

        allowed_fields = {
            "leave_notifications", "policy_notifications",
            "escalation_notifications", "document_notifications",
        }
        for field, value in kwargs.items():
            if field in allowed_fields and isinstance(value, bool):
                setattr(prefs, field, value)

        await self.db.flush()
        return prefs

    async def _batch_fetch_preferences(
        self, employee_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, NotificationPreference | None]:
        """Finding 5: Batch-fetch preferences for multiple employees in one query."""
        if not employee_ids:
            return {}
        result = await self.db.execute(
            select(NotificationPreference).where(
                NotificationPreference.tenant_id == self.tenant_id,
                NotificationPreference.employee_id.in_(employee_ids),
            )
        )
        prefs_list = result.scalars().all()
        prefs_map: dict[uuid.UUID, NotificationPreference | None] = {
            p.employee_id: p for p in prefs_list
        }
        # Fill in None for employees without preferences
        for eid in employee_ids:
            if eid not in prefs_map:
                prefs_map[eid] = None
        return prefs_map

    @staticmethod
    def _check_category_from_prefs(
        prefs: NotificationPreference | None,
        category: NotificationCategory,
    ) -> bool:
        """Check if a category is enabled given a preferences object (or None for defaults)."""
        if not prefs:
            return True  # No preferences set — default to enabled

        category_to_field = {
            NotificationCategory.leave: prefs.leave_notifications,
            NotificationCategory.policy: prefs.policy_notifications,
            NotificationCategory.escalation: prefs.escalation_notifications,
            NotificationCategory.document: prefs.document_notifications,
            NotificationCategory.general: True,
        }
        return category_to_field.get(category, True)

    async def _is_category_enabled(
        self,
        employee_id: uuid.UUID,
        category: NotificationCategory,
    ) -> bool:
        """Check if the employee has enabled notifications for this category."""
        result = await self.db.execute(
            select(NotificationPreference).where(
                NotificationPreference.tenant_id == self.tenant_id,
                NotificationPreference.employee_id == employee_id,
            )
        )
        prefs = result.scalar_one_or_none()
        return self._check_category_from_prefs(prefs, category)
