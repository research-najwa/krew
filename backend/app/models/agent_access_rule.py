"""Agent access rules -- controls which employees can interact with which agents."""
import uuid
import enum
from datetime import datetime, timezone

from sqlalchemy import String, DateTime, Boolean, ForeignKey, Index
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AccessType(str, enum.Enum):
    """How access is determined for this agent."""
    all = "all"                     # Every employee in the tenant
    role_based = "role_based"       # Check employee's job role against allowed_roles
    department = "department"       # Check employee's department against allowed_departments
    specific_users = "specific_users"  # Whitelist of specific employee UUIDs


class AgentAccessRule(Base):
    """Defines who can access a specific agent within a tenant.

    One row per (tenant_id, agent_name) pair. If no row exists for an agent,
    access is PERMITTED by default (permissive default for new/unknown agents).
    """
    __tablename__ = "agent_access_rules"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), index=True)
    agent_name: Mapped[str] = mapped_column(String(100))
    # agent_name values: "deema", "ahmad", "mohammad", "waleed", "yara", "dept:{uuid}"

    access_type: Mapped[AccessType] = mapped_column(
        SAEnum(AccessType, name="accesstype", create_constraint=False),
        default=AccessType.all,
    )

    # JSONB arrays -- only the relevant field is checked based on access_type.
    # Using JSONB instead of association tables for simplicity: the number of roles
    # and departments is small (< 50 per tenant), and JSONB supports gin indexing.
    allowed_roles: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # Values: "employee", "manager", "department_head", "hr_specialist",
    #         "hr_manager", "hr_admin", "it_admin", "c_suite", "hiring_manager"

    allowed_departments: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # Values: list of department UUID strings

    allowed_users: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # Values: list of employee UUID strings

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

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

    __table_args__ = (
        Index("ix_agent_access_tenant_agent", "tenant_id", "agent_name", unique=True),
    )
