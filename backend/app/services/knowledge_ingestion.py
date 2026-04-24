"""Knowledge ingestion pipeline — heading-aware markdown chunking with embeddings."""
import re
import uuid
import logging
from uuid import UUID

import httpx
import tiktoken
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.knowledge_source import (
    KnowledgeSource, KnowledgeChunk, EmbeddingStatus,
)

logger = logging.getLogger(__name__)
settings = get_settings()

# tiktoken encoder for accurate token counting (same tokenizer as OpenAI embeddings)
_encoding: tiktoken.Encoding | None = None


def _get_encoding() -> tiktoken.Encoding:
    global _encoding
    if _encoding is None:
        _encoding = tiktoken.get_encoding("cl100k_base")
    return _encoding


def _count_tokens(text: str) -> int:
    """Count tokens using cl100k_base encoding."""
    return len(_get_encoding().encode(text))


# Module-level shared httpx client (same pattern as rag/retriever.py)
_httpx_client: httpx.AsyncClient | None = None


def _get_httpx_client() -> httpx.AsyncClient:
    global _httpx_client
    if _httpx_client is None or _httpx_client.is_closed:
        _httpx_client = httpx.AsyncClient(timeout=60.0)
    return _httpx_client


async def _get_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """Get embeddings for a batch of texts from OpenAI API."""
    client = _get_httpx_client()
    response = await client.post(
        "https://api.openai.com/v1/embeddings",
        headers={
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": settings.embedding_model,
            "input": texts,
        },
    )
    response.raise_for_status()
    data = response.json()
    sorted_embeddings = sorted(data["data"], key=lambda x: x["index"])
    return [item["embedding"] for item in sorted_embeddings]


# ── Heading-aware markdown chunking ─────────────────────────────────────────

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


def _parse_sections(content: str) -> list[dict]:
    """Parse markdown into sections with heading hierarchy.

    Returns a list of dicts:
        {
            "heading_path": ["## Leave Policy", "### Annual Leave"],
            "text": "section body text...",
        }
    """
    lines = content.split("\n")
    sections: list[dict] = []
    heading_stack: list[tuple[int, str]] = []  # (level, heading_text)
    current_lines: list[str] = []

    def _flush():
        body = "\n".join(current_lines).strip()
        if body:
            path = [h for _, h in heading_stack]
            sections.append({"heading_path": list(path), "text": body})

    for line in lines:
        m = _HEADING_RE.match(line)
        if m:
            _flush()
            current_lines = []
            level = len(m.group(1))
            heading_text = f"{'#' * level} {m.group(2)}"
            # Pop headings at same or deeper level
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            heading_stack.append((level, heading_text))
        else:
            current_lines.append(line)

    _flush()

    # If no sections were created (no headings), treat the whole content as one section
    if not sections and content.strip():
        sections.append({"heading_path": [], "text": content.strip()})

    return sections


def _chunk_text(
    text: str,
    chunk_size: int,
    chunk_overlap: int,
    heading_prefix: str,
) -> list[tuple[str, int]]:
    """Split text into token-sized chunks with overlap.

    Returns list of (chunk_content_with_prefix, token_count).
    """
    encoding = _get_encoding()
    tokens = encoding.encode(text)

    if not tokens:
        return []

    # If entire text fits in one chunk, return as-is
    prefix_tokens = _count_tokens(heading_prefix) if heading_prefix else 0
    effective_chunk_size = chunk_size - prefix_tokens

    if effective_chunk_size <= 0:
        effective_chunk_size = chunk_size  # heading is huge; skip prefix budget

    if len(tokens) <= effective_chunk_size:
        full_text = f"{heading_prefix}\n\n{text}" if heading_prefix else text
        return [(full_text.strip(), _count_tokens(full_text.strip()))]

    chunks: list[tuple[str, int]] = []
    start = 0

    while start < len(tokens):
        end = min(start + effective_chunk_size, len(tokens))
        chunk_tokens = tokens[start:end]
        chunk_text = encoding.decode(chunk_tokens)

        # Try to break at paragraph or sentence boundary
        if end < len(tokens):
            # Look for last paragraph break
            last_para = chunk_text.rfind("\n\n")
            if last_para > len(chunk_text) // 3:
                chunk_text = chunk_text[:last_para]
                # Recalculate the actual token end
                actual_tokens = len(encoding.encode(chunk_text))
                end = start + actual_tokens
            else:
                # Look for last sentence break
                last_sentence = max(
                    chunk_text.rfind(". "),
                    chunk_text.rfind(".\n"),
                    chunk_text.rfind("\u06D4 "),  # Arabic full stop
                )
                if last_sentence > len(chunk_text) // 3:
                    chunk_text = chunk_text[:last_sentence + 1]
                    actual_tokens = len(encoding.encode(chunk_text))
                    end = start + actual_tokens

        full_chunk = f"{heading_prefix}\n\n{chunk_text}" if heading_prefix else chunk_text
        full_chunk = full_chunk.strip()
        chunks.append((full_chunk, _count_tokens(full_chunk)))

        # Advance with overlap
        step = end - start
        start = end - chunk_overlap if end < len(tokens) else end
        # Safety: ensure we make progress
        if start <= end - step:
            start = end

    return chunks


