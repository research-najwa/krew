"""Deployed AI agents — department-level agents created by Sarah."""
import uuid
import enum
from datetime import datetime, timezone

from sqlalchemy import String, Text, DateTime, Integer, Float, ForeignKey, Index
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AgentStatus(str, enum.Enum):
    draft = "draft"
    testing = "testing"
    active = "active"
    paused = "paused"
    archived = "archived"


class DeployedAgent(Base):
    __tablename__ = "deployed_agents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), index=True)
    department_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("departments.id"), index=True)

    # Identity
    name: Mapped[str] = mapped_column(String(100))
    name_ar: Mapped[str | None] = mapped_column(String(100))
    role_title: Mapped[str] = mapped_column(String(255))
    role_title_ar: Mapped[str | None] = mapped_column(String(255))

    # Agent configuration — channel-agnostic, pure logic
    personality: Mapped[str | None] = mapped_column(Text)
    system_prompt: Mapped[str] = mapped_column(Text)
    tools_config: Mapped[dict | None] = mapped_column(JSONB, default=list)
    scope_boundaries: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    escalation_rules: Mapped[dict | None] = mapped_column(JSONB, default=dict)

    # Channel availability — agent works on any enabled channel
    channel_config: Mapped[dict | None] = mapped_column(
        JSONB, default=lambda: {"web": True, "whatsapp": True, "teams": True, "slack": True, "email": False}
    )

    # Lifecycle
    status: Mapped[AgentStatus] = mapped_column(
        SAEnum(AgentStatus, name="agentstatus", create_constraint=False),
        default=AgentStatus.draft,
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("employees.id"))

    # Performance tracking (updated periodically by Sarah's governance tools)
    performance_metrics: Mapped[dict | None] = mapped_column(JSONB, default=dict)

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
    department: Mapped["Department"] = relationship()
    tenant: Mapped["Tenant"] = relationship()

    __table_args__ = (
        Index("ix_deployed_agents_tenant_status", "tenant_id", "status"),
        Index("ix_deployed_agents_tenant_dept", "tenant_id", "department_id"),
    )
