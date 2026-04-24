"""Employee HR documents — typed document layer with expiry tracking and verification."""
import uuid
import enum
from datetime import datetime, date, timezone

from sqlalchemy import (
    String, Text, Integer, DateTime, Date, ForeignKey, Boolean,
    Index, Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class DocumentType(str, enum.Enum):
    national_id = "national_id"
    iqama = "iqama"
    contract = "contract"
    gosi_cert = "gosi_cert"
    medical_insurance = "medical_insurance"
    education_cert = "education_cert"
    passport = "passport"
    bank_letter = "bank_letter"
    driving_license = "driving_license"
    other = "other"


EXPIRING_DOCUMENT_TYPES = {
    DocumentType.iqama,
    DocumentType.medical_insurance,
    DocumentType.passport,
    DocumentType.driving_license,
}


class VerificationStatus(str, enum.Enum):
    pending = "pending"
    verified = "verified"
    rejected = "rejected"


class EmployeeDocument(Base):
    """An HR document belonging to an employee, linked to an underlying file (Document)."""
    __tablename__ = "employee_documents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id"))

    document_type: Mapped[DocumentType] = mapped_column(SAEnum(DocumentType))
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    label_ar: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Link to the actual file stored via DocumentService
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"))

    original_filename: Mapped[str] = mapped_column(String(500))
    file_size: Mapped[int] = mapped_column(Integer)
    mime_type: Mapped[str] = mapped_column(String(100))

    # Expiry tracking
    expires_at: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Verification workflow
    verification_status: Mapped[VerificationStatus] = mapped_column(
        SAEnum(VerificationStatus), default=VerificationStatus.pending
    )
    verified_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("admin_users.id"), nullable=True
    )
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Audit
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id"))
    uploaded_via: Mapped[str] = mapped_column(String(20), default="web")

    # Soft-delete
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_empdocs_tenant_employee", "tenant_id", "employee_id"),
        Index("ix_empdocs_tenant_expires", "tenant_id", "expires_at"),
        Index("ix_empdocs_tenant_doctype", "tenant_id", "document_type"),
    )
