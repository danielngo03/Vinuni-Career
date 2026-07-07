"""Batch CV-to-job fit scoring for paginated job list pages.

Called once per page load after the frontend receives its paginated job list.
Returns a score dict keyed by job_id_str so the frontend can hydrate every card
in a single POST.

Design goals
------------
- ONE DB round-trip for the user's active CVs (shared across all jobs on the page).
- ONE DB round-trip to bulk-load the job rows that missed the Redis cache.
- Pure-Python deterministic scoring (<1 ms / job) — no LLM for this path.
- Redis TTL is the primary cache.  No DB write on a pure cache-hit page.

Security
--------
- Student persona + ``cv:read`` permission enforced before any data access.
- Results are private (user_id is embedded in the cache key).
- No AI provider / model / token / score internals leak into the response.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.cv import job_fit, skill_translation
from app.ai.cv.fit_cache import get_cached, set_cached
from app.modules.documents.application import _shared, fit_store
from app.modules.documents.application.job_fit_service import (
    _build_cv_input,
    _fit_to_result_payload,
    _load_active_cvs,
    _stale_days,
)
from app.modules.documents.domain.models import CvProfile
from app.modules.opportunities.application.visibility import apply_visible_filter
from app.modules.opportunities.domain import lifecycle
from app.modules.opportunities.domain.models import Job
from app.modules.organization.application import org_reporting_facade
from app.shared.permissions import Principal, permission_checker

_RESOURCE = _shared.RESOURCE

# Maximum job_ids accepted per request. The caller (frontend page) sends at most
# 50 job cards per page, but we enforce a hard server-side cap.
MAX_JOB_IDS = 50


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _job_projection(job: Job, org_display_name: str | None) -> dict:
    """Build the requirements dict for ``job_fit.evaluate``.

    Mirrors ``job_fit_read.load_job_for_fit``'s projection so scoring is
    consistent between the single-job and batch paths.  Only requirement /
    logistics / text fields are included — no internal status columns.
    """
    jd_text = " ".join(
        part
        for part in (job.title, job.description, job.requirements, job.benefits)
        if part
    )
    return {
        "id": str(job.id),
        # Internal content-version stamp for the persisted fit store (never surfaced).
        "version": job.version,
        "title": job.title,
        "company": {"display_name": org_display_name},
        "description": job.description,
        "requirements": job.requirements,
        "benefits": job.benefits,
        "required_skills": list(job.required_skills or []),
        "preferred_skills": list(job.preferred_skills or []),
        "experience_min_years": job.experience_min_years,
        "experience_max_years": job.experience_max_years,
        "experience_mode": job.experience_mode,
        "degree_required": job.degree_required,
        "seniority_level": job.seniority_level,
        "candidate_requirements": dict(job.candidate_requirements or {}),
        "employment_type": job.employment_type,
        "location_type": job.location_type,
        "location_city": job.location_city,
        "location_country": job.location_country,
        "locations": list(job.locations or []),
        "cv_language_required": getattr(job, "cv_language_required", "any") or "any",
        "jd_text": jd_text,
    }


def _card_from_rows(rows: list) -> dict:
    """Trimmed job-card payload from persisted fit rows (fast path).

    Ranks exactly like ``job_fit.evaluate`` (``-score``, ``-avg_skill_level``,
    ``last_updated_days``, ``cv_id``) so the recommended CV matches the detail path.
    """
    best = min(
        rows,
        key=lambda r: (-r.score, -r.avg_skill_level, r.last_updated_days, str(r.cv_id)),
    )
    return {
        "score": best.score,
        "recommended_cv_id": str(best.cv_id),
        "signal": best.signal,
        "stale": best.stale,
    }


async def _score_job(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    job: Job,
    job_dict: dict,
    cvs: list[CvProfile],
    cv_inputs: list[job_fit.CvInput],
) -> dict:
    """Return the lightweight card payload for one job, store-backed.

    Uses persisted fresh rows when every active CV has one; otherwise recomputes
    deterministically and upserts each CV row (still no LLM on this path). The
    response is intentionally trimmer than the full ``job_fit_for_job`` response
    (no per-CV breakdown, no bands, no explanation) — job-card badges need a
    score, recommended_cv_id, signal, and stale flag only.
    """
    job_version = int(job_dict.get("version") or 1)
    stored = await fit_store.load_rows(
        session,
        user_id=user_id,
        job_id=job.id,
        cv_ids=[cv.id for cv in cvs],
    )
    all_fresh = all(
        (row := stored.get(cv.id)) is not None
        and fit_store.is_fresh(row, cv_version=cv.version, job_version=job_version)
        for cv in cvs
    )
    if all_fresh and stored:
        return _card_from_rows(list(stored.values()))

    cv_by_id = {str(cv.id): cv for cv in cvs}
    # Cross-lingual (VN↔EN) matching on compute-miss only (fresh rows short-circuit
    # above). Translate every JD/CV skill term to canonical English and append the
    # English forms before scoring. Gated + best-effort: offline / error -> inputs
    # unchanged -> pure lexical score, which is what the store then persists.
    # CACHE-ONLY: batch card scoring covers a whole page of jobs. Blocking on a
    # per-job model translation would take tens of seconds (and time out the
    # request), so we use only already-warm translations; uncached terms fall back
    # to pure lexical. The single-job detail path (job_fit_for_job) still warms the
    # translation cache with real model calls.
    aug_job, aug_cv_inputs, aug_complete = await skill_translation.english_augment(
        job_dict, cv_inputs, allow_model_calls=False
    )
    outcome = job_fit.evaluate(
        aug_job, aug_cv_inputs, stale_days=_stale_days()
    )
    for fit in outcome.results:
        cv = cv_by_id[fit.cv_id]
        payload = _fit_to_result_payload(fit, signal=outcome.signal)
        # Degraded (AI-on-but-translation-failed) scores persist provisionally so
        # the next request retries instead of caching a degraded score as final.
        await fit_store.upsert_result(
            session,
            user_id=user_id,
            cv_id=cv.id,
            job_id=job.id,
            result=payload,
            cv_version=cv.version,
            job_version=job_version,
            provisional=not aug_complete,
        )
    best = outcome.results[0] if outcome.results else None
    return {
        "score": best.score if best else 0,
        "recommended_cv_id": outcome.recommended_cv_id,
        "signal": outcome.signal,
        "stale": best.stale if best else False,
    }


async def batch_fit_for_jobs(
    session: AsyncSession,
    redis: object,
    *,
    principal: Principal,
    job_ids: list[uuid.UUID],
) -> dict[str, dict]:
    """Return fit scores for up to ``MAX_JOB_IDS`` jobs in a single call.

    Response shape::

        {
            "<job_id>": {
                "score": int,           # 0-100 product score
                "recommended_cv_id": str | null,
                "signal": str,          # "ok" | "low_signal"
                "stale": bool,
            },
            ...
        }

    Absent entries (job not found / not visible) are silently omitted; the
    frontend falls back to rendering no badge for that card.

    Algorithm
    ---------
    1. Permission gate (student + cv:read).
    2. Deduplicate + cap job_ids.
    3. ONE query for the user's active CVs.
    4. Short-circuit when user has no active CVs — return empty dict for all.
    5. Check Redis for each job_id.  Collect misses.
    6. ONE bulk query for all cache-miss jobs (visible filter applied).
    7. For each loaded job: compute score, write to Redis.
    8. Return merged dict {job_id_str: score_payload}.
    """
    permission_checker.require(principal, _RESOURCE, "read")
    assert principal.user_id is not None

    # Deduplicate and enforce cap without raising — silently truncate.
    seen: set[uuid.UUID] = set()
    deduped: list[uuid.UUID] = []
    for jid in job_ids:
        if jid not in seen:
            seen.add(jid)
            deduped.append(jid)
            if len(deduped) >= MAX_JOB_IDS:
                break

    if not deduped:
        return {}

    # 1. Load active CVs — single query shared across all jobs.
    cvs = await _load_active_cvs(session, user_id=principal.user_id)
    if not cvs:
        return {}

    now = _now()
    cv_inputs = [await _build_cv_input(session, cv=cv, now=now) for cv in cvs]

    # Signature of the user's CV library — changes whenever any CV is
    # added/edited/deleted (every mutation bumps ``cv.version``), so a cached
    # badge built against an older library is a miss.
    cv_sig = ";".join(sorted(f"{cv.id}:{cv.version}" for cv in cvs))

    # Job version map (id + version only — lightweight) so the cache signature
    # also tracks JD edits (``job.version`` bumps on every real amendment).
    ver_rows = await session.execute(
        select(Job.id, Job.version).where(Job.id.in_(deduped))
    )
    job_versions: dict[uuid.UUID, int] = {row.id: row.version for row in ver_rows}

    def _sig(job_id: uuid.UUID) -> str:
        return f"{job_fit.SCORER_VERSION}:{job_versions.get(job_id, 'x')}:{cv_sig}"

    # 2. Check Redis cache (self-validating on the content signature).
    scores: dict[str, dict] = {}
    misses: list[uuid.UUID] = []

    for jid in deduped:
        cached = await get_cached(redis, principal.user_id, jid, sig=_sig(jid))
        if cached is not None:
            scores[str(jid)] = cached
        else:
            misses.append(jid)

    if not misses:
        return scores

    # 3. Bulk load missing jobs — one query, visibility-filtered (same predicate
    #    as ``load_job_for_fit`` so hidden/closed jobs score as if missing).
    levels = lifecycle.visible_levels_for("student", is_authenticated=True)
    stmt = apply_visible_filter(
        select(Job).where(Job.id.in_(misses)),
        levels=levels,
        now=now,
    )
    loaded_jobs = list((await session.execute(stmt)).scalars().all())

    # 4. Fetch org names for loaded jobs — one query per distinct org_id.
    org_ids = {job.org_id for job in loaded_jobs}
    org_names: dict[uuid.UUID, str | None] = {}
    for org_id in org_ids:
        org = await org_reporting_facade.summary_for(session, org_id)
        org_names[org_id] = org.display_name if org else None

    # 5. Score each loaded job (store-backed) and populate Redis.
    for job in loaded_jobs:
        job_dict = _job_projection(job, org_names.get(job.org_id))
        result = await _score_job(
            session,
            user_id=principal.user_id,
            job=job,
            job_dict=job_dict,
            cvs=cvs,
            cv_inputs=cv_inputs,
        )
        scores[str(job.id)] = result
        await set_cached(redis, principal.user_id, job.id, result, sig=_sig(job.id))

    # Persist any fit rows upserted on cache-miss jobs. A commit with no dirty
    # rows (every miss hit its fresh store row) issues no SQL, so a fully cached
    # page still does zero DB writes. Pure cache-hit pages return above.
    await session.commit()

    return scores
