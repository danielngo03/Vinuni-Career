"""Hybrid search: BM25 full-text + dense vector retrieval fused via RRF.

Pipeline:
  1. BM25 (Postgres ``tsvector`` + ``ts_rank``) retrieves text-keyword matches.
  2. Dense vector search (pgvector cosine) retrieves semantic matches.
  3. Reciprocal Rank Fusion merges both ranked lists into a single score.
  4. Optional: top-k result set can be further reranked by a cross-encoder
     (see ``rerank.py``) before returning.

When pgvector is disabled, only BM25 runs and its scores are returned directly.
When no full-text index exists, only vector scores are used.
"""

from __future__ import annotations

import json
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.retrieval.job_indexer import search_by_embedding
from app.core.config import get_settings

# RRF constant (Cormack 2009 recommend 60 for IR tasks)
_RRF_K = 60


def _rrf_score(rank: int) -> float:
    """Reciprocal Rank Fusion score for a single-list rank (1-indexed)."""
    return 1.0 / (_RRF_K + rank)


def fuse_rrf(
    bm25_ids: list[uuid.UUID],
    vector_ids: list[tuple[uuid.UUID, float]],
    *,
    bm25_weight: float = 0.4,
    vector_weight: float = 0.6,
) -> list[tuple[uuid.UUID, float]]:
    """Merge two ranked lists using Reciprocal Rank Fusion.

    Args:
        bm25_ids: Job IDs from BM25, ordered by relevance (most relevant first).
        vector_ids: ``(job_id, raw_score)`` from dense search, ordered by score.
        bm25_weight: Weight multiplier applied to BM25 RRF contribution.
        vector_weight: Weight multiplier applied to vector RRF contribution.

    Returns:
        Merged list of ``(job_id, fused_score)`` sorted by descending score.
    """
    scores: dict[uuid.UUID, float] = {}

    for rank, jid in enumerate(bm25_ids, start=1):
        scores[jid] = scores.get(jid, 0.0) + bm25_weight * _rrf_score(rank)

    for rank, (jid, _raw) in enumerate(vector_ids, start=1):
        scores[jid] = scores.get(jid, 0.0) + vector_weight * _rrf_score(rank)

    return sorted(scores.items(), key=lambda t: -t[1])


async def bm25_job_search(
    session: AsyncSession,
    *,
    query: str,
    limit: int = 30,
    province_code: str | None = None,
) -> list[uuid.UUID]:
    """Full-text BM25 search over jobs using Postgres ``tsvector``.

    Uses the ``tsv_search`` generated column on ``jobs`` (created by migration
    0004). Falls back to a plain ``ILIKE`` title scan if full-text is
    unavailable. An optional ``province_code`` filter matches the
    ``locations[].province_code`` JSONB array (jobs has no top-level
    ``province_code`` column).

    Each query attempt runs inside a SAVEPOINT so a DB-level failure (e.g. a
    missing column on an older snapshot) rolls back only the savepoint and never
    poisons the caller's request transaction.

    Returns a list of job UUIDs ordered by relevance.
    """
    q = query.strip()
    if not q:
        return []

    # Optional province filter: jobs store locations as a JSONB array of
    # ``{"province_code": ...}`` objects (see job_alert_dispatch_service), so
    # containment is the correct predicate — there is no scalar column.
    province_clause = ""
    prov_params: dict = {}
    if province_code:
        province_clause = "AND locations @> :prov_json ::jsonb"
        prov_params["prov_json"] = json.dumps([{"province_code": province_code}])

    # Build a ts_query from the raw query string (websearch_to_tsquery is lenient)
    base_query = text(
        f"""
        SELECT id
        FROM jobs
        WHERE
            deleted_at IS NULL
            AND status = 'active'
            AND (
                tsv_search @@ websearch_to_tsquery('simple', :q)
                OR title ILIKE '%' || :q_raw || '%'
            )
            {province_clause}
        ORDER BY ts_rank(tsv_search, websearch_to_tsquery('simple', :q)) DESC,
                 created_at DESC
        LIMIT :limit
    """
    )

    nested = None
    try:
        nested = await session.begin_nested()
        rows = await session.execute(
            base_query,
            {"q": q, "q_raw": q, "limit": limit, **prov_params},
        )
        result = [uuid.UUID(str(row.id)) for row in rows]
        await nested.commit()
        return result
    except Exception:
        # Full-text column may be unavailable on some DB snapshots — degrade
        # gracefully. Roll back the savepoint first so the fallback (and the
        # caller's transaction) run on a clean connection.
        if nested is not None and nested.is_active:
            await nested.rollback()

    fallback_query = text(
        f"""
        SELECT id FROM jobs
        WHERE deleted_at IS NULL AND status = 'active'
          AND title ILIKE '%' || :q || '%'
          {province_clause}
        ORDER BY created_at DESC
        LIMIT :limit
    """
    )
    nested_fb = None
    try:
        nested_fb = await session.begin_nested()
        rows = await session.execute(
            fallback_query, {"q": q, "limit": limit, **prov_params}
        )
        result = [uuid.UUID(str(row.id)) for row in rows]
        await nested_fb.commit()
        return result
    except Exception:
        if nested_fb is not None and nested_fb.is_active:
            await nested_fb.rollback()
        return []


async def hybrid_job_search(
    session: AsyncSession,
    *,
    query: str,
    limit: int = 10,
    province_code: str | None = None,
    bm25_weight: float = 0.4,
    vector_weight: float = 0.6,
) -> list[tuple[uuid.UUID, float]]:
    """Run BM25 + dense vector search and fuse results with RRF.

    When pgvector is disabled, returns BM25 results with uniform score 1.0.
    When the query is empty, returns an empty list.

    Args:
        query: User search string (raw, not normalized).
        limit: Maximum number of results.
        province_code: Optional province filter applied only to the BM25 leg.
        bm25_weight: RRF weight for BM25 contributions (default 0.4).
        vector_weight: RRF weight for dense vector contributions (default 0.6).

    Returns:
        List of ``(job_id, fused_score)`` sorted by descending fused score.
    """
    if not query.strip():
        return []

    settings = get_settings()
    bm25_limit = max(limit * 3, 30)  # retrieve more candidates for fusion
    vector_limit = max(limit * 3, 30)

    bm25_ids = await bm25_job_search(
        session, query=query, limit=bm25_limit, province_code=province_code
    )

    if settings.pgvector_enabled:
        vector_results = await search_by_embedding(session, query_text=query, limit=vector_limit)
    else:
        vector_results = []

    if not bm25_ids and not vector_results:
        return []

    fused = fuse_rrf(
        bm25_ids,
        vector_results,
        bm25_weight=bm25_weight,
        vector_weight=vector_weight,
    )
    return fused[:limit]
