"""CV embedding indexer for the talent pool (pgvector-free).

Mirrors ``app.ai.retrieval.job_indexer`` for CVs, but stores vectors PORTABLY in
the ``cv_embeddings`` JSONB ``vector`` column so ranking runs in Python via
``top_k_by_cosine`` (no ``<=>`` operator, no pgvector). Local scale is hundreds of
consented CVs, so a full in-process scan is fine.

Cross-module boundary (``docs/ARCHITECTURE.md`` §8): CV content comes through
``documents.application.cv_index_facade`` and consent through
``student_profiles.application.talent_facade`` — this module never imports another
module's ``domain.models``.

Consent (owner follow-up — no dedicated flag yet): only students who are
DISCOVERABLE are indexed — ``is_open_to_work = True`` AND
``profile_visibility != private`` (enforced by ``talent_facade``). A first-class
``talent_pool_opt_in`` consent column is a recommended follow-up migration.

Idempotent: a row is keyed by ``(cv_id, model_alias)`` and only re-embedded when
the meaningful CV text (``text_hash``) changed — a re-run over an unchanged CV
spends zero embedding calls.
"""

from __future__ import annotations

import hashlib
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.retrieval.embeddings import embed_single
from app.core.config import get_settings
from app.modules.documents.application import cv_index_facade
from app.modules.student_profiles.application import talent_facade
from app.modules.talent_pool.domain import cv_text
from app.modules.talent_pool.domain.models import CvEmbedding


def _text_hash(text: str, *, alias: str) -> str:
    return hashlib.sha256(f"{alias}:{text}".encode()).hexdigest()


async def index_cv(
    session: AsyncSession,
    *,
    cv_id: uuid.UUID,
    model_alias: str | None = None,
    force: bool = False,
) -> bool:
    """(Re)index one CV's embedding. Idempotent, consent-gated.

    Returns ``True`` when a row was written/updated, ``False`` when skipped
    (not discoverable, not a ready CV, empty text, or unchanged content). Does NOT
    commit — the caller owns the transaction.
    """

    settings = get_settings()
    alias = model_alias or settings.ai_embedding_model_alias

    cv = await cv_index_facade.get_indexable_cv(session, cv_id=cv_id)
    if cv is None:
        # Not an indexable CV (missing / deleted / not ready) — remove any stale
        # vector so an archived/deleted CV never lingers in the pool.
        await remove_cv(session, cv_id=cv_id, model_alias=alias)
        return False

    if not await talent_facade.is_discoverable(session, user_id=cv.user_id):
        await remove_cv(session, cv_id=cv_id, model_alias=alias)
        return False

    content_text, skills, years = cv_text.project_cv(cv.sections)
    if not content_text.strip():
        await remove_cv(session, cv_id=cv_id, model_alias=alias)
        return False

    new_hash = _text_hash(content_text, alias=alias)
    existing = (
        await session.execute(
            select(CvEmbedding).where(
                CvEmbedding.cv_id == cv_id, CvEmbedding.model_alias == alias
            )
        )
    ).scalar_one_or_none()

    if existing is not None and existing.text_hash == new_hash and not force:
        return False  # unchanged — no re-embed

    vector = await embed_single(content_text, alias=alias)
    if not vector:
        return False

    if existing is None:
        existing = CvEmbedding(cv_id=cv_id, user_id=cv.user_id, model_alias=alias)
        session.add(existing)
    existing.snapshot_id = cv.snapshot_id
    existing.user_id = cv.user_id
    existing.content_version = cv.content_version
    existing.vector = list(vector)
    existing.skills = skills
    existing.experience_years = years
    existing.content_text = content_text
    existing.text_hash = new_hash
    await session.flush()
    return True


async def remove_cv(
    session: AsyncSession, *, cv_id: uuid.UUID, model_alias: str | None = None
) -> None:
    """Remove a CV's embedding row(s) (un-consent / archive / delete)."""

    stmt = select(CvEmbedding).where(CvEmbedding.cv_id == cv_id)
    if model_alias is not None:
        stmt = stmt.where(CvEmbedding.model_alias == model_alias)
    rows = (await session.execute(stmt)).scalars().all()
    for row in rows:
        await session.delete(row)
    if rows:
        await session.flush()


async def backfill_talent_pool(
    session: AsyncSession,
    *,
    model_alias: str | None = None,
    limit: int | None = None,
) -> dict:
    """Index every consented, discoverable ready CV.

    Entry point for a one-off backfill (script / management command). Resolves the
    discoverable users (student_profiles seam) then their ready CVs (documents
    seam) — no cross-module ORM join. Commits once at the end.
    """

    settings = get_settings()
    alias = model_alias or settings.ai_embedding_model_alias

    user_ids = await talent_facade.list_discoverable_user_ids(session)
    cv_ids = await cv_index_facade.list_ready_cv_ids_for_users(
        session, user_ids=user_ids, limit=limit
    )

    indexed = 0
    skipped = 0
    for cv_id in cv_ids:
        try:
            if await index_cv(session, cv_id=cv_id, model_alias=alias):
                indexed += 1
            else:
                skipped += 1
        except Exception:  # noqa: BLE001 — one bad CV must not abort the whole backfill
            skipped += 1
    await session.commit()
    return {"candidates": len(cv_ids), "indexed": indexed, "skipped": skipped}
