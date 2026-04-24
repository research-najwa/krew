"""Document API — upload, list, download, and delete attachments."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.admin_user import AdminUser, AdminRole
from app.auth.dependencies import get_current_user, has_minimum_role, require_role, require_tenant
from app.api.helpers import resolve_employee_id
from app.services.document import DocumentService
from app.security.rate_limiter import _check_rate_limit, _raise_rate_limit

router = APIRouter(prefix="/documents", tags=["documents"])


# -- Response schemas --------------------------------------------------------


class DocumentOut(BaseModel):
    id: str
    filename: str
    original_filename: str
    content_type: str
    file_size: int
    category: str
    resource_type: str | None
    resource_id: str | None
    description: str | None
    created_at: str
    updated_at: str


# -- Helpers -----------------------------------------------------------------


def _doc_to_out(doc) -> DocumentOut:
    return DocumentOut(
        id=str(doc.id),
        filename=doc.filename,
        original_filename=doc.original_filename,
        content_type=doc.content_type,
        file_size=doc.file_size,
        category=doc.category.value,
        resource_type=doc.resource_type,
        resource_id=str(doc.resource_id) if doc.resource_id else None,
        description=doc.description,
        created_at=doc.created_at.isoformat(),
        updated_at=doc.updated_at.isoformat(),
    )


# -- Endpoints ---------------------------------------------------------------


@router.post("/upload", response_model=DocumentOut)
async def upload_document(
    file: UploadFile = File(...),
    category: str = Form(...),
    resource_type: str | None = Form(None),
    resource_id: str | None = Form(None),
    description: str | None = Form(None),
    current_user: AdminUser = Depends(get_current_user),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Upload a file (PDF, JPEG, PNG). Max 5 MB. Rate limited: 10 uploads/hour."""
    employee_id = await resolve_employee_id(current_user, tenant_id, db)

    # Finding 3: Per-employee upload rate limit — 10 uploads per hour
    rate_key = f"rl:upload:{employee_id}"
    allowed = await _check_rate_limit(rate_key, max_requests=10, window_seconds=3600)
    if not allowed:
        _raise_rate_limit(retry_after=3600)

    # Parse resource_id if provided
    res_id = None
    if resource_id:
        try:
            res_id = UUID(resource_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid resource_id format.")

    svc = DocumentService(db, tenant_id)
    doc = await svc.upload(
        file=file,
        uploaded_by=employee_id,
        category=category,
        resource_type=resource_type,
        resource_id=res_id,
        description=description,
    )
    await db.commit()
    await db.refresh(doc)
    return _doc_to_out(doc)


@router.get("/", response_model=list[DocumentOut])
async def list_documents(
    resource_type: str | None = Query(None),
    resource_id: str | None = Query(None),
    category: str | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: AdminUser = Depends(get_current_user),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """List documents with optional filters. Non-HR users only see own documents."""
    res_id = None
    if resource_id:
        try:
            res_id = UUID(resource_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid resource_id format.")

    # Finding 2: Non-HR users can only list their own documents
    is_hr = has_minimum_role(current_user, AdminRole.hr_manager)
    employee_id = await resolve_employee_id(current_user, tenant_id, db)
    owner_filter = None if is_hr else employee_id

    svc = DocumentService(db, tenant_id)
    docs = await svc.list_documents(
        resource_type=resource_type,
        resource_id=res_id,
        category=category,
        limit=limit,
        offset=offset,
        uploaded_by=owner_filter,
    )
    return [_doc_to_out(d) for d in docs]


@router.get("/{document_id}", response_model=DocumentOut)
async def get_document(
    document_id: UUID,  # Finding 13: UUID path param
    current_user: AdminUser = Depends(get_current_user),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Get document metadata. Non-HR users can only view own documents."""
    svc = DocumentService(db, tenant_id)
    doc = await svc.get_document(document_id)

    # Finding 2: Ownership check for non-HR users
    if not has_minimum_role(current_user, AdminRole.hr_manager):
        employee_id = await resolve_employee_id(current_user, tenant_id, db)
        if doc.uploaded_by != employee_id:
            raise HTTPException(status_code=404, detail="Document not found.")

    return _doc_to_out(doc)


@router.get("/{document_id}/download")
async def download_document(
    document_id: UUID,  # Finding 13
    current_user: AdminUser = Depends(get_current_user),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Stream file content as a download. Non-HR users can only download own documents."""
    svc = DocumentService(db, tenant_id)
    doc = await svc.get_document(document_id)

    # Finding 2: Ownership check for non-HR users
    if not has_minimum_role(current_user, AdminRole.hr_manager):
        employee_id = await resolve_employee_id(current_user, tenant_id, db)
        if doc.uploaded_by != employee_id:
            raise HTTPException(status_code=404, detail="Document not found.")

    file_path = await svc.get_file_path(document_id)

    return FileResponse(
        path=file_path,
        media_type=doc.content_type,
        filename=doc.original_filename,
    )


@router.delete("/{document_id}")
async def delete_document(
    document_id: UUID,  # Finding 13
    current_user: AdminUser = Depends(get_current_user),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete a document. HR managers can delete any; others can delete own."""
    svc = DocumentService(db, tenant_id)

    # Finding 7 + 12: resolve employee_id once, use has_minimum_role,
    # and delegate ownership check to service layer
    employee_id = await resolve_employee_id(current_user, tenant_id, db)
    is_hr = has_minimum_role(current_user, AdminRole.hr_manager)

    # Pass owner_employee_id only for non-HR users so the service enforces ownership
    await svc.soft_delete(
        document_id,
        deleted_by=employee_id,
        owner_employee_id=None if is_hr else employee_id,
    )
    await db.commit()
    return {"status": "deleted", "document_id": str(document_id)}
