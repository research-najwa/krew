"""Knowledge sources and chunks — flexible document storage with pgvector embeddings."""
import uuid
import enum
from datetime import datetime, timezone

from sqlalchemy import (
    String, DateTime, Integer, Text, Boolean, ForeignKey,
    Index, UniqueConstraint, Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector
from app.database import Base


class SourceType(str, enum.Enum):
    policy = "policy"
    document = "document"
    markdown = "markdown"
    custom_text = "custom_text"
    url = "url"


class EmbeddingStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    complete = "complete"
    failed = "failed"


class KnowledgeSource(Base):
    """A knowledge document that can be chunked, embedded, and assigned to agents."""
    __tablename__ = "knowledge_sources"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    title_ar: Mapped[str | None] = mapped_column(String(500), nullable=True)

    source_type: Mapped[SourceType] = mapped_column(SAEnum(SourceType), nullable=False)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)

    content_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    url: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    source_policy_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("hr_policies.id"), nullable=True
    )

    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    embedding_status: Mapped[EmbeddingStatus] = mapped_column(
        SAEnum(EmbeddingStatus), default=EmbeddingStatus.pending
    )

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("employees.id"), nullable=True
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
    chunks: Mapped[list["KnowledgeChunk"]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )
    assignments: Mapped[list["AgentKnowledgeAssignment"]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_knowledge_sources_tenant_type", "tenant_id", "source_type"),
        Index("ix_knowledge_sources_tenant_active", "tenant_id", "is_active"),
    )


class KnowledgeChunk(Base):
    """Chunked and embedded text from a knowledge source."""
    __tablename__ = "knowledge_chunks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_sources.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id"), nullable=False
    )  # Denormalized for query performance

    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    embedding = mapped_column(Vector(1536), nullable=True)  # OpenAI text-embedding-3-small

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    source: Mapped["KnowledgeSource"] = relationship(back_populates="chunks")

    __table_args__ = (
        Index("ix_knowledge_chunks_source", "source_id"),
        Index("ix_knowledge_chunks_tenant", "tenant_id"),
    )


class AgentKnowledgeAssignment(Base):
    """Many-to-many: which knowledge sources are assigned to which deployed agents."""
    __tablename__ = "agent_knowledge_assignments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("deployed_agents.id"), nullable=False
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_sources.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id"), nullable=False
    )

    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    assigned_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("employees.id"), nullable=True
    )

    # Relationships
    source: Mapped["KnowledgeSource"] = relationship(back_populates="assignments")

    __table_args__ = (
        UniqueConstraint("agent_id", "source_id", name="uq_agent_knowledge_agent_source"),
        Index("ix_agent_knowledge_tenant_agent", "tenant_id", "agent_id"),
    )
