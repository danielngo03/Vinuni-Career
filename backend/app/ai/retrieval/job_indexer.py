"""Job embedding indexer: write and query vectors in the ``job_embeddings`` table.

When ``PGVECTOR_ENABLED=false`` (or the table doesn't exist) the indexer is a
no-op on writes and returns empty results on reads — callers fall back to
keyword/BM25 search automatically.
"""

from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.retrieval.embeddings import embed_single
from app.core.config import get_settings


async def _pgvector_ready(session: AsyncSession) -> bool:
    if not get_settings().pgvector_enabled:
        return False
    bind = session.get_bind()
    if bind.dialect.name != "postgresql":
        return False
    try:
        row = (
            await session.execute(
                text("""
                    SELECT
                      EXISTS (
                        SELECT 1 FROM pg_extension WHERE extname = 'vector'
                      )
                      AND EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_name = 'job_embeddings'
                          AND column_name = 'vector'
                          AND udt_name = 'vector'
                      ) AS ready
                """)
            )
        ).first()
        return bool(row and row.ready)
    except Exception:
        return False


async def index_job_embedding(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    text_to_embed: str,
    model_alias: str | None = None,
) -> bool:
    """Upsert the embedding for a single job.

    The text passed should be a normalised concatenation of the job's title,
    description, required skills, and preferred skills — assembled by the caller
    so this function stays model/schema agnostic.

    Returns ``True`` if the embedding was written, ``False`` otherwise (e.g.
    when pgvector is disabled or AI calls are off).
    """
    if not await _pgvector_ready(session):
        return False

    settings = get_settings()
    alias = model_alias or settings.ai_embedding_model_alias

    try:
        vector = await embed_single(text_to_embed, alias=alias)
    except Exception:
        return False

    if not vector:
        return False

    # Store as a Postgres array literal — pgvector accepts ARRAY[...] or '[...]'::vector
    vec_literal = "[" + ",".join(f"{v:.8f}" for v in vector) + "]"
    await session.execute(
        text("""
            INSERT INTO job_embeddings (job_id, model_alias, vector)
            VALUES (:job_id, :model_alias, :vector::vector)
            ON CONFLICT (job_id)
            DO UPDATE SET vector = EXCLUDED.vector, model_alias = EXCLUDED.model_alias,
                          updated_at = now()
        """),
        {"job_id": str(job_id), "model_alias": alias, "vector": vec_literal},
    )
    return True


async def search_by_embedding(
    session: AsyncSession,
    *,
    query_text: str,
    limit: int = 20,
    model_alias: str | None = None,
) -> list[tuple[uuid.UUID, float]]:
    """Return ``(job_id, score)`` pairs ordered by cosine similarity to ``query_text``.

    Falls back to an empty list when pgvector is disabled so callers can chain
    to BM25 / full-text search transparently.
    """
    if not await _pgvector_ready(session):
        return []

    settings = get_settings()
    alias = model_alias or settings.ai_embedding_model_alias

    try:
        q_vector = await embed_single(query_text, alias=alias)
    except Exception:
        return []

    if not q_vector:
        return []

    vec_literal = "[" + ",".join(f"{v:.8f}" for v in q_vector) + "]"

    # Use pgvector's <=> (cosine distance) operator — lower is more similar.
    rows = await session.execute(
        text("""
            SELECT job_id, 1 - (vector <=> :qvec::vector) AS score
            FROM job_embeddings
            ORDER BY vector <=> :qvec::vector
            LIMIT :limit
        """),
        {"qvec": vec_literal, "limit": limit},
    )

    return [
        (uuid.UUID(str(row.job_id)), float(row.score))
        for row in rows
    ]


async def delete_job_embedding(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
) -> None:
    """Remove the embedding for a job (called on job delete)."""
    if not await _pgvector_ready(session):
        return
    await session.execute(
        text("DELETE FROM job_embeddings WHERE job_id = :job_id"),
        {"job_id": str(job_id)},
    )
