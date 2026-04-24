"""RAG ingestion — split documents into chunks and embed them for retrieval."""
import re
import uuid
import logging
from sqlalchemy.ext.asyncio import AsyncSession
import httpx

from app.config import get_settings
from app.models import Policy, PolicyChunk

logger = logging.getLogger(__name__)
settings = get_settings()

# Rough token estimate: 1 token ~ 4 characters for English, ~2 chars for Arabic.
# We use a conservative estimate and target ~500 tokens per chunk.
TARGET_CHUNK_TOKENS = 500
CHARS_PER_TOKEN_ESTIMATE = 4
TARGET_CHUNK_CHARS = TARGET_CHUNK_TOKENS * CHARS_PER_TOKEN_ESTIMATE  # ~2000 chars


class PolicyIngestor:
    """Ingests policy documents: splits into chunks, embeds, and stores."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _get_embeddings_batch(self, texts: list[str]) -> list[list[float]]:
        """Get embeddings for a batch of texts from OpenAI API.

        The OpenAI embeddings endpoint supports batching natively, which is
        more efficient than one-at-a-time calls.
        """
        async with httpx.AsyncClient(timeout=60.0) as client:
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
            # Sort by index to ensure correct ordering
            sorted_embeddings = sorted(data["data"], key=lambda x: x["index"])
            return [item["embedding"] for item in sorted_embeddings]

    @staticmethod
    def _split_into_chunks(content: str) -> list[str]:
        """Split content into chunks of approximately TARGET_CHUNK_TOKENS tokens.

        Strategy:
        1. Split on double-newlines (paragraph boundaries) first.
        2. If a paragraph is too long, split on single newlines.
        3. If a line is still too long, split on sentence boundaries.
        4. Merge small adjacent chunks to stay close to the target size.
        """
        # Split into paragraphs
        paragraphs = re.split(r"\n\s*\n", content.strip())
        paragraphs = [p.strip() for p in paragraphs if p.strip()]

        # Further split oversized paragraphs into sentences
        segments: list[str] = []
        for para in paragraphs:
            if len(para) <= TARGET_CHUNK_CHARS:
                segments.append(para)
            else:
                # Split long paragraph on single newlines first
                lines = para.split("\n")
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    if len(line) <= TARGET_CHUNK_CHARS:
                        segments.append(line)
                    else:
                        # Split on sentence boundaries (., !, ?, or Arabic full stop)
                        sentences = re.split(r"(?<=[.!?\u06D4])\s+", line)
                        for sentence in sentences:
                            sentence = sentence.strip()
                            if sentence:
                                segments.append(sentence)

        # Merge small segments into chunks close to target size
        chunks: list[str] = []
        current_chunk: list[str] = []
        current_length = 0

        for segment in segments:
            segment_length = len(segment)

            if current_length + segment_length + 1 > TARGET_CHUNK_CHARS and current_chunk:
                chunks.append("\n\n".join(current_chunk))
                current_chunk = [segment]
                current_length = segment_length
            else:
                current_chunk.append(segment)
                current_length += segment_length + 1  # +1 for the join separator

        if current_chunk:
            chunks.append("\n\n".join(current_chunk))

        return chunks

    @staticmethod
    def _strip_arabic_diacritics(s: str) -> str:
        return re.sub(r'[\u0610-\u061A\u064B-\u065F\u0670]', '', s)

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Rough token count estimate."""
        return max(1, len(text) // CHARS_PER_TOKEN_ESTIMATE)

    async def ingest_document(
        self,
        tenant_id: uuid.UUID,
        title: str,
        category: str,
        content: str,
        source_filename: str | None = None,
    ) -> Policy:
        """Ingest a policy document: create record, chunk, embed, and store.

        Args:
            tenant_id: The tenant this policy belongs to.
            title: Human-readable policy title.
            category: Policy category (e.g., leave, benefits, conduct).
            content: The full text content of the policy document.
            source_filename: Optional original filename.

        Returns:
            The created Policy ORM object with chunks populated.
        """
        # 1. Create the Policy record
        policy = Policy(
            tenant_id=tenant_id,
            title=title,
            category=category,
            source_filename=source_filename,
        )
        self.db.add(policy)
        await self.db.flush()  # Get the generated ID without committing

        logger.info(
            "Created policy '%s' (id=%s) for tenant %s",
            title,
            policy.id,
            tenant_id,
        )

        # 2. Split content into chunks
        chunk_texts = self._split_into_chunks(content)
        logger.info("Split document into %d chunks", len(chunk_texts))

        if not chunk_texts:
            logger.warning("Document '%s' produced no chunks after splitting", title)
            await self.db.commit()
            return policy

        # 3. Get embeddings for all chunks in batch
        # OpenAI allows up to 2048 inputs per request; batch in groups of 100
        # to stay well within limits and manage memory.
        BATCH_SIZE = 100
        all_embeddings: list[list[float]] = []

        for i in range(0, len(chunk_texts), BATCH_SIZE):
            batch = chunk_texts[i : i + BATCH_SIZE]
            batch_embeddings = await self._get_embeddings_batch(batch)
            all_embeddings.extend(batch_embeddings)

        # 4. Create PolicyChunk records
        for idx, (chunk_text, embedding) in enumerate(
            zip(chunk_texts, all_embeddings)
        ):
            chunk = PolicyChunk(
                policy_id=policy.id,
                chunk_index=idx,
                content=chunk_text,
                content_normalized=self._strip_arabic_diacritics(chunk_text),
                embedding=embedding,
                token_count=self._estimate_tokens(chunk_text),
            )
            self.db.add(chunk)

        await self.db.commit()
        await self.db.refresh(policy)

        logger.info(
            "Ingested %d chunks for policy '%s' (id=%s)",
            len(chunk_texts),
            title,
            policy.id,
        )
        return policy
