"""HR Policy CRUD — draft/publish/archive lifecycle with versioning and acknowledgments."""
import uuid
import enum
from datetime import datetime, date, timezone

from sqlalchemy import (
    String, DateTime, Date, Integer, Text, ForeignKey, Boolean,
    Index, UniqueConstraint, Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class PolicyCategory(str, enum.Enum):
    leave = "leave"
    attendance = "attendance"
    conduct = "conduct"
    compensation = "compensation"
    benefits = "benefits"
    safety = "safety"
    general = "general"


class PolicyStatus(str, enum.Enum):
    draft = "draft"
    published = "published"
    archived = "archived"


class HRPolicy(Base):
    """A managed HR policy with draft/publish/archive lifecycle."""
    __tablename__ = "hr_policies"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))

    title: Mapped[str] = mapped_column(String(500))
    title_ar: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content: Mapped[str] = mapped_column(Text)
    content_ar: Mapped[str | None] = mapped_column(Text, nullable=True)

    category: Mapped[PolicyCategory] = mapped_column(SAEnum(PolicyCategory))
    status: Mapped[PolicyStatus] = mapped_column(
        SAEnum(PolicyStatus), default=PolicyStatus.draft
    )

    version: Mapped[int] = mapped_column(Integer, default=1)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("hr_policies.id"), nullable=True
    )

    effective_date: Mapped[date] = mapped_column(Date)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("employees.id"), nullable=True
    )

    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index("ix_hr_policies_tenant_category_status", "tenant_id", "category", "status"),
        Index("ix_hr_policies_tenant_parent", "tenant_id", "parent_id"),
    )


class PolicyAcknowledgment(Base):
    """Record of an employee acknowledging a policy."""
    __tablename__ = "policy_acknowledgments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    policy_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("hr_policies.id"))
    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id"))
    acknowledged_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)

    __table_args__ = (
        UniqueConstraint("policy_id", "employee_id", name="uq_policy_ack_policy_employee"),
    )
