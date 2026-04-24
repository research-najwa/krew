"""Onboarding checklist templates and employee assignments."""
import uuid
import enum
from datetime import datetime, timezone

from sqlalchemy import (
    String, DateTime, Integer, Boolean, ForeignKey, Text,
    UniqueConstraint, Index, Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class OnboardingStepType(str, enum.Enum):
    manual = "manual"          # HR marks complete
    automatic = "automatic"    # System detects completion (e.g., policy acknowledged)
    agent_assisted = "agent_assisted"  # Deema/Waleed guides the employee


class OnboardingAssignmentStatus(str, enum.Enum):
    in_progress = "in_progress"
    completed = "completed"
    cancelled = "cancelled"


class OnboardingStepStatus(str, enum.Enum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"
    skipped = "skipped"


class OnboardingTemplate(Base):
    """Tenant-configurable onboarding checklist template."""
    __tablename__ = "onboarding_templates"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_onboarding_template_tenant_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    name: Mapped[str] = mapped_column(String(255))
    name_ar: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    # If is_default=True, auto-assigned to new hires when no specific template is specified

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    steps: Mapped[list["OnboardingTemplateStep"]] = relationship(
        back_populates="template", order_by="OnboardingTemplateStep.order"
    )
    tenant = relationship("Tenant")


class OnboardingTemplateStep(Base):
    """A step within an onboarding template (the blueprint)."""
    __tablename__ = "onboarding_template_steps"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    template_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("onboarding_templates.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(500))
    name_ar: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    description_ar: Mapped[str | None] = mapped_column(Text, nullable=True)
    step_type: Mapped[OnboardingStepType] = mapped_column(
        SAEnum(OnboardingStepType), default=OnboardingStepType.manual
    )
    order: Mapped[int] = mapped_column(Integer)
    due_days_after_hire: Mapped[int] = mapped_column(Integer, default=7)
    # e.g., 3 means due 3 days after hire_date
    is_required: Mapped[bool] = mapped_column(Boolean, default=True)

    # For automatic steps: what triggers completion
    auto_trigger: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # e.g., "policy_acknowledged", "document_uploaded:employment_contract"

    template: Mapped["OnboardingTemplate"] = relationship(back_populates="steps")


class OnboardingAssignment(Base):
    """An onboarding instance assigned to a specific employee."""
    __tablename__ = "onboarding_assignments"
    __table_args__ = (
        UniqueConstraint("employee_id", "template_id", name="uq_onboarding_assignment_emp_template"),
        Index("ix_onboarding_assignment_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id"))
    template_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("onboarding_templates.id"))

    status: Mapped[OnboardingAssignmentStatus] = mapped_column(
        SAEnum(OnboardingAssignmentStatus), default=OnboardingAssignmentStatus.in_progress
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    step_statuses: Mapped[list["OnboardingStepAssignment"]] = relationship(
        back_populates="assignment", order_by="OnboardingStepAssignment.order"
    )
    employee = relationship("Employee")
    template = relationship("OnboardingTemplate")


class OnboardingStepAssignment(Base):
    """Status of a single onboarding step for a specific employee."""
    __tablename__ = "onboarding_step_assignments"
    __table_args__ = (
        UniqueConstraint(
            "assignment_id", "template_step_id",
            name="uq_onboarding_step_assignment_unique"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    assignment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("onboarding_assignments.id", ondelete="CASCADE")
    )
    template_step_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("onboarding_template_steps.id")
    )

    status: Mapped[OnboardingStepStatus] = mapped_column(
        SAEnum(OnboardingStepStatus), default=OnboardingStepStatus.pending
    )
    order: Mapped[int] = mapped_column(Integer)
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # "hr:<admin_user_id>", "system:policy_acknowledged", "agent:deema"
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    assignment: Mapped["OnboardingAssignment"] = relationship(back_populates="step_statuses")
    template_step: Mapped["OnboardingTemplateStep"] = relationship()
