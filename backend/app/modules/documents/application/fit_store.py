"""Persisted, version-stamped CV-JD fit-score store (repository layer).

The deterministic 6-criteria product score and the optional AI ``explanation`` are
persisted per ``(cv_id, job_id)`` in ``cv_job_fit_scores``, stamped with the CV
and JD content versions and the deterministic ``scorer_version`` at compute time.

Freshness contract
------------------
A stored row is REUSED (not recomputed) while all three stamps still match the
live inputs (``is_fresh``). The score/bands are recomputed only when the CV or JD
content version changes, or when ``job_fit.SCORER_VERSION`` is bumped. The
expensive LLM explanation is regenerated only when the row is stale OR the
explanation was produced by a different prompt version / output language
(``has_fresh_explanation``) — so a page reload reuses the stored explanation and
never re-invokes the model.

PII-safety
----------
Only the user-facing ``explanation`` text is stored. No provider/model/token/
prompt/embedding internals ever reach this table — the caller passes the
already-scrubbed summary string.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.cv import job_fit
from app.modules.documents.domain.models import CvFitExplanationCache, CvJobFitScore

# Sentinel appended to ``scorer_version`` for a PROVISIONAL (degraded) row so
# ``is_fresh`` never matches it and the next read recomputes (retries). Contains a
# character never present in a real ``SCORER_VERSION`` so it cannot collide.
_PROVISIONAL_SUFFIX = "~provisional"


def is_fresh(row: CvJobFitScore, *, cv_version: int, job_version: int) -> bool:
    """A row is fresh when its CV/JD/scorer stamps all match the live inputs."""
    return (
        row.cv_version == cv_version
        and row.job_version == job_version
        and row.scorer_version == job_fit.SCORER_VERSION
    )


def has_fresh_explanation(
    row: CvJobFitScore, *, prompt_version: int, lang: str
) -> bool:
    """Whether the row already holds a reusable explanation.

    Caller is responsible for confirming the row itself is fresh
    (``is_fresh``) first; this only checks the explanation dimensions
    (present + same prompt version + same output language).
    """
    return (
        row.explanation is not None
        and row.explanation_prompt_version == prompt_version
        and row.explanation_lang == lang
    )


async def load_rows(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    job_id: uuid.UUID,
    cv_ids: list[uuid.UUID],
) -> dict[uuid.UUID, CvJobFitScore]:
    """Fetch existing stored rows for ``cv_ids`` against ``job_id``.

    Scoped by ``user_id`` as a tenant-isolation guard even though
    ``(cv_id, job_id)`` is already unique. Returns a ``{cv_id: row}`` map;
    missing pairs are simply absent.
    """
    if not cv_ids:
        return {}
    stmt = select(CvJobFitScore).where(
        CvJobFitScore.user_id == user_id,
        CvJobFitScore.job_id == job_id,
        CvJobFitScore.cv_id.in_(cv_ids),
    )
    rows = (await session.execute(stmt)).scalars().all()
    return {row.cv_id: row for row in rows}


async def upsert_result(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    cv_id: uuid.UUID,
    job_id: uuid.UUID,
    result: dict,
    cv_version: int,
    job_version: int,
    provisional: bool = False,
) -> CvJobFitScore:
    """Insert or update the DETERMINISTIC fields for ``(cv_id, job_id)``.

    Stamps ``cv_version`` / ``job_version`` / ``scorer_version`` / ``computed_at``
    so the row's freshness can be checked later. An existing FRESH explanation is
    NOT clobbered: the explanation columns are only reset when the stamps actually
    move (the content changed), which is exactly when the cached explanation must
    be regenerated anyway.

    ``result`` carries the deterministic payload
    (``score``/``bands``/``matched_skills``/``gaps``/``signal``/``stale``/
    ``last_updated_days``).
    """
    now = datetime.now(tz=UTC)
    existing = (
        await session.execute(
            select(CvJobFitScore).where(
                CvJobFitScore.cv_id == cv_id,
                CvJobFitScore.job_id == job_id,
            )
        )
    ).scalar_one_or_none()

    stamps_changed = existing is None or not is_fresh(
        existing, cv_version=cv_version, job_version=job_version
    )

    if existing is None:
        row = CvJobFitScore(
            user_id=user_id,
            cv_id=cv_id,
            job_id=job_id,
        )
        session.add(row)
    else:
        row = existing
        # Keep ownership authoritative (defensive; cv_id is already user-scoped).
        row.user_id = user_id

    row.score = int(result["score"])
    row.bands = dict(result["bands"])
    row.matched_skills = list(result["matched_skills"])
    row.gaps = list(result["gaps"])
    row.signal = str(result["signal"])
    row.stale = bool(result["stale"])
    row.last_updated_days = int(result["last_updated_days"])
    row.avg_skill_level = float(result.get("avg_skill_level", 50.0))
    row.cv_version = cv_version
    row.job_version = job_version
    # A PROVISIONAL row (AI was on but a cross-lingual translation failed, so the
    # score is degraded to lexical-only) is stamped with a sentinel scorer_version
    # that ``is_fresh`` never matches — so the next read RECOMPUTES (retries the
    # translation) instead of serving the degraded score forever. A later complete
    # compute overwrites it with the real ``SCORER_VERSION`` and it caches normally.
    row.scorer_version = (
        f"{job_fit.SCORER_VERSION}{_PROVISIONAL_SUFFIX}"
        if provisional
        else job_fit.SCORER_VERSION
    )
    row.computed_at = now

    if stamps_changed:
        # Content moved (or brand-new row): any cached explanation no longer
        # describes the current score, so drop it (and its structured detail) and
        # let the caller regenerate.
        row.explanation = None
        row.explanation_structured = None
        row.explanation_prompt_version = None
        row.explanation_lang = None
        row.explanation_generated_at = None

    await session.flush()
    return row


async def save_explanation(
    session: AsyncSession,
    *,
    cv_id: uuid.UUID,
    job_id: uuid.UUID,
    explanation: str,
    prompt_version: int,
    lang: str,
    structured: dict | None = None,
) -> None:
    """Persist the AI explanation for ``(cv_id, job_id)`` — explanation fields only.

    The deterministic score/bands are left untouched. ``structured`` is the
    leak-safe per-requirement matching detail (``semantic_scorer.analysis_payload``)
    for THIS CV; it is stored on the row and defaults to ``None`` (e.g. a cross-CV
    summary reuse carries no CV-specific structured detail). No-op if the row is
    missing (it is always upserted first by the caller).
    """
    row = (
        await session.execute(
            select(CvJobFitScore).where(
                CvJobFitScore.cv_id == cv_id,
                CvJobFitScore.job_id == job_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        return
    row.explanation = explanation
    row.explanation_structured = structured
    row.explanation_prompt_version = prompt_version
    row.explanation_lang = lang
    row.explanation_generated_at = datetime.now(tz=UTC)
    await session.flush()


# --------------------------------------------------------------------------- #
# Cross-CV explanation reuse cache (the "learning" cache)                       #
# --------------------------------------------------------------------------- #
#
# At scale many DIFFERENT students apply to the SAME popular JD. Two CVs that
# produce the SAME deterministic evidence (matched skills + gaps) against the
# SAME JD version share ONE generated explanation, so the second CV reuses the
# first CV's summary at 0 extra tokens instead of triggering its own LLM call.
#
# The reused text is REQUIREMENT-CENTRIC / CV-AGNOSTIC by construction (prompt v3
# rule 9), so it can never leak another CV's unique details.


def explanation_fingerprint(
    *,
    job_id: uuid.UUID,
    job_version: int,
    matched_skills: list[str],
    gaps: list[str],
    prompt_version: int,
    lang: str,
) -> str:
    """Stable content fingerprint (sha256 hex) for a reusable fit explanation.

    Two CVs that yield the SAME deterministic matched skills + gaps against the
    SAME JD version (for the same prompt version + output language) map to the
    SAME fingerprint, so they can share one generated explanation. Both lists are
    SORTED first so ordering is irrelevant — the evidence set is what matters.
    """
    matched_part = "|".join(sorted(matched_skills))
    gaps_part = "|".join(sorted(gaps))
    raw = f"{job_id}|{job_version}|{matched_part}|{gaps_part}|{prompt_version}|{lang}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def get_reusable_explanation(
    session: AsyncSession, *, fingerprint: str
) -> str | None:
    """Return the cached explanation for ``fingerprint`` (and bump ``hit_count``).

    A hit means a DIFFERENT CV already generated an equivalent explanation for
    the same JD/evidence — the caller reuses it and skips the LLM (0 tokens).
    Returns ``None`` on a miss.
    """
    row = (
        await session.execute(
            select(CvFitExplanationCache).where(
                CvFitExplanationCache.fingerprint == fingerprint
            )
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    row.hit_count = (row.hit_count or 0) + 1
    await session.flush()
    return row.explanation


async def put_reusable_explanation(
    session: AsyncSession,
    *,
    fingerprint: str,
    explanation: str,
    prompt_version: int,
    lang: str,
) -> None:
    """Upsert a freshly generated explanation into the cross-CV reuse cache.

    PII-safe: only the requirement-centric explanation text is stored (plus the
    prompt version / language it was generated for). No user/cv id, provider,
    model, token, or prompt internals.
    """
    row = (
        await session.execute(
            select(CvFitExplanationCache).where(
                CvFitExplanationCache.fingerprint == fingerprint
            )
        )
    ).scalar_one_or_none()
    if row is None:
        session.add(
            CvFitExplanationCache(
                fingerprint=fingerprint,
                explanation=explanation,
                prompt_version=prompt_version,
                lang=lang,
                hit_count=0,
            )
        )
    else:
        row.explanation = explanation
        row.prompt_version = prompt_version
        row.lang = lang
    await session.flush()
