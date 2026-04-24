"""Activity event — append-only feed of agent / employee / system actions."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import String, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ActivityEvent(Base):
    __tablename__ = "activity_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)  # agent | employee | system
    actor_id: Mapped[str] = mapped_column(String(64), nullable=False)
    subject_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"), nullable=True, index=True,
    )
    subject_department_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True,
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(32), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    label_en: Mapped[str] = mapped_column(String(280), nullable=False)
    label_ar: Mapped[str] = mapped_column(String(280), nullable=False)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    sensitivity: Mapped[str] = mapped_column(String(16), nullable=False, default="normal")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True,
    )

    __table_args__ = (
        Index("ix_activity_tenant_created", "tenant_id", "created_at"),
        Index("ix_activity_tenant_subject", "tenant_id", "subject_employee_id"),
        Index("ix_activity_tenant_dept", "tenant_id", "subject_department_id"),
    )
