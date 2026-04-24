"""Conversation and message log — every interaction is stored for learning."""
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, Text, Float, Boolean, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

import enum


class ConversationStatus(str, enum.Enum):
    active = "active"
    resolved = "resolved"
    escalated = "escalated"


class Conversation(Base):
    """A conversation thread between an employee and a Krew agent."""
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id"))
    agent_name: Mapped[str] = mapped_column(String(50))  # deema, waleed, mohammad...
    channel: Mapped[str] = mapped_column(String(20))  # whatsapp, slack, teams, email
    status: Mapped[ConversationStatus] = mapped_column(
        SAEnum(ConversationStatus), default=ConversationStatus.active
    )
    topic: Mapped[str | None] = mapped_column(String(255))  # auto-detected topic
    language: Mapped[str] = mapped_column(String(5), default="ar")
    satisfaction_score: Mapped[float | None] = mapped_column(Float)
    resolved_automatically: Mapped[bool] = mapped_column(Boolean, default=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime)

    tenant: Mapped["Tenant"] = relationship(back_populates="conversations")
    employee: Mapped["Employee"] = relationship(back_populates="conversations")
    messages: Mapped[list["Message"]] = relationship(back_populates="conversation")


class Message(Base):
    """Individual message in a conversation."""
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id"))
    role: Mapped[str] = mapped_column(String(20))  # employee, agent, system
    content: Mapped[str] = mapped_column(Text)
    channel: Mapped[str] = mapped_column(String(20))
    language: Mapped[str] = mapped_column(String(5), default="ar")
    tool_calls: Mapped[str | None] = mapped_column(Text)  # JSON of tools the agent called
    tokens_used: Mapped[int | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")
