"""Leave policy model — configurable per tenant per leave type."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    String, DateTime, Integer, Boolean, ForeignKey, UniqueConstraint,
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
from app.models.leave import LeaveType


class LeavePolicy(Base):
    """Per-tenant leave policy configuration for each leave type."""
    __tablename__ = "leave_policies"
    __table_args__ = (
        UniqueConstraint("tenant_id", "leave_type", name="uq_leave_policies_tenant_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    leave_type: Mapped[LeaveType] = mapped_column(SAEnum(LeaveType))

    # Entitlement
    default_days_per_year: Mapped[int] = mapped_column(Integer)
    extended_days_per_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tenure_threshold_years: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Request constraints
    min_days_per_request: Mapped[int] = mapped_column(Integer, default=1)
    max_days_per_request: Mapped[int | None] = mapped_column(Integer, nullable=True)
    advance_notice_days: Mapped[int] = mapped_column(Integer, default=0)

    # Attachment requirements
    requires_attachment: Mapped[bool] = mapped_column(Boolean, default=False)
    attachment_after_days: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Auto-approval
    auto_approve: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_approve_max_days: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Approval routing
    requires_manager_approval: Mapped[bool] = mapped_column(Boolean, default=True)
    requires_hr_approval: Mapped[bool] = mapped_column(Boolean, default=False)

    # Probation
    blocked_during_probation: Mapped[bool] = mapped_column(Boolean, default=False)

    # Blackout periods (list of {start_date, end_date, reason})
    blackout_periods: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # Carry-over
    max_carry_over_days: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    tenant = relationship("Tenant")
