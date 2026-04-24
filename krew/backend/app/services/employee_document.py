"""Employee document service — typed HR document management with expiry and verification."""
import logging
import uuid
from datetime import datetime, date, timezone

from fastapi import UploadFile, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.employee import Employee
from app.models.employee_document import (
    EmployeeDocument,
    DocumentType,
    VerificationStatus,
    EXPIRING_DOCUMENT_TYPES,
)
from sqlalchemy import func as sa_func

from app.models.document import DocumentCategory
from app.services.document import DocumentService

logger = logging.getLogger(__name__)

MAX_DOCUMENTS_PER_EMPLOYEE = 50


class EmployeeDocumentService:
    """Manages typed HR documents for employees."""

    def __init__(self, db: AsyncSession, tenant_id: uuid.UUID):
        self.db = db
        self.tenant_id = tenant_id

    async def upload(
        self,
        file: UploadFile,
        employee_id: uuid.UUID,
        uploaded_by: uuid.UUID,
        document_type: str | DocumentType,
        uploaded_via: str = "web",
        expires_at: date | None = None,
        label: str | None = None,
        label_ar: str | None = None,
        notes: str | None = None,
    ) -> EmployeeDocument:
        """Upload and register an HR document for an employee.

        Validates document type and expiry requirements, uploads the file
        via DocumentService, then creates the EmployeeDocument metadata record.
        """
        # Parse document type
        if isinstance(document_type, str):
            try:
                document_type = DocumentType(document_type)
            except ValueError:
                valid = ", ".join(t.value for t in DocumentType)
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid document type. Valid types: {valid}",
                )

        # Verify employee belongs to this tenant
        emp_result = await self.db.execute(
            select(Employee).where(
                Employee.id == employee_id,
                Employee.tenant_id == self.tenant_id,
            )
        )
        if not emp_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Employee not found.")

        # Check per-employee document count limit
        count_result = await self.db.execute(
            select(sa_func.count(EmployeeDocument.id)).where(
                EmployeeDocument.tenant_id == self.tenant_id,
                EmployeeDocument.employee_id == employee_id,
                EmployeeDocument.is_deleted.is_(False),
            )
        )
        if count_result.scalar_one() >= MAX_DOCUMENTS_PER_EMPLOYEE:
            raise HTTPException(
                status_code=400,
                detail=f"Maximum of {MAX_DOCUMENTS_PER_EMPLOYEE} documents per employee reached.",
            )

        # Expiring document types require expires_at
        if document_type in EXPIRING_DOCUMENT_TYPES and not expires_at:
            raise HTTPException(
                status_code=400,
                detail=f"Document type '{document_type.value}' requires an expiry date.",
            )

        # Upload the actual file via the generic DocumentService
        doc_svc = DocumentService(self.db, self.tenant_id)
        document = await doc_svc.upload(
            file=file,
            uploaded_by=uploaded_by,
            category=DocumentCategory.employee_document,
            resource_type="employee_document",
            resource_id=employee_id,
        )

        # Create the typed EmployeeDocument record
        emp_doc = EmployeeDocument(
            tenant_id=self.tenant_id,
            employee_id=employee_id,
            document_type=document_type,
            label=label,
            label_ar=label_ar,
            notes=notes,
            document_id=document.id,
            original_filename=document.original_filename,
            file_size=document.file_size,
            mime_type=document.content_type,
            expires_at=expires_at,
            uploaded_by=uploaded_by,
            uploaded_via=uploaded_via,
        )
        self.db.add(emp_doc)
        await self.db.flush()

        logger.info(
            "Employee document uploaded: type=%s employee=%s file=%s",
            document_type.value, employee_id, document.original_filename,
        )
        return emp_doc

    async def verify(
        self,
        doc_id: uuid.UUID,
        admin_id: uuid.UUID,
        new_status: str | VerificationStatus,
        rejection_reason: str | None = None,
    ) -> EmployeeDocument:
        """Verify or reject a pending employee document."""
        if isinstance(new_status, str):
            try:
                new_status = VerificationStatus(new_status)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="Status must be 'verified' or 'rejected'.",
                )

        if new_status not in (VerificationStatus.verified, VerificationStatus.rejected):
            raise HTTPException(
                status_code=400,
                detail="Status must be 'verified' or 'rejected'.",
            )

        doc = await self.get_document(doc_id)

        # Segregation of duties: uploader cannot verify their own document
        if doc.uploaded_by == admin_id:
            raise HTTPException(
                status_code=403,
                detail="Cannot verify a document you uploaded. A different admin must verify it.",
            )

        if doc.verification_status != VerificationStatus.pending:
            raise HTTPException(
                status_code=409,
                detail=f"Document is already '{doc.verification_status.value}'. Only pending documents can be verified.",
            )

        doc.verification_status = new_status
        doc.verified_by = admin_id
        doc.verified_at = datetime.now(timezone.utc)

        if new_status == VerificationStatus.rejected:
            if not rejection_reason:
                raise HTTPException(
                    status_code=400,
                    detail="Rejection reason is required when rejecting a document.",
                )
            doc.rejection_reason = rejection_reason

        await self.db.flush()
        logger.info(
            "Employee document %s: id=%s by_admin=%s",
            new_status.value, doc_id, admin_id,
        )
        return doc

    async def list_expiring(
        self,
        days: int = 30,
        document_type: str | DocumentType | None = None,
    ) -> list[tuple[EmployeeDocument, Employee]]:
        """List documents expiring within N days, joined with Employee."""
        cutoff = date.today()
        from datetime import timedelta
        deadline = cutoff + timedelta(days=days)

        query = (
            select(EmployeeDocument, Employee)
            .join(Employee, EmployeeDocument.employee_id == Employee.id)
            .where(
                EmployeeDocument.tenant_id == self.tenant_id,
                EmployeeDocument.is_deleted.is_(False),
                EmployeeDocument.expires_at.isnot(None),
                EmployeeDocument.expires_at >= cutoff,
                EmployeeDocument.expires_at <= deadline,
            )
            .order_by(EmployeeDocument.expires_at.asc())
        )

        if document_type:
            if isinstance(document_type, str):
                document_type = DocumentType(document_type)
            query = query.where(EmployeeDocument.document_type == document_type)

        result = await self.db.execute(query)
        return list(result.all())

    async def list_for_employee(
        self,
        employee_id: uuid.UUID,
        document_type: str | DocumentType | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[EmployeeDocument]:
        """List non-deleted documents for an employee with pagination."""
        query = (
            select(EmployeeDocument)
            .where(
                EmployeeDocument.tenant_id == self.tenant_id,
                EmployeeDocument.employee_id == employee_id,
                EmployeeDocument.is_deleted.is_(False),
            )
            .order_by(EmployeeDocument.created_at.desc())
            .offset(offset)
            .limit(limit)
        )

        if document_type:
            if isinstance(document_type, str):
                document_type = DocumentType(document_type)
            query = query.where(EmployeeDocument.document_type == document_type)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_document(self, doc_id: uuid.UUID) -> EmployeeDocument:
        """Get a single employee document by ID, tenant-scoped."""
        result = await self.db.execute(
            select(EmployeeDocument).where(
                EmployeeDocument.id == doc_id,
                EmployeeDocument.tenant_id == self.tenant_id,
                EmployeeDocument.is_deleted.is_(False),
            )
        )
        doc = result.scalar_one_or_none()
        if not doc:
            raise HTTPException(status_code=404, detail="Employee document not found.")
        return doc

    async def soft_delete(self, doc_id: uuid.UUID) -> EmployeeDocument:
        """Soft-delete an employee document."""
        doc = await self.get_document(doc_id)
        doc.is_deleted = True
        doc.deleted_at = datetime.now(timezone.utc)
        await self.db.flush()
        logger.info("Employee document soft-deleted: id=%s", doc_id)
        return doc
