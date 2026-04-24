"""Document service — file upload, metadata storage, and retrieval."""
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

import aiofiles
import aiofiles.os
from fastapi import UploadFile, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from datetime import timedelta

from app.config import get_settings
from app.models.document import Document, DocumentCategory

logger = logging.getLogger(__name__)

ALLOWED_TYPES = {"application/pdf", "image/jpeg", "image/png", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB

# Map content types to file extensions
CONTENT_TYPE_EXT = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
}

# Magic byte signatures for content-type verification (Finding 2)
MAGIC_BYTES = {
    "application/pdf": b"%PDF",
    "image/jpeg": b"\xff\xd8\xff",
    "image/png": b"\x89PNG",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": b"PK\x03\x04",
}

# Control character pattern for filename sanitization (Finding 8)
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f-\x9f]")


def _sanitize_filename(raw: str | None) -> str:
    """Sanitize an upload filename: strip path traversal, control chars, limit length."""
    name = Path(raw or "unknown").name  # strips ../ and directory components
    name = _CONTROL_CHARS.sub("", name)  # strip control characters
    name = name.strip(". ")  # strip leading/trailing dots and spaces
    if not name:
        name = "unknown"
    return name[:255]


class DocumentService:
    """Handles file upload, metadata tracking, and retrieval."""

    def __init__(self, db: AsyncSession, tenant_id: uuid.UUID):
        self.db = db
        self.tenant_id = tenant_id

    async def upload(
        self,
        file: UploadFile,
        uploaded_by: uuid.UUID,
        category: str | DocumentCategory,
        resource_type: str | None = None,
        resource_id: uuid.UUID | None = None,
        description: str | None = None,
        max_file_size: int | None = None,
    ) -> Document:
        """Upload a file: validate, store on disk, and create metadata record."""
        if isinstance(category, str):
            try:
                category = DocumentCategory(category)
            except ValueError:
                valid = ", ".join(c.value for c in DocumentCategory)
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid document category. Valid: {valid}",
                )

        # Validate content type
        content_type = file.content_type or ""
        if content_type not in ALLOWED_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"File type '{content_type}' not allowed. Allowed: PDF, JPEG, PNG, DOCX.",
            )

        # Read file content and validate size
        file_content = await file.read()
        file_size = len(file_content)
        effective_max = max_file_size if max_file_size is not None else MAX_FILE_SIZE
        if file_size > effective_max:
            raise HTTPException(
                status_code=400,
                detail=f"File size ({file_size} bytes) exceeds maximum of {effective_max} bytes.",
            )
        if file_size == 0:
            raise HTTPException(status_code=400, detail="File is empty.")

        # Finding 2: Verify magic bytes match declared content type
        expected_magic = MAGIC_BYTES.get(content_type)
        if expected_magic and not file_content[:len(expected_magic)] == expected_magic:
            raise HTTPException(
                status_code=400,
                detail="File content does not match declared content type.",
            )

        # Finding 8: Sanitize original filename
        safe_original = _sanitize_filename(file.filename)

        # Generate storage path — use settings.upload_dir (Finding 6)
        ext = CONTENT_TYPE_EXT.get(content_type, "")
        file_uuid = str(uuid.uuid4())
        filename = f"{file_uuid}{ext}"
        storage_dir = Path(get_settings().upload_dir) / str(self.tenant_id) / category.value
        await aiofiles.os.makedirs(str(storage_dir), exist_ok=True)
        storage_path = str(storage_dir / filename)

        # Finding 1: Flush DB record first, then write file.
        # If file write fails, the transaction rolls back automatically.
        document = Document(
            tenant_id=self.tenant_id,
            uploaded_by=uploaded_by,
            filename=filename,
            original_filename=safe_original,
            content_type=content_type,
            file_size=file_size,
            storage_path=storage_path,
            category=category,
            resource_type=resource_type,
            resource_id=resource_id,
            description=description,
        )
        self.db.add(document)
        await self.db.flush()

        # Finding 1: Async file write (non-blocking)
        async with aiofiles.open(storage_path, "wb") as f:
            await f.write(file_content)

        logger.info(
            "File uploaded: path=%s size=%d type=%s by=%s",
            storage_path, file_size, content_type, uploaded_by,
        )

        return document

    async def get_document(
        self,
        document_id: uuid.UUID,
        employee_id: uuid.UUID | None = None,
    ) -> Document:
        """Fetch document metadata. Raises HTTPException if not found or deleted."""
        query = select(Document).where(
            Document.id == document_id,
            Document.tenant_id == self.tenant_id,
            Document.is_deleted.is_(False),  # Finding 15
        )
        result = await self.db.execute(query)
        doc = result.scalar_one_or_none()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found.")
        return doc

    async def list_documents(
        self,
        resource_type: str | None = None,
        resource_id: uuid.UUID | None = None,
        category: str | None = None,
        limit: int = 50,
        offset: int = 0,
        uploaded_by: uuid.UUID | None = None,
    ) -> list[Document]:
        """List documents with optional filters, tenant-scoped.

        If uploaded_by is provided, only returns documents owned by that employee.
        """
        query = (
            select(Document)
            .where(
                Document.tenant_id == self.tenant_id,
                Document.is_deleted.is_(False),  # Finding 15
            )
            .order_by(Document.created_at.desc())
            .offset(offset)
            .limit(limit)
        )

        # Finding 2: Ownership filter for non-HR users
        if uploaded_by:
            query = query.where(Document.uploaded_by == uploaded_by)
        if resource_type:
            query = query.where(Document.resource_type == resource_type)
        if resource_id:
            query = query.where(Document.resource_id == resource_id)
        if category:
            try:
                cat_enum = DocumentCategory(category)
                query = query.where(Document.category == cat_enum)
            except ValueError:
                pass  # Ignore invalid category filter

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def soft_delete(
        self,
        document_id: uuid.UUID,
        deleted_by: uuid.UUID,
        owner_employee_id: uuid.UUID | None = None,
    ) -> Document:
        """Soft-delete a document. Returns the updated document.

        If owner_employee_id is provided, enforces ownership check (Finding 7).
        """
        doc = await self.get_document(document_id)

        if owner_employee_id is not None and doc.uploaded_by != owner_employee_id:
            raise HTTPException(
                status_code=403,
                detail="You can only delete your own documents.",
            )

        doc.is_deleted = True
        doc.deleted_at = datetime.now(timezone.utc)  # Finding 21
        await self.db.flush()
        logger.info("Document soft-deleted: id=%s by=%s", document_id, deleted_by)
        return doc

    @staticmethod
    async def purge_deleted(db: AsyncSession, retention_days: int = 30) -> int:
        """Purge soft-deleted files older than retention_days.

        Deletes files from disk and hard-deletes DB records.
        Returns the number of records purged.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        result = await db.execute(
            select(Document).where(
                Document.is_deleted.is_(True),
                Document.deleted_at.isnot(None),
                Document.deleted_at < cutoff,
            )
        )
        expired_docs = list(result.scalars().all())

        purged = 0
        for doc in expired_docs:
            # Delete file from disk (best-effort)
            try:
                if await aiofiles.os.path.exists(doc.storage_path):
                    await aiofiles.os.remove(doc.storage_path)
            except OSError as e:
                logger.warning("Failed to delete file %s: %s", doc.storage_path, e)

            await db.delete(doc)
            purged += 1

        if purged:
            await db.flush()
            logger.info("Purged %d soft-deleted documents older than %d days", purged, retention_days)

        return purged

    async def get_file_path(self, document_id: uuid.UUID) -> str:
        """Return the storage path for streaming a file."""
        doc = await self.get_document(document_id)
        # Finding 1: Use async path existence check
        if not await aiofiles.os.path.exists(doc.storage_path):
            raise HTTPException(status_code=404, detail="File not found on disk.")
        return doc.storage_path
