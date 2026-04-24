"""Notification system — in-app notifications and user preferences."""
import uuid
import enum
from datetime import datetime, timezone

from sqlalchemy import String, Text, Integer, DateTime, ForeignKey, Boolean, Index, UniqueConstraint, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class NotificationCategory(str, enum.Enum):
    leave = "leave"
    policy = "policy"
    escalation = "escalation"
    document = "document"
    general = "general"
    onboarding = "onboarding"


class NotificationPriority(str, enum.Enum):
    low = "low"
    normal = "normal"
    high = "high"


class NotificationChannel(str, enum.Enum):
    in_app = "in_app"
    email = "email"
    whatsapp = "whatsapp"
    slack = "slack"


class Notification(Base):
    """In-app notification delivered to an employee."""
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id"))

    title: Mapped[str] = mapped_column(String(500))
    title_ar: Mapped[str | None] = mapped_column(String(500), nullable=True)
    body: Mapped[str] = mapped_column(String(2000))
    body_ar: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    category: Mapped[NotificationCategory] = mapped_column(
        SAEnum(NotificationCategory), default=NotificationCategory.general
    )
    priority: Mapped[NotificationPriority] = mapped_column(
        SAEnum(NotificationPriority), default=NotificationPriority.normal
    )
    channel: Mapped[NotificationChannel] = mapped_column(
        SAEnum(NotificationChannel), default=NotificationChannel.in_app
    )

    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Link to related resource (e.g., leave_request, policy)
    resource_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    resource_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)

    # Delivery tracking
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivery_status: Mapped[str] = mapped_column(String(20), server_default="pending")
    delivery_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivery_attempts: Mapped[int] = mapped_column(Integer, server_default="0")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.utcnow())

    __table_args__ = (
        Index("ix_notifications_tenant_employee_read", "tenant_id", "employee_id", "is_read"),
        Index("ix_notifications_tenant_created", "tenant_id", "created_at"),
    )


class NotificationPreference(Base):
    """Per-employee notification preferences."""
    __tablename__ = "notification_preferences"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id"))

    leave_notifications: Mapped[bool] = mapped_column(Boolean, default=True)
    policy_notifications: Mapped[bool] = mapped_column(Boolean, default=True)
    escalation_notifications: Mapped[bool] = mapped_column(Boolean, default=True)
    document_notifications: Mapped[bool] = mapped_column(Boolean, default=True)

    onboarding_notifications: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "employee_id", name="uq_notification_prefs_tenant_employee"),
    )
