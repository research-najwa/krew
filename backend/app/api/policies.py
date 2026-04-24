"""Policy upload and management API — feeds the RAG pipeline."""
from uuid import UUID

from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.database import get_db
from app.models.policy import Policy
from app.rag.ingest import PolicyIngestor
from app.models.admin_user import AdminUser, AdminRole
from app.auth.dependencies import require_role, require_tenant
from app.security.input_validator import sanitize_filename, validate_string_field

router = APIRouter(prefix="/policies", tags=["policies"])


class PolicyResponse(BaseModel):
    id: UUID
    title: str
    category: str
    version: int
    is_active: bool
    chunk_count: int


@router.post("/upload", response_model=PolicyResponse)
async def upload_policy(
    title: str = Form(...),
    category: str = Form(...),
    file: UploadFile = File(...),
    current_user: AdminUser = Depends(require_role(AdminRole.hr_manager)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Upload a policy document. Supported: .txt, .pdf, .docx"""
    title = validate_string_field(title, "title", max_length=500)
    category = validate_string_field(category, "category", max_length=200)
    safe_filename = sanitize_filename(file.filename)

    content = ""

    if safe_filename.endswith(".txt"):
        raw = await file.read()
        content = raw.decode("utf-8")
    elif safe_filename.endswith(".pdf"):
        from pypdf import PdfReader
        import io
        raw = await file.read()
        reader = PdfReader(io.BytesIO(raw))
        content = "\n".join(page.extract_text() or "" for page in reader.pages)
    elif safe_filename.endswith(".docx"):
        from docx import Document
        import io
        raw = await file.read()
        doc = Document(io.BytesIO(raw))
        content = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    else:
        raise HTTPException(status_code=400, detail="Unsupported file format. Use .txt, .pdf, or .docx")

    if not content.strip():
        raise HTTPException(status_code=400, detail="Document appears to be empty")

    ingestor = PolicyIngestor(db)
    policy = await ingestor.ingest_document(
        tenant_id=tenant_id,
        title=title,
        category=category,
        content=content,
        source_filename=safe_filename,
    )

    return PolicyResponse(
        id=policy.id,
        title=policy.title,
        category=policy.category,
        version=policy.version,
        is_active=policy.is_active,
        chunk_count=len(policy.chunks),
    )


@router.get("/")
async def list_policies(
    current_user: AdminUser = Depends(require_role(AdminRole.hr_specialist)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """List all policies for the authenticated user's tenant."""
    result = await db.execute(
        select(Policy)
        .where(Policy.tenant_id == tenant_id, Policy.is_active == True)
        .order_by(Policy.category, Policy.title)
    )
    policies = result.scalars().all()

    return [
        {
            "id": str(p.id),
            "title": p.title,
            "category": p.category,
            "version": p.version,
            "uploaded_at": p.uploaded_at.isoformat(),
        }
        for p in policies
    ]
