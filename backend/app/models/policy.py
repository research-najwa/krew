"""Policy storage with vector embeddings for RAG — this is a key moat."""
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector
from app.database import Base


class Policy(Base):
    """A company policy document (e.g., Employee Handbook, PTO Policy)."""
    __tablename__ = "policies"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    title: Mapped[str] = mapped_column(String(500))
    category: Mapped[str] = mapped_column(String(100))  # leave, benefits, conduct, compliance...
    source_filename: Mapped[str | None] = mapped_column(String(500))
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(default=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    tenant: Mapped["Tenant"] = relationship(back_populates="policies")
    chunks: Mapped[list["PolicyChunk"]] = relationship(back_populates="policy")


class PolicyChunk(Base):
    """Chunked and embedded policy text for vector retrieval."""
    __tablename__ = "policy_chunks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    policy_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("policies.id"))
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    content_normalized: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding = mapped_column(Vector(1536))  # OpenAI text-embedding-3-small dimensions
    token_count: Mapped[int] = mapped_column(Integer, default=0)

    policy: Mapped["Policy"] = relationship(back_populates="chunks")
