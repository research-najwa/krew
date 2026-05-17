"""Direct messaging between employees — human-to-human chat.

Supports: plain messages, @agent mentions (inline AI responses),
replies/quotes, emoji reactions, pins, attachments, and voice notes.
"""
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    String, DateTime, ForeignKey, Text, Boolean, Index,
    CheckConstraint, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class DmMessageType(str, enum.Enum):
    human = "human"       # Regular message from an employee
    agent = "agent"       # Response from an AI agent (@mention)
    system = "system"     # System messages (pinned, etc.)


class DirectConversation(Base):
    """A 1-on-1 DM thread between two employees.

    Invariant: participant_a_id < participant_b_id (lexicographic UUID order)
    so the pair is always stored in a canonical form and the unique constraint
    prevents duplicates.
    """
    __tablename__ = "direct_conversations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    participant_a_id: Mapped[uuid.UUID] = mapped_column()
    participant_b_id: Mapped[uuid.UUID] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    read_cursor_a: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    read_cursor_b: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Pinned message IDs (list of message UUIDs)
    pinned_message_ids: Mapped[list | None] = mapped_column(JSONB, default=None)

    tenant: Mapped["Tenant"] = relationship()
    participant_a: Mapped["Employee"] = relationship(
        foreign_keys=[participant_a_id],
        primaryjoin="DirectConversation.participant_a_id == Employee.id",
        viewonly=True,
    )
    participant_b: Mapped["Employee"] = relationship(
        foreign_keys=[participant_b_id],
        primaryjoin="DirectConversation.participant_b_id == Employee.id",
        viewonly=True,
    )
    messages: Mapped[list["DirectMessage"]] = relationship(
        back_populates="conversation", order_by="DirectMessage.created_at"
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "participant_a_id", "participant_b_id",
                         name="uq_dm_conv_pair"),
        CheckConstraint("participant_a_id < participant_b_id",
                        name="ck_dm_conv_ordered_pair"),
        Index("ix_dm_conv_tenant_participant_a", "tenant_id", "participant_a_id"),
        Index("ix_dm_conv_tenant_participant_b", "tenant_id", "participant_b_id"),
    )


class DirectMessage(Base):
    """A single message in a direct conversation."""
    __tablename__ = "direct_messages"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("direct_conversations.id", ondelete="CASCADE")
    )
    sender_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id"))
    content: Mapped[str] = mapped_column(Text)
    is_edited: Mapped[bool] = mapped_column(Boolean, default=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Message type: human (default), agent (@mention response), system
    message_type: Mapped[str] = mapped_column(
        String(20), default=DmMessageType.human.value
    )
    # Agent name when message_type == agent (e.g. "deema")
    agent_name: Mapped[str | None] = mapped_column(String(100))

    # Reply/quote: points to the message being replied to
    reply_to_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("direct_messages.id", ondelete="SET NULL")
    )

    # Emoji reactions: {"👍": ["emp-uuid-1", "emp-uuid-2"], "❤️": ["emp-uuid-3"]}
    reactions: Mapped[dict | None] = mapped_column(JSONB, default=None)

    # Attachments: [{"type": "file"|"image"|"voice", "url": "...", "name": "...", "size": 1234, "duration_sec": 15}]
    attachments: Mapped[list | None] = mapped_column(JSONB, default=None)

    conversation: Mapped["DirectConversation"] = relationship(back_populates="messages")
    sender: Mapped["Employee"] = relationship(foreign_keys=[sender_id])
    reply_to: Mapped["DirectMessage | None"] = relationship(
        remote_side=[id], foreign_keys=[reply_to_id]
    )

    __table_args__ = (
        Index("ix_dm_msg_conv_created", "conversation_id", "created_at"),
    )
