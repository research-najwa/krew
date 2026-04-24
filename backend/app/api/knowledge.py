"""Knowledge management API — CRUD, ingestion, agent assignments, AI capture."""
import asyncio
import json
import logging
from uuid import UUID

import anthropic
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db

# prevent background tasks from being GC'd before completion
_background_tasks: set = set()
from app.auth.dependencies import get_current_user, require_tenant
from app.models.admin_user import AdminUser
from app.models.knowledge_source import (
    KnowledgeSource, KnowledgeChunk, AgentKnowledgeAssignment,
    SourceType, EmbeddingStatus,
)
from app.models.deployed_agent import DeployedAgent
from app.services.knowledge_ingestion import ingest_markdown

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


# ── Pydantic schemas ────────────────────────────────────────────────────────


class KnowledgeSourceCreate(BaseModel):
    title: str
    title_ar: str | None = None
    source_type: SourceType
    category: str | None = None
    content_text: str | None = None
    url: str | None = None
    source_policy_id: str | None = None
    metadata_json: dict | None = None


class KnowledgeSourceUpdate(BaseModel):
    title: str | None = None
    title_ar: str | None = None
    category: str | None = None
    is_active: bool | None = None
    metadata_json: dict | None = None


class KnowledgeSourceResponse(BaseModel):
    id: str
    tenant_id: str
    title: str
    title_ar: str | None
    source_type: str
    category: str | None
    chunk_count: int
    embedding_status: str
    is_active: bool
    assignment_count: int
    created_at: str
    updated_at: str


class KnowledgeSourceListResponse(BaseModel):
    items: list[KnowledgeSourceResponse]
    total: int
    page: int
    page_size: int


class AgentAssignRequest(BaseModel):
    agent_id: str


class IngestTextRequest(BaseModel):
    content: str


class CaptureRequest(BaseModel):
    content: str
    language: str = "en"


class CaptureResponse(BaseModel):
    suggested_title: str
    suggested_category: str
    suggested_agents: list[str]
    structured_content: str
    confidence: float


# ── Helpers ──────────────────────────────────────────────────────────────────


def _source_to_response(source: KnowledgeSource, assignment_count: int = 0) -> KnowledgeSourceResponse:
    """Convert a KnowledgeSource ORM object to a response dict."""
    return KnowledgeSourceResponse(
        id=str(source.id),
        tenant_id=str(source.tenant_id),
        title=source.title,
        title_ar=source.title_ar,
        source_type=source.source_type.value,
        category=source.category,
        chunk_count=source.chunk_count,
        embedding_status=source.embedding_status.value,
        is_active=source.is_active,
        assignment_count=assignment_count,
        created_at=source.created_at.isoformat() if source.created_at else "",
        updated_at=source.updated_at.isoformat() if source.updated_at else "",
    )


async def _get_assignment_count(db: AsyncSession, source_id: UUID) -> int:
    """Count agent assignments for a source."""
    count = await db.scalar(
        select(func.count(AgentKnowledgeAssignment.id)).where(
            AgentKnowledgeAssignment.source_id == source_id
        )
    )
    return count or 0


async def _get_source_or_404(
    db: AsyncSession, source_id: UUID, tenant_id: UUID
) -> KnowledgeSource:
    """Fetch a KnowledgeSource by ID and tenant, or raise 404."""
    result = await db.execute(
        select(KnowledgeSource).where(
            KnowledgeSource.id == source_id,
            KnowledgeSource.tenant_id == tenant_id,
        )
    )
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Knowledge source not found")
    return source


async def _background_ingest(source_id: UUID, tenant_id: UUID, content: str) -> None:
    """Background task to run ingestion in a fresh DB session."""
    try:
        from app.database import async_session
        async with async_session() as db:
            await ingest_markdown(db, tenant_id, source_id, content)
            await db.commit()
    except Exception as exc:
        logger.error("Background ingestion failed for source %s: %s", source_id, exc)
        # Mark as failed in a fresh session
        try:
            from app.database import async_session as session_maker
            async with session_maker() as db:
                result = await db.execute(
                    select(KnowledgeSource).where(KnowledgeSource.id == source_id)
                )
                src = result.scalar_one_or_none()
                if src:
                    src.embedding_status = EmbeddingStatus.failed
                    await db.commit()
        except Exception:
            logger.error("Failed to mark source %s as failed", source_id)


