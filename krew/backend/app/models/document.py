"""Document/attachment tracking — file metadata storage."""
import uuid
import enum
from datetime import datetime, timezone

from sqlalchemy import String, DateTime, Integer, ForeignKey, Boolean, Index, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class DocumentCategory(str, enum.Enum):
    leave_attachment = "leave_attachment"
    employee_document = "employee_document"
    policy_document = "policy_document"


class Document(Base):
    """Metadata record for an uploaded file."""
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id"))

    filename: Mapped[str] = mapped_column(String(500))
    original_filename: Mapped[str] = mapped_column(String(500))
    content_type: Mapped[str] = mapped_column(String(100))
    file_size: Mapped[int] = mapped_column(Integer)
    storage_path: Mapped[str] = mapped_column(String(1000))

    category: Mapped[DocumentCategory] = mapped_column(SAEnum(DocumentCategory))

    # Link to related resource
    resource_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    resource_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)

    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index("ix_documents_tenant_resource", "tenant_id", "resource_type", "resource_id"),
        Index("ix_documents_tenant_uploader", "tenant_id", "uploaded_by"),
    )
