"""Scoped knowledge retriever — vector similarity search scoped to agent assignments."""
import uuid
import logging
from sqlalchemy import text, select, func
from sqlalchemy.ext.asyncio import AsyncSession
import httpx

from app.config import get_settings
from app.models.knowledge_source import AgentKnowledgeAssignment

logger = logging.getLogger(__name__)
settings = get_settings()

# Module-level shared httpx client (same pattern as rag/retriever.py)
_httpx_client: httpx.AsyncClient | None = None


def _get_httpx_client() -> httpx.AsyncClient:
    global _httpx_client
    if _httpx_client is None or _httpx_client.is_closed:
        _httpx_client = httpx.AsyncClient(timeout=30.0)
    return _httpx_client


class ScopedKnowledgeRetriever:
    """Retrieves relevant knowledge chunks scoped to a specific agent's assignments.

    When agent_id is provided and the agent has knowledge assignments, search
    is scoped to those assigned sources only. Otherwise falls back to searching
    all active knowledge sources for the tenant.
    """

    def __init__(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
        agent_id: uuid.UUID | None = None,
    ):
        self.db = db
        self.tenant_id = tenant_id
        self.agent_id = agent_id

    async def _get_embedding(self, text_input: str) -> list[float]:
        """Get embedding vector from OpenAI API."""
        client = _get_httpx_client()
        response = await client.post(
            "https://api.openai.com/v1/embeddings",
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.embedding_model,
                "input": text_input,
            },
        )
        response.raise_for_status()
        data = response.json()
        return data["data"][0]["embedding"]

    async def _scoped_search(
        self, query_embedding: list[float], top_k: int
    ) -> list[dict]:
        """Search knowledge chunks scoped to agent's assigned sources."""
        embedding_str = "[" + ",".join(str(v) for v in query_embedding) + "]"

        sql = text("""
            SELECT
                kc.content,
                kc.chunk_index,
                ks.id AS source_id,
                ks.title AS source_title,
                ks.source_type,
                1 - (kc.embedding <=> :query_embedding) AS similarity_score
            FROM knowledge_chunks kc
            JOIN knowledge_sources ks ON kc.source_id = ks.id
            JOIN agent_knowledge_assignments aka ON kc.source_id = aka.source_id
            WHERE
                aka.agent_id = :agent_id
                AND aka.tenant_id = :tenant_id
                AND kc.tenant_id = :tenant_id
                AND ks.is_active = true
                AND kc.embedding IS NOT NULL
            ORDER BY kc.embedding <=> :query_embedding
            LIMIT :top_k
        """)

        result = await self.db.execute(
            sql,
            {
                "agent_id": str(self.agent_id),
                "tenant_id": str(self.tenant_id),
                "query_embedding": embedding_str,
                "top_k": top_k,
            },
        )
        rows = result.fetchall()
        return [
            {
                "content": row[0],
                "chunk_index": row[1],
                "source_id": str(row[2]),
                "source_title": row[3],
                "source_type": row[4],
                "similarity_score": float(row[5]) if row[5] is not None else 0.0,
            }
            for row in rows
        ]

    async def _global_search(
        self, query_embedding: list[float], top_k: int
    ) -> list[dict]:
        """Search all active knowledge chunks for the tenant (global fallback)."""
        embedding_str = "[" + ",".join(str(v) for v in query_embedding) + "]"

        sql = text("""
            SELECT
                kc.content,
                kc.chunk_index,
                ks.id AS source_id,
                ks.title AS source_title,
                ks.source_type,
                1 - (kc.embedding <=> :query_embedding) AS similarity_score
            FROM knowledge_chunks kc
            JOIN knowledge_sources ks ON kc.source_id = ks.id
            WHERE
                kc.tenant_id = :tenant_id
                AND ks.is_active = true
                AND kc.embedding IS NOT NULL
            ORDER BY kc.embedding <=> :query_embedding
            LIMIT :top_k
        """)

        result = await self.db.execute(
            sql,
            {
                "tenant_id": str(self.tenant_id),
                "query_embedding": embedding_str,
                "top_k": top_k,
            },
        )
        rows = result.fetchall()
        return [
            {
                "content": row[0],
                "chunk_index": row[1],
                "source_id": str(row[2]),
                "source_title": row[3],
                "source_type": row[4],
                "similarity_score": float(row[5]) if row[5] is not None else 0.0,
            }
            for row in rows
        ]

    async def search(self, query: str, top_k: int = 5) -> list[dict]:
        """Search knowledge chunks, scoped to agent's assigned sources.

        If agent_id is provided and the agent has assignments, search only
        those sources. Otherwise fall back to all active sources for the tenant.

        Returns list of:
        {
            "content": str,
            "source_title": str,
            "source_id": str,
            "source_type": str,
            "chunk_index": int,
            "similarity_score": float,
        }
        """
        if not settings.openai_api_key:
            logger.warning("OpenAI API key not set — cannot perform vector search")
            return []

        try:
            query_embedding = await self._get_embedding(query)
        except httpx.HTTPStatusError as exc:
            logger.error("OpenAI embedding API error: %s", exc.response.text)
            return []
        except httpx.RequestError as exc:
            logger.error("Network error calling OpenAI embeddings: %s", exc)
            return []

        if self.agent_id:
            # Check if agent has any assignments
            assignment_count = await self.db.scalar(
                select(func.count(AgentKnowledgeAssignment.id)).where(
                    AgentKnowledgeAssignment.agent_id == self.agent_id,
                    AgentKnowledgeAssignment.tenant_id == self.tenant_id,
                )
            )
            if assignment_count and assignment_count > 0:
                results = await self._scoped_search(query_embedding, top_k)
                if results:
                    logger.info(
                        "Scoped search: %d results for agent %s, tenant %s",
                        len(results), self.agent_id, self.tenant_id,
                    )
                    return results
                # If scoped search returned nothing, fall through to global

        # Fall back to global search
        results = await self._global_search(query_embedding, top_k)
        logger.info(
            "Global search: %d results for tenant %s",
            len(results), self.tenant_id,
        )
        return results
