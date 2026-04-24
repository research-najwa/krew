"""Employee Document API — typed HR document management for admin and employees."""
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.admin_user import AdminUser, AdminRole
from app.auth.dependencies import get_current_user, has_minimum_role, require_tenant
from app.api.helpers import resolve_employee_id
from app.services.employee_document import EmployeeDocumentService
from app.services.document import DocumentService

router = APIRouter(prefix="/employee-documents", tags=["employee-documents"])


# -- Response schemas --------------------------------------------------------


class EmployeeDocumentOut(BaseModel):
    id: str
    employee_id: str
    document_type: str
    label: str | None
    label_ar: str | None
    notes: str | None
    original_filename: str
    file_size: int
    mime_type: str
    expires_at: str | None
    verification_status: str
    verified_by: str | None
    verified_at: str | None
    rejection_reason: str | None
    uploaded_by: str
    uploaded_via: str
    created_at: str
    updated_at: str


class VerifyRequest(BaseModel):
    status: str  # "verified" or "rejected"
    rejection_reason: str | None = None


class ExpiringDocumentOut(BaseModel):
    id: str
    employee_id: str
    employee_name: str
    document_type: str
    original_filename: str
    expires_at: str
    verification_status: str
    days_until_expiry: int


# -- Helpers -----------------------------------------------------------------


def _doc_to_out(doc) -> EmployeeDocumentOut:
    return EmployeeDocumentOut(
        id=str(doc.id),
        employee_id=str(doc.employee_id),
        document_type=doc.document_type.value,
        label=doc.label,
        label_ar=doc.label_ar,
        notes=doc.notes,
        original_filename=doc.original_filename,
        file_size=doc.file_size,
        mime_type=doc.mime_type,
        expires_at=doc.expires_at.isoformat() if doc.expires_at else None,
        verification_status=doc.verification_status.value,
        verified_by=str(doc.verified_by) if doc.verified_by else None,
        verified_at=doc.verified_at.isoformat() if doc.verified_at else None,
        rejection_reason=doc.rejection_reason,
        uploaded_by=str(doc.uploaded_by),
        uploaded_via=doc.uploaded_via,
        created_at=doc.created_at.isoformat(),
        updated_at=doc.updated_at.isoformat(),
    )


# -- Endpoints ---------------------------------------------------------------


