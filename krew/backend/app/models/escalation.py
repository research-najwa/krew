"""Escalation tickets — when agents need human HR intervention."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Text, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

import enum


class EscalationCategory(str, enum.Enum):
    employee_request = "employee_request"
    agent_failure = "agent_failure"
    sensitive_topic = "sensitive_topic"
    policy_gap = "policy_gap"


class EscalationUrgency(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"


class EscalationStatus(str, enum.Enum):
    open = "open"
    assigned = "assigned"
    resolved = "resolved"


class EscalationTicket(Base):
    """An escalation ticket created when an agent cannot resolve an issue."""
    __tablename__ = "escalation_tickets"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("conversations.id"))
    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id"))
    agent_name: Mapped[str] = mapped_column(String(50))
    category: Mapped[EscalationCategory] = mapped_column(SAEnum(EscalationCategory))
    urgency: Mapped[EscalationUrgency] = mapped_column(
        SAEnum(EscalationUrgency), default=EscalationUrgency.medium
    )
    reason: Mapped[str] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    status: Mapped[EscalationStatus] = mapped_column(
        SAEnum(EscalationStatus), default=EscalationStatus.open
    )
    assigned_to: Mapped[str | None] = mapped_column(String(255))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