# ── CRUD Endpoints ───────────────────────────────────────────────────────────


@router.post("/sources", response_model=KnowledgeSourceResponse, status_code=201)
async def create_knowledge_source(
    body: KnowledgeSourceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
    tenant_id: UUID = Depends(require_tenant()),
):
    """Create a new knowledge source."""
    source = KnowledgeSource(
        tenant_id=tenant_id,
        title=body.title,
        title_ar=body.title_ar,
        source_type=body.source_type,
        category=body.category,
        content_text=body.content_text,
        url=body.url,
        source_policy_id=UUID(body.source_policy_id) if body.source_policy_id else None,
        metadata_json=body.metadata_json,
        created_by=current_user.id if current_user else None,
    )
    db.add(source)
    await db.commit()
    await db.refresh(source)
    return _source_to_response(source, assignment_count=0)


@router.get("/sources", response_model=KnowledgeSourceListResponse)
async def list_knowledge_sources(
    source_type: str | None = Query(None),
    category: str | None = Query(None),
    status: str | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
    tenant_id: UUID = Depends(require_tenant()),
):
    """List knowledge sources with optional filters and pagination."""
    # Base query
    query = select(KnowledgeSource).where(
        KnowledgeSource.tenant_id == tenant_id,
    )
    count_query = select(func.count(KnowledgeSource.id)).where(
        KnowledgeSource.tenant_id == tenant_id,
    )

    # Apply filters
    if source_type:
        try:
            st = SourceType(source_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid source_type: {source_type}")
        query = query.where(KnowledgeSource.source_type == st)
        count_query = count_query.where(KnowledgeSource.source_type == st)

    if category:
        query = query.where(KnowledgeSource.category == category)
        count_query = count_query.where(KnowledgeSource.category == category)

    if status:
        try:
            es = EmbeddingStatus(status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
        query = query.where(KnowledgeSource.embedding_status == es)
        count_query = count_query.where(KnowledgeSource.embedding_status == es)

    # Get total count
    total = await db.scalar(count_query) or 0

    # Paginate and fetch
    offset = (page - 1) * page_size
    query = query.order_by(KnowledgeSource.created_at.desc()).offset(offset).limit(page_size)
    result = await db.execute(query)
    sources = result.scalars().all()

    # Get assignment counts for each source
    items = []
    for source in sources:
        ac = await _get_assignment_count(db, source.id)
        items.append(_source_to_response(source, assignment_count=ac))

    return KnowledgeSourceListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/sources/{source_id}", response_model=KnowledgeSourceResponse)
async def get_knowledge_source(
    source_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
    tenant_id: UUID = Depends(require_tenant()),
):
    """Get a single knowledge source with chunk and assignment counts."""
    source = await _get_source_or_404(db, source_id, tenant_id)
    ac = await _get_assignment_count(db, source.id)
    return _source_to_response(source, assignment_count=ac)


@router.patch("/sources/{source_id}", response_model=KnowledgeSourceResponse)
async def update_knowledge_source(
    source_id: UUID,
    body: KnowledgeSourceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
    tenant_id: UUID = Depends(require_tenant()),
):
    """Update a knowledge source's metadata."""
    source = await _get_source_or_404(db, source_id, tenant_id)

    if body.title is not None:
        source.title = body.title
    if body.title_ar is not None:
        source.title_ar = body.title_ar
    if body.category is not None:
        source.category = body.category
    if body.is_active is not None:
        source.is_active = body.is_active
    if body.metadata_json is not None:
        source.metadata_json = body.metadata_json

    await db.commit()
    await db.refresh(source)
    ac = await _get_assignment_count(db, source.id)
    return _source_to_response(source, assignment_count=ac)


@router.delete("/sources/{source_id}")
async def delete_knowledge_source(
    source_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
    tenant_id: UUID = Depends(require_tenant()),
):
    """Soft delete a knowledge source (set is_active=False)."""
    source = await _get_source_or_404(db, source_id, tenant_id)
    source.is_active = False
    await db.commit()
    return {"status": "deactivated"}


# ── Upload and Ingestion ────────────────────────────────────────────────────


@router.post("/sources/{source_id}/upload", status_code=202)
async def upload_markdown_file(
    source_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
    tenant_id: UUID = Depends(require_tenant()),
):
    """Upload a markdown file and trigger background ingestion."""
    source = await _get_source_or_404(db, source_id, tenant_id)

    # Validate file extension
    if not file.filename or not file.filename.lower().endswith(".md"):
        raise HTTPException(status_code=400, detail="Only .md files are supported")

    # Validate file size (5 MB max)
    contents = await file.read()
    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 5 MB)")

    try:
        content_str = contents.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File is not valid UTF-8 text")

    # Update source — sanitize filename to prevent path traversal
    import os
    source.file_path = os.path.basename(file.filename or "upload.md")
    source.embedding_status = EmbeddingStatus.processing
    await db.commit()

    # Trigger background ingestion
    task = asyncio.create_task(_background_ingest(source.id, tenant_id, content_str))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return {"status": "processing", "source_id": str(source.id)}


@router.post("/sources/{source_id}/ingest-text", status_code=202)
async def ingest_text(
    source_id: UUID,
    body: IngestTextRequest,
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
    tenant_id: UUID = Depends(require_tenant()),
):
    """Ingest raw text content into a knowledge source."""
    source = await _get_source_or_404(db, source_id, tenant_id)

    if not body.content.strip():
        raise HTTPException(status_code=400, detail="Content cannot be empty")

    # Update source
    source.embedding_status = EmbeddingStatus.processing
    await db.commit()

    # Trigger background ingestion
    task = asyncio.create_task(_background_ingest(source.id, tenant_id, body.content))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return {"status": "processing", "source_id": str(source.id)}


# ── Agent Assignments ────────────────────────────────────────────────────────


@router.post("/sources/{source_id}/assign")
async def assign_source_to_agent(
    source_id: UUID,
    body: AgentAssignRequest,
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
    tenant_id: UUID = Depends(require_tenant()),
):
    """Assign a knowledge source to a deployed agent."""
    source = await _get_source_or_404(db, source_id, tenant_id)

    agent_uuid = UUID(body.agent_id)

    # Verify agent exists and belongs to tenant
    agent_result = await db.execute(
        select(DeployedAgent).where(
            DeployedAgent.id == agent_uuid,
            DeployedAgent.tenant_id == tenant_id,
        )
    )
    agent = agent_result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Create assignment
    assignment = AgentKnowledgeAssignment(
        agent_id=agent_uuid,
        source_id=source.id,
        tenant_id=tenant_id,
        assigned_by=current_user.id if hasattr(current_user, 'id') else None,
    )
    db.add(assignment)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Source already assigned to this agent")

    return {"status": "assigned"}


@router.delete("/sources/{source_id}/assign/{agent_id}")
async def unassign_source_from_agent(
    source_id: UUID,
    agent_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
    tenant_id: UUID = Depends(require_tenant()),
):
    """Remove a knowledge source assignment from an agent."""
    result = await db.execute(
        select(AgentKnowledgeAssignment).where(
            AgentKnowledgeAssignment.source_id == source_id,
            AgentKnowledgeAssignment.agent_id == agent_id,
            AgentKnowledgeAssignment.tenant_id == tenant_id,
        )
    )
    assignment = result.scalar_one_or_none()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    await db.delete(assignment)
    await db.commit()
    return {"status": "unassigned"}


@router.get("/agents/{agent_id}/sources", response_model=KnowledgeSourceListResponse)
async def list_agent_sources(
    agent_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
    tenant_id: UUID = Depends(require_tenant()),
):
    """List knowledge sources assigned to a specific agent."""
    # Get source IDs assigned to the agent
    assignment_query = select(AgentKnowledgeAssignment.source_id).where(
        AgentKnowledgeAssignment.agent_id == agent_id,
        AgentKnowledgeAssignment.tenant_id == tenant_id,
    )

    # Count total
    count_query = select(func.count(KnowledgeSource.id)).where(
        KnowledgeSource.tenant_id == tenant_id,
        KnowledgeSource.id.in_(assignment_query),
    )
    total = await db.scalar(count_query) or 0

    # Fetch paginated sources
    offset = (page - 1) * page_size
    query = (
        select(KnowledgeSource)
        .where(
            KnowledgeSource.tenant_id == tenant_id,
            KnowledgeSource.id.in_(assignment_query),
        )
        .order_by(KnowledgeSource.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    result = await db.execute(query)
    sources = result.scalars().all()

    items = []
    for source in sources:
        ac = await _get_assignment_count(db, source.id)
        items.append(_source_to_response(source, assignment_count=ac))

    return KnowledgeSourceListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


# ── AI-Assisted Knowledge Capture ───────────────────────────────────────────

CAPTURE_SYSTEM_PROMPT = """You are a knowledge structuring assistant for an HR platform.
Given raw text input (possibly from voice transcription), extract and structure it into:
1. A clear, concise title (English)
2. A category (one of: leave, attendance, conduct, compensation, benefits, safety, general, onboarding, recruitment, compliance)
3. Suggested agents who should have access (from: deema, waleed, mohammad, ahmad, yara)
4. A clean, structured version of the content

Respond in JSON format:
{
    "suggested_title": "...",
    "suggested_category": "...",
    "suggested_agents": ["..."],
    "structured_content": "...",
    "confidence": 0.0-1.0
}

Rules:
- If the content is about leave/absence/vacation -> suggest deema
- If about recruitment/hiring/candidates -> suggest mohammad
- If about onboarding/team/approvals -> suggest waleed
- If about analytics/compliance/budgets -> suggest ahmad
- If about agents/automation -> suggest yara
- Default to deema for general HR content
- Confidence is your certainty about the categorization (0.5 = unsure, 0.9 = very confident)
"""


@router.post("/capture", response_model=CaptureResponse)
async def capture_knowledge(
    body: CaptureRequest,
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
    tenant_id: UUID = Depends(require_tenant()),
):
    """AI-assisted knowledge capture — structures raw text into a knowledge entry."""
    if not body.content.strip():
        raise HTTPException(status_code=400, detail="Content cannot be empty")

    if not settings.anthropic_api_key:
        raise HTTPException(status_code=503, detail="AI service unavailable")

    try:
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system=CAPTURE_SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": f"Language hint: {body.language}\n\n<user_input>\n{body.content}\n</user_input>",
            }],
        )

        # Parse the JSON response
        response_text = response.content[0].text.strip()
        # Handle markdown code blocks (```json ... ```)
        import re as _re
        response_text = _re.sub(r'^```[a-z]*\n', '', response_text)
        response_text = _re.sub(r'\n?```\s*$', '', response_text)
        response_text = response_text.strip()

        parsed = json.loads(response_text)

        return CaptureResponse(
            suggested_title=parsed.get("suggested_title", "Untitled"),
            suggested_category=parsed.get("suggested_category", "general"),
            suggested_agents=parsed.get("suggested_agents", ["deema"]),
            structured_content=parsed.get("structured_content", body.content),
            confidence=float(parsed.get("confidence", 0.5)),
        )

    except json.JSONDecodeError:
        logger.error("Failed to parse AI capture response as JSON")
        # Return a best-effort fallback
        return CaptureResponse(
            suggested_title="Untitled Knowledge Entry",
            suggested_category="general",
            suggested_agents=["deema"],
            structured_content=body.content,
            confidence=0.3,
        )
    except anthropic.APIError as exc:
        logger.error("Anthropic API error in capture: %s", exc)
        raise HTTPException(status_code=503, detail="AI service temporarily unavailable")
