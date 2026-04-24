"""Workforce plans — Sarah's department analysis and human:AI ratio recommendations."""
import uuid
import enum
from datetime import datetime, timezone

from sqlalchemy import String, Integer, Float, DateTime, ForeignKey, Index
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class PlanStatus(str, enum.Enum):
    draft = "draft"
    approved = "approved"
    in_progress = "in_progress"
    implemented = "implemented"


class WorkforcePlan(Base):
    __tablename__ = "workforce_plans"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), index=True)
    department_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("departments.id"), index=True)

    # Analysis output
    analysis: Mapped[dict | None] = mapped_column(JSONB)  # task breakdown, scores, rationale

    # Recommended workforce composition
    current_headcount: Mapped[int] = mapped_column(Integer, default=0)
    recommended_humans: Mapped[int] = mapped_column(Integer, default=0)
    recommended_ai_agents: Mapped[int] = mapped_column(Integer, default=0)
    estimated_annual_savings_sar: Mapped[int] = mapped_column(Integer, default=0)

    # Saudization impact
    saudization_before_pct: Mapped[float | None] = mapped_column(Float)
    saudization_after_pct: Mapped[float | None] = mapped_column(Float)

    # Lifecycle
    status: Mapped[PlanStatus] = mapped_column(
        SAEnum(PlanStatus, name="planstatus", create_constraint=False),
        default=PlanStatus.draft,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    department: Mapped["Department"] = relationship()
    tenant: Mapped["Tenant"] = relationship()

    __table_args__ = (
        Index("ix_workforce_plans_tenant_dept", "tenant_id", "department_id"),
    )
