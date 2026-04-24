"""One-time migration: copy policies + policy_chunks -> knowledge_sources + knowledge_chunks.

Usage:
    cd backend
    python -m scripts.migrate_policies_to_knowledge

Idempotent: checks by (tenant_id, title, source_type) before inserting.
Original tables are NOT modified or deleted.
"""
import asyncio
import logging
import sys
from pathlib import Path

# Ensure the backend app is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from app.database import async_session
from app.models.policy import Policy, PolicyChunk
from app.models.knowledge_source import (
    KnowledgeSource, KnowledgeChunk, SourceType, EmbeddingStatus,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


async def migrate_policies() -> None:
    """Copy active policies and their chunks to the knowledge management tables."""
    async with async_session() as db:
        # Fetch all active policies
        result = await db.execute(
            select(Policy).where(Policy.is_active == True)  # noqa: E712
        )
        policies = result.scalars().all()
        logger.info("Found %d active policies to migrate", len(policies))

        migrated_count = 0
        skipped_count = 0

        for policy in policies:
            # Idempotency check: skip if KnowledgeSource already exists
            existing = await db.execute(
                select(KnowledgeSource).where(
                    KnowledgeSource.tenant_id == policy.tenant_id,
                    KnowledgeSource.title == policy.title,
                    KnowledgeSource.source_type == SourceType.policy,
                )
            )
            if existing.scalar_one_or_none():
                logger.info("SKIP (already migrated): '%s'", policy.title)
                skipped_count += 1
                continue

            # Create KnowledgeSource
            ks = KnowledgeSource(
                tenant_id=policy.tenant_id,
                title=policy.title,
                source_type=SourceType.policy,
                category=policy.category,
                source_policy_id=policy.id,
                embedding_status=EmbeddingStatus.complete,
                is_active=True,
            )
            db.add(ks)
            await db.flush()  # Get ks.id

            # Copy chunks
            chunks_result = await db.execute(
                select(PolicyChunk).where(PolicyChunk.policy_id == policy.id)
            )
            chunk_count = 0
            for chunk in chunks_result.scalars():
                kc = KnowledgeChunk(
                    source_id=ks.id,
                    tenant_id=policy.tenant_id,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    token_count=chunk.token_count,
                    embedding=chunk.embedding,
                )
                db.add(kc)
                chunk_count += 1

            ks.chunk_count = chunk_count
            migrated_count += 1
            logger.info(
                "MIGRATED: '%s' (id=%s) -> KnowledgeSource (id=%s) with %d chunks",
                policy.title, policy.id, ks.id, chunk_count,
            )

        await db.commit()

        logger.info("=" * 60)
        logger.info("Migration complete.")
        logger.info("  Migrated: %d policies", migrated_count)
        logger.info("  Skipped:  %d policies (already existed)", skipped_count)
        logger.info("  Total:    %d policies processed", migrated_count + skipped_count)


if __name__ == "__main__":
    asyncio.run(migrate_policies())