@router.post("/upload", response_model=EmployeeDocumentOut)
async def upload_employee_document(
    file: UploadFile = File(...),
    employee_id: str = Form(...),
    document_type: str = Form(...),
    expires_at: str | None = Form(None),
    label: str | None = Form(None),
    label_ar: str | None = Form(None),
    notes: str | None = Form(None),
    uploaded_via: str = Form("web"),
    current_user: AdminUser = Depends(get_current_user),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Upload an HR document for an employee. HR specialist+ can upload for any employee."""
    # HR specialist+ required for uploading
    if not has_minimum_role(current_user, AdminRole.hr_specialist):
        # Non-HR users can only upload for themselves
        uploader_emp_id = await resolve_employee_id(current_user, tenant_id, db)
        try:
            target_emp_id = UUID(employee_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid employee_id format.")
        if target_emp_id != uploader_emp_id:
            raise HTTPException(
                status_code=403,
                detail="You can only upload documents for yourself.",
            )

    try:
        target_emp_id = UUID(employee_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid employee_id format.")

    # Parse expires_at if provided
    parsed_expires: date | None = None
    if expires_at:
        try:
            parsed_expires = date.fromisoformat(expires_at)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid expires_at format. Expected YYYY-MM-DD.",
            )

    uploader_id = await resolve_employee_id(current_user, tenant_id, db)

    svc = EmployeeDocumentService(db, tenant_id)
    emp_doc = await svc.upload(
        file=file,
        employee_id=target_emp_id,
        uploaded_by=uploader_id,
        document_type=document_type,
        uploaded_via=uploaded_via,
        expires_at=parsed_expires,
        label=label,
        label_ar=label_ar,
        notes=notes,
    )
    await db.commit()
    await db.refresh(emp_doc)
    return _doc_to_out(emp_doc)


@router.get("/", response_model=list[EmployeeDocumentOut])
async def list_employee_documents(
    employee_id: str | None = Query(None),
    document_type: str | None = Query(None),
    verification_status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: AdminUser = Depends(get_current_user),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """List employee documents with filters. Non-HR users only see their own."""
    is_hr = has_minimum_role(current_user, AdminRole.hr_specialist)
    current_emp_id = await resolve_employee_id(current_user, tenant_id, db)

    # Non-HR users forced to their own employee_id
    if not is_hr:
        target_emp_id = current_emp_id
    elif employee_id:
        try:
            target_emp_id = UUID(employee_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid employee_id format.")
    else:
        target_emp_id = None

    svc = EmployeeDocumentService(db, tenant_id)

    if target_emp_id:
        docs = await svc.list_for_employee(
            target_emp_id, document_type=document_type,
            limit=limit, offset=offset,
        )
    else:
        # HR listing all — use service without employee filter
        from sqlalchemy import select as sa_select
        from app.models.employee_document import EmployeeDocument, DocumentType as DT, VerificationStatus as VS
        query = (
            sa_select(EmployeeDocument)
            .where(
                EmployeeDocument.tenant_id == tenant_id,
                EmployeeDocument.is_deleted.is_(False),
            )
            .order_by(EmployeeDocument.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        if document_type:
            try:
                query = query.where(EmployeeDocument.document_type == DT(document_type))
            except ValueError:
                pass
        if verification_status:
            try:
                query = query.where(EmployeeDocument.verification_status == VS(verification_status))
            except ValueError:
                pass
        result = await db.execute(query)
        docs = list(result.scalars().all())

    # Apply verification_status filter for employee-scoped queries
    if target_emp_id and verification_status:
        from app.models.employee_document import VerificationStatus as VS
        try:
            vs = VS(verification_status)
            docs = [d for d in docs if d.verification_status == vs]
        except ValueError:
            pass

    return [_doc_to_out(d) for d in docs]


@router.get("/expiring", response_model=list[ExpiringDocumentOut])
async def list_expiring_documents(
    days: int = Query(30, ge=1, le=365),
    document_type: str | None = Query(None),
    current_user: AdminUser = Depends(get_current_user),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """List documents expiring within N days. HR specialist+ only."""
    if not has_minimum_role(current_user, AdminRole.hr_specialist):
        raise HTTPException(status_code=403, detail="HR specialist role required.")

    svc = EmployeeDocumentService(db, tenant_id)
    rows = await svc.list_expiring(days=days, document_type=document_type)

    today = date.today()
    return [
        ExpiringDocumentOut(
            id=str(doc.id),
            employee_id=str(doc.employee_id),
            employee_name=emp.full_name,
            document_type=doc.document_type.value,
            original_filename=doc.original_filename,
            expires_at=doc.expires_at.isoformat(),
            verification_status=doc.verification_status.value,
            days_until_expiry=(doc.expires_at - today).days,
        )
        for doc, emp in rows
    ]


@router.get("/{doc_id}", response_model=EmployeeDocumentOut)
async def get_employee_document(
    doc_id: UUID,
    current_user: AdminUser = Depends(get_current_user),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Get document metadata. Non-HR users can only view own documents."""
    svc = EmployeeDocumentService(db, tenant_id)
    doc = await svc.get_document(doc_id)

    if not has_minimum_role(current_user, AdminRole.hr_specialist):
        emp_id = await resolve_employee_id(current_user, tenant_id, db)
        if doc.employee_id != emp_id:
            raise HTTPException(status_code=404, detail="Employee document not found.")

    return _doc_to_out(doc)


@router.get("/{doc_id}/download")
async def download_employee_document(
    doc_id: UUID,
    current_user: AdminUser = Depends(get_current_user),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Stream file content. Non-HR users can only download own documents."""
    svc = EmployeeDocumentService(db, tenant_id)
    doc = await svc.get_document(doc_id)

    if not has_minimum_role(current_user, AdminRole.hr_specialist):
        emp_id = await resolve_employee_id(current_user, tenant_id, db)
        if doc.employee_id != emp_id:
            raise HTTPException(status_code=404, detail="Employee document not found.")

    # Delegate file streaming to DocumentService
    doc_svc = DocumentService(db, tenant_id)
    file_path = await doc_svc.get_file_path(doc.document_id)

    return FileResponse(
        path=file_path,
        media_type=doc.mime_type,
        filename=doc.original_filename,
    )


@router.delete("/{doc_id}")
async def delete_employee_document(
    doc_id: UUID,
    current_user: AdminUser = Depends(get_current_user),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete an employee document. HR manager+ required."""
    if not has_minimum_role(current_user, AdminRole.hr_manager):
        raise HTTPException(status_code=403, detail="HR manager role required.")

    svc = EmployeeDocumentService(db, tenant_id)
    await svc.soft_delete(doc_id)
    await db.commit()
    return {"status": "deleted", "document_id": str(doc_id)}


@router.put("/{doc_id}/verify", response_model=EmployeeDocumentOut)
async def verify_employee_document(
    doc_id: UUID,
    body: VerifyRequest,
    current_user: AdminUser = Depends(get_current_user),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Verify or reject a pending document. HR manager+ required."""
    if not has_minimum_role(current_user, AdminRole.hr_manager):
        raise HTTPException(status_code=403, detail="HR manager role required.")

    svc = EmployeeDocumentService(db, tenant_id)
    doc = await svc.verify(
        doc_id=doc_id,
        admin_id=current_user.id,
        new_status=body.status,
        rejection_reason=body.rejection_reason,
    )
    await db.commit()
    await db.refresh(doc)
    return _doc_to_out(doc)