def chunk_markdown(
    content: str,
    chunk_size: int = 800,
    chunk_overlap: int = 100,
) -> list[tuple[str, int]]:
    """Split markdown content into heading-aware chunks.

    Returns list of (chunk_content, token_count).
    """
    sections = _parse_sections(content)
    all_chunks: list[tuple[str, int]] = []

    for section in sections:
        heading_prefix = " > ".join(section["heading_path"]) if section["heading_path"] else ""
        section_chunks = _chunk_text(
            section["text"],
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            heading_prefix=heading_prefix,
        )
        all_chunks.extend(section_chunks)

    return all_chunks


# ── Main ingestion functions ─────────────────────────────────────────────────

async def ingest_markdown(
    db: AsyncSession,
    tenant_id: UUID,
    source_id: UUID,
    content: str,
    chunk_size: int = 800,
    chunk_overlap: int = 100,
) -> int:
    """Ingest markdown content: chunk, embed, store. Returns chunk count.

    Updates the KnowledgeSource embedding_status and chunk_count.
    Atomic: rolls back partial chunks on failure.
    """
    from sqlalchemy import select

    # Fetch the source record
    result = await db.execute(
        select(KnowledgeSource).where(KnowledgeSource.id == source_id, KnowledgeSource.tenant_id == tenant_id)
    )
    source = result.scalar_one_or_none()
    if not source:
        raise ValueError(f"KnowledgeSource {source_id} not found")

    # Mark as processing
    source.embedding_status = EmbeddingStatus.processing
    await db.flush()

    try:
        # Delete any existing chunks for re-ingestion
        await db.execute(
            delete(KnowledgeChunk).where(KnowledgeChunk.source_id == source_id)
        )

        # Chunk the content
        chunks = chunk_markdown(content, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        if not chunks:
            source.chunk_count = 0
            source.embedding_status = EmbeddingStatus.complete
            await db.flush()
            logger.info("Source %s produced no chunks after splitting", source_id)
            return 0

        logger.info("Split source %s into %d chunks", source_id, len(chunks))

        # Embed in batches of 50
        BATCH_SIZE = 50
        chunk_texts = [c[0] for c in chunks]
        all_embeddings: list[list[float]] = []

        for i in range(0, len(chunk_texts), BATCH_SIZE):
            batch = chunk_texts[i:i + BATCH_SIZE]
            batch_embeddings = await _get_embeddings_batch(batch)
            all_embeddings.extend(batch_embeddings)

        # Create KnowledgeChunk records
        for idx, ((chunk_text, token_count), embedding) in enumerate(
            zip(chunks, all_embeddings)
        ):
            chunk = KnowledgeChunk(
                source_id=source_id,
                tenant_id=tenant_id,
                chunk_index=idx,
                content=chunk_text,
                token_count=token_count,
                embedding=embedding,
            )
            db.add(chunk)

        # Update source metadata
        source.chunk_count = len(chunks)
        source.embedding_status = EmbeddingStatus.complete
        source.content_text = content
        await db.flush()

        logger.info(
            "Ingested %d chunks for source %s (tenant %s)",
            len(chunks), source_id, tenant_id,
        )
        return len(chunks)

    except Exception as exc:
        logger.error("Ingestion failed for source %s: %s", source_id, exc)
        # Mark as failed — caller can decide to rollback or commit
        source.embedding_status = EmbeddingStatus.failed
        source.chunk_count = 0
        # Delete any partial chunks
        await db.execute(
            delete(KnowledgeChunk).where(KnowledgeChunk.source_id == source_id)
        )
        await db.flush()
        raise


async def ingest_file(
    db: AsyncSession,
    tenant_id: UUID,
    source_id: UUID,
    file_path: str,
) -> int:
    """Read a .md file from disk and ingest."""
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    return await ingest_markdown(db, tenant_id, source_id, content)
