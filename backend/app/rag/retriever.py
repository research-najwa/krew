"""RAG retriever — vector similarity search over tenant policy chunks."""
import re
import uuid
import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Module-level shared httpx client — avoids TCP/TLS handshake on every embedding call
_httpx_client: httpx.AsyncClient | None = None


def _get_httpx_client() -> httpx.AsyncClient:
    global _httpx_client
    if _httpx_client is None or _httpx_client.is_closed:
        _httpx_client = httpx.AsyncClient(timeout=30.0)
    return _httpx_client


class PolicyRetriever:
    """Retrieves relevant policy chunks for a tenant using pgvector cosine distance."""

    def __init__(self, db: AsyncSession, tenant_id: uuid.UUID):
        self.db = db
        self.tenant_id = tenant_id

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

    # Common Arabic/English stop words to exclude from keyword extraction
    _STOP_WORDS = {
        "وش", "ايش", "شو", "ما", "هل", "عن", "في", "من", "على", "إلى",
        "هو", "هي", "هم", "أنا", "هذا", "هذه", "ذلك", "تلك", "التي", "الذي",
        "كيف", "لماذا", "متى", "أين", "كم", "لي", "لك", "يا", "مع",
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "what", "how", "why", "when", "where", "who", "which", "do", "does",
        "can", "could", "would", "should", "my", "your", "our", "their",
        "of", "in", "on", "at", "to", "for", "with", "by", "from", "about",
        "and", "or", "not", "no", "it", "this", "that", "i", "me", "we",
    }

    def _extract_keywords(self, query: str) -> list[str]:
        """Extract meaningful keywords from a search query."""
        # Remove common Arabic diacritics
        clean = re.sub(r'[\u0610-\u061A\u064B-\u065F\u0670]', '', query)
        # Split on whitespace and punctuation
        tokens = re.split(r'[\s,،.؟?!]+', clean)
        # Filter stop words and short tokens
        keywords = [
            t for t in tokens
            if len(t) > 1 and t.lower() not in self._STOP_WORDS
        ]
        return keywords if keywords else tokens[:3]

    @staticmethod
    def _strip_arabic_diacritics(s: str) -> str:
        """Remove Arabic diacritics (tashkeel) from text."""
        return re.sub(r'[\u0610-\u061A\u064B-\u065F\u0670]', '', s)

    async def _keyword_search(self, query: str, top_k: int = 3) -> str:
        """Fallback text search when embeddings are unavailable.

        Uses PostgreSQL regexp_replace to strip Arabic diacritics before
        ILIKE matching, so queries without tashkeel match stored text with it.
        """
        keywords = self._extract_keywords(query)
        if not keywords:
            return ""

        # Strip diacritics from keywords too (in case query has them)
        keywords = [self._strip_arabic_diacritics(kw) for kw in keywords]

        strip_expr = "COALESCE(pc.content_normalized, regexp_replace(pc.content, '[\u064B-\u065F\u0610-\u061A\u0670]', '', 'g'))"

        conditions = []
        params: dict = {
            "tenant_id": str(self.tenant_id),
            "top_k": top_k,
        }
        score_parts = []
        for i, kw in enumerate(keywords):
            param_name = f"kw_{i}"
            kw_escaped = kw.replace('%', '\\%').replace('_', '\\_')
            params[param_name] = f"%{kw_escaped}%"
            conditions.append(f"{strip_expr} ILIKE :{param_name}")
            score_parts.append(
                f"CASE WHEN {strip_expr} ILIKE :{param_name} THEN 1 ELSE 0 END"
            )

        where_clause = " OR ".join(conditions)
        score_expr = " + ".join(score_parts)

        sql = text(f"""
            SELECT pc.content, ({score_expr}) AS relevance
            FROM policy_chunks pc
            JOIN policies p ON pc.policy_id = p.id
            WHERE p.tenant_id = :tenant_id
              AND p.is_active = true
              AND ({where_clause})
            ORDER BY relevance DESC
            LIMIT :top_k
        """)

        result = await self.db.execute(sql, params)
        rows = result.fetchall()

        if not rows:
            logger.info(
                "Keyword search: no chunks found for tenant %s, query: %s",
                self.tenant_id,
                query[:80],
            )
            return ""

        chunks = [row[0] for row in rows]
        logger.info(
            "Keyword search: retrieved %d chunks for tenant %s",
            len(chunks),
            self.tenant_id,
        )
        return "\n\n---\n\n".join(chunks)

    async def search(self, query: str, top_k: int = 3) -> str:
        """Search policy chunks by semantic similarity and return concatenated text.

        Uses pgvector's cosine distance operator (<=>) to find the most relevant
        policy chunks for the given tenant. Falls back to keyword search if
        embeddings are unavailable.

        Args:
            query: The natural-language search query.
            top_k: Maximum number of chunks to return.

        Returns:
            Concatenated chunk text separated by newlines, or empty string if
            no relevant chunks are found.
        """
        if not settings.openai_api_key:
            return await self._keyword_search(query, top_k)

        try:
            query_embedding = await self._get_embedding(query)
        except httpx.HTTPStatusError as exc:
            logger.error("OpenAI embedding API error: %s", exc.response.text)
            return await self._keyword_search(query, top_k)
        except httpx.RequestError as exc:
            logger.error("Network error calling OpenAI embeddings: %s", exc)
            return await self._keyword_search(query, top_k)

        # Use raw SQL for pgvector cosine distance — SQLAlchemy ORM support
        # for vector operators is limited, and raw SQL is clearer here.
        sql = text("""
            SELECT pc.content
            FROM policy_chunks pc
            JOIN policies p ON pc.policy_id = p.id
            WHERE p.tenant_id = :tenant_id
              AND p.is_active = true
              AND pc.embedding IS NOT NULL
            ORDER BY pc.embedding <=> :embedding
            LIMIT :top_k
        """)

        # pgvector expects the embedding as a string representation of an array
        embedding_str = "[" + ",".join(str(v) for v in query_embedding) + "]"

        result = await self.db.execute(
            sql,
            {
                "tenant_id": str(self.tenant_id),
                "embedding": embedding_str,
                "top_k": top_k,
            },
        )
        rows = result.fetchall()

        if not rows:
            logger.info(
                "Vector search returned 0 rows for tenant %s, falling back to keyword search",
                self.tenant_id,
            )
            return await self._keyword_search(query, top_k)

        chunks = [row[0] for row in rows]
        logger.info(
            "Retrieved %d policy chunks for tenant %s", len(chunks), self.tenant_id
        )
        return "\n\n---\n\n".join(chunks)
