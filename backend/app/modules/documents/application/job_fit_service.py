"""CV-to-job fit scoring + best-CV recommendation (documents module).

The headline student feature: given a target job, score every one of the
caller's ACTIVE CVs against the job's requirements and recommend the best one to
apply with (``docs/BUSINESS_LOGIC.md`` §4B.3B; ``docs/CV_STUDIO_SPEC.md``
§recommend).

Guarantees:

- The ``score`` (0-100) and the per-category ``bands`` are DETERMINISTIC — pure
  functions of the structured job requirements and the CV content
  (``app.ai.cv.job_fit``). Same inputs -> identical scores, every time.
- The AI ``explanation`` is OPTIONAL enrichment only: a short, grounded "why /
  what to improve" string for the recommended CV, produced through the gateway
  and scrubbed by the output guard. Under the default offline provider (or any
  provider failure) it degrades to ``explanation: null`` +
  ``ai_explanation_available: false`` while the full deterministic results are
  still returned.
- Owner-only (reads the caller's own ``cv:read`` library). This is a read; no
  audit write. Any AI call is logged PII-safely as metadata via the gateway.
- Never exposes provider/model/token/latency/raw confidence/embedding internals:
  the number is a product score, not a model confidence.
"""

from __future__ import annotations

import asyncio
import copy
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.cv import job_fit, semantic_scorer, skill_translation
from app.ai.cv.grounding import sections_to_text as _cv_sections_to_text
from app.ai.gateway import runtime_config
from app.ai.gateway.factory import real_provider_active
from app.core.config import get_settings
from app.modules.documents.application import _cv_core, _shared, fit_store
from app.modules.documents.domain import catalog
from app.modules.documents.domain.models import CvJobFitScore, CvProfile, CvSection
from app.modules.opportunities.application import job_fit_read
from app.shared.exceptions import ResourceNotFoundError
from app.shared.permissions import Principal, permission_checker

_RESOURCE = _shared.RESOURCE
TASK_TYPE = "recommend_cv_for_job"


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


async def _load_active_cvs(session: AsyncSession, *, user_id: uuid.UUID) -> list[CvProfile]:
    """The caller's matchable CV library: committed (``ready``), not soft-deleted.

    Only CVs the student has committed to their library (status ``ready`` —
    finalized template CVs + upload imports) are analyzed and eligible for
    CV-JD matching (design spec 2026-07-05). Unlimited scratch drafts and archived
    CVs are excluded, so job-fit never scores a CV the student cannot actually
    apply with.
    """

    stmt = (
        select(CvProfile)
        .where(
            CvProfile.user_id == user_id,
            CvProfile.deleted_at.is_(None),
            CvProfile.status == catalog.CV_READY,
        )
        .order_by(CvProfile.last_edited_at.desc(), CvProfile.id)
    )
    return list((await session.execute(stmt)).scalars().all())


def _section_dict(s: CvSection) -> dict:
    return {
        "section_type": s.section_type,
        "title": s.title,
        "content": s.content_json or {},
    }


def _last_updated_days(cv: CvProfile, sections: list[CvSection], *, now: datetime) -> int:
    stamps = [_as_utc(cv.last_edited_at)]
    stamps.extend(_as_utc(s.updated_at) for s in sections)
    latest = max((s for s in stamps if s is not None), default=None)
    if latest is None:
        return 0
    return max(0, (now - latest).days)


def _fast_last_updated_days(mj: dict, *, now: datetime) -> int:
    """``last_updated_days`` from the snapshot's stored ``last_activity_at``.

    Equals the live ``_last_updated_days`` while the snapshot is fresh: the stored
    timestamp IS the ``max(cv.last_edited_at, section.updated_at)`` computed at
    analysis time, and a fresh snapshot means neither has changed since.
    """
    raw = mj.get("last_activity_at")
    if not isinstance(raw, str):
        return 0
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return 0
    latest = _as_utc(parsed)
    return max(0, (now - latest).days) if latest is not None else 0


async def _build_cv_input(
    session: AsyncSession, *, cv: CvProfile, now: datetime
) -> job_fit.CvInput:
    # FAST PATH (B-596): a committed CV carries a version-stamped matching snapshot
    # (``cv_profiles.matching_json``) that is a byte-identical projection of the
    # sections the scorer consumes. When it is FRESH — its ``content_version`` still
    # equals the live CV version (any edit bumps the version and invalidates it) —
    # rebuild the input from it and skip the section load. Sections are DEEP-COPIED
    # so upstream cross-lingual augmentation can never mutate the stored JSON. The
    # snapshot is byte-identical to a live load, so the deterministic score is
    # unchanged; a missing/stale/legacy snapshot falls through to the live load.
    mj = cv.matching_json
    if (
        isinstance(mj, dict)
        and mj.get("content_version") == cv.version
        and isinstance(mj.get("sections"), list)
    ):
        return job_fit.CvInput(
            cv_id=str(cv.id),
            title=cv.title,
            language=cv.language or "vi",
            sections=copy.deepcopy(mj["sections"]),
            last_updated_days=_fast_last_updated_days(mj, now=now),
        )

    sections = await _cv_core._load_sections(session, cv_id=cv.id)
    return job_fit.CvInput(
        cv_id=str(cv.id),
        title=cv.title,
        language=cv.language or "vi",
        sections=[_section_dict(s) for s in sections],
        last_updated_days=_last_updated_days(cv, sections, now=now),
    )


async def _maybe_semantic_analyze(
    job: dict,
    best_cv_input: job_fit.CvInput,
    deterministic_score: int,
    matched_skills: list[str],
    gaps: list[str],
) -> semantic_scorer.SemanticFitResult | None:
    """LLM semantic analysis for the recommended CV — one call per request.

    The product ``score`` is ALWAYS the deterministic 6-criteria ``job_fit.py`` score;
    the LLM never moves it (owner decision 2026-07-06). This call is used ONLY for
    its natural-language ``summary`` explaining the match in the CV's own language —
    any ``score`` the model returns on ``SemanticFitResult`` is discarded by the
    caller. (There is deliberately NO 40/60 blend; do not reintroduce one.)
    Guarded by the same two gates as the old plain-text explanation:
      1. ``real_provider_active()`` — env ceiling + key presence + DB toggle.
      2. ``job_fit_ai_explanation_enabled`` — admin feature flag (ADR-0011 §2).

    Returns ``None`` on gate-off or any provider failure so the caller always
    has a complete deterministic result to fall back to.
    """
    if not real_provider_active() or not runtime_config.current().job_fit_ai_explanation_enabled:
        return None
    try:
        cv_text = _cv_sections_to_text(best_cv_input.sections)
        return await asyncio.wait_for(
            semantic_scorer.analyze(
                job=job,
                cv_text=cv_text,
                cv_language=best_cv_input.language,
                deterministic_score=deterministic_score,
                matched_skills=matched_skills,
                gaps=gaps,
            ),
            timeout=20.0,
        )
    except Exception:  # noqa: BLE001 - semantic is advisory; never crash caller
        return None


def _fit_to_result_payload(fit: job_fit.CvFit, *, signal: str) -> dict:
    """The deterministic store payload (no explanation) from a fresh compute.

    ``signal`` is the job-level fit signal (``ok`` / ``low_signal``) — identical
    across a job's rows; it is denormalized onto each row so the fast path can
    rebuild the response without re-deriving requirements.
    """
    return {
        # The product score is ALWAYS the deterministic 6-criteria score: fully
        # reproducible, free, and identical on every reload. The LLM never moves
        # the number — it only contributes the natural-language ``explanation``
        # (owner decision 2026-07-06). This is what makes the score defensible
        # and stable across page refreshes.
        "score": fit.score,
        "bands": fit.bands.as_dict(),
        "matched_skills": fit.matched_skills,
        "gaps": fit.gaps,
        "signal": signal,
        "stale": fit.stale,
        "last_updated_days": fit.last_updated_days,
        # Persisted for consistent tie-break ranking on the fast path (never
        # surfaced to the user, never part of the score).
        "avg_skill_level": fit.avg_skill_level,
    }


def _present_from_row(row: CvJobFitScore, *, title: str, explanation: str | None) -> dict:
    """Build the user-facing per-CV result from a stored fit row."""
    return {
        "cv_id": str(row.cv_id),
        "title": title,
        "score": row.score,
        "bands": dict(row.bands or {}),
        "matched_skills": list(row.matched_skills or []),
        "gaps": list(row.gaps or []),
        "stale": row.stale,
        "last_updated_days": row.last_updated_days,
        "explanation": explanation,
    }


async def _resolve_explanation_for_row(
    session: AsyncSession,
    *,
    job: dict,
    job_id: uuid.UUID,
    job_version: int,
    recommended_row: CvJobFitScore,
    best_cv: CvProfile,
    now: datetime,
) -> tuple[str | None, bool]:
    """Reuse-or-generate the AI explanation for ONE recommended CV row.

    This is the single, shared explanation block used by BOTH the (opt-in)
    ``job_fit_for_job(with_explanation=True)`` slow path and the async
    ``fit_explanation_for_job`` endpoint, so the two call sites run byte-for-byte
    identical logic (no duplication):

    1. Fresh row-level explanation (same content version + prompt + lang) -> REUSE.
    2. Cross-CV "learning" cache hit (same JD version + same deterministic
       evidence) -> stamp onto this row, SKIP the LLM.
    3. Otherwise, if both AI gates are open, generate once (20s timeout), persist
       the row explanation, and seed the cross-CV cache.

    Returns ``(explanation, ai_explanation_available)``. On gate-off or any
    provider failure -> ``(None, False)`` — never raises (user-safe).
    Callers are responsible for committing the session.
    """
    lang = best_cv.language or "vi"
    prompt_version = semantic_scorer.PROMPT_VERSION
    matched_skills = list(recommended_row.matched_skills or [])
    gaps = list(recommended_row.gaps or [])

    if fit_store.has_fresh_explanation(recommended_row, prompt_version=prompt_version, lang=lang):
        # Fresh cached explanation for THIS (cv, job) content version on the
        # row itself — REUSE, no LLM.
        return recommended_row.explanation, True

    if not (real_provider_active() and runtime_config.current().job_fit_ai_explanation_enabled):
        # AI gate off -> deterministic-only, no explanation. Never raise.
        return None, False

    # CROSS-CV REUSE ("learning" cache): a DIFFERENT CV may have already
    # generated an equivalent, requirement-centric explanation for the
    # SAME JD version + SAME deterministic evidence. The reused text is
    # CV-agnostic by construction (prompt v3 rule 9), so sharing it can
    # never leak another CV's unique details.
    fingerprint = fit_store.explanation_fingerprint(
        job_id=job_id,
        job_version=job_version,
        matched_skills=matched_skills,
        gaps=gaps,
        prompt_version=prompt_version,
        lang=lang,
    )
    reused = await fit_store.get_reusable_explanation(session, fingerprint=fingerprint)
    if reused is not None:
        # Cross-CV cache hit -> stamp it onto this row; SKIP the LLM.
        await fit_store.save_explanation(
            session,
            cv_id=best_cv.id,
            job_id=job_id,
            explanation=reused,
            prompt_version=prompt_version,
            lang=lang,
        )
        return reused, True

    best_input = await _build_cv_input(session, cv=best_cv, now=now)
    # The deterministic matched/gap lists on the stored row are AUTHORITATIVE
    # (already synonym-normalized). Thread them into the explanation layer so the
    # LLM narrative can never contradict them (e.g. suggest "add Kubernetes" when
    # the CV already writes "k8s").
    sem = await _maybe_semantic_analyze(
        job,
        best_input,
        recommended_row.score,
        matched_skills,
        gaps,
    )
    if sem is not None and not sem.ai_unavailable and sem.summary:
        await fit_store.save_explanation(
            session,
            cv_id=best_cv.id,
            job_id=job_id,
            explanation=sem.summary,
            prompt_version=prompt_version,
            lang=lang,
        )
        # Seed the cross-CV cache so the NEXT CV with the same evidence
        # against this JD version reuses it at 0 tokens.
        await fit_store.put_reusable_explanation(
            session,
            fingerprint=fingerprint,
            explanation=sem.summary,
            prompt_version=prompt_version,
            lang=lang,
        )
        return sem.summary, True

    # Provider failure / empty summary -> user-safe degrade.
    return None, False


async def _score_active_cvs(
    session: AsyncSession,
    *,
    principal: Principal,
    job_id: uuid.UUID,
) -> dict:
    """Shared deterministic scoring core for both fit entry points.

    Loads the job + the caller's active CVs, reuses fresh stored rows or
    recomputes/persists the deterministic 6-criteria score, ranks them, and returns
    the internal working set. NO LLM is invoked here.

    Returns a dict with keys:
      - ``job`` / ``job_public`` / ``job_version``
      - ``cv_by_id`` (``{cv_id_str: CvProfile}``)
      - ``titles`` (``{cv_id_str: title}``)
      - ``ordered_rows`` (ranked ``list[CvJobFitScore]``)
      - ``recommended_row`` / ``recommended_cv_id``
      - ``signal``
      - ``now``
      - ``has_cvs`` (bool)

    Raises ``ResourceNotFoundError`` for hidden/closed/missing jobs.
    """
    permission_checker.require(principal, _RESOURCE, "read")
    assert principal.user_id is not None

    job = await job_fit_read.load_job_for_fit(session, job_id=job_id, persona=principal.persona)
    if job is None:
        # Hidden / closed / unpublished / missing -> non-enumerable 404.
        raise ResourceNotFoundError()

    job_public = {"id": job["id"], "title": job["title"], "company": job["company"]}
    job_version = int(job.get("version") or 1)
    now = datetime.now(tz=UTC)
    cvs = await _load_active_cvs(session, user_id=principal.user_id)

    if not cvs:
        return {
            "job": job,
            "job_public": job_public,
            "job_version": job_version,
            "cv_by_id": {},
            "titles": {},
            "ordered_rows": [],
            "recommended_row": None,
            "recommended_cv_id": None,
            "signal": job_fit.evaluate(job, [], stale_days=_stale_days()).signal,
            "now": now,
            "has_cvs": False,
        }

    cv_by_id = {str(cv.id): cv for cv in cvs}
    titles = {str(cv.id): cv.title for cv in cvs}
    stored = await fit_store.load_rows(
        session,
        user_id=principal.user_id,
        job_id=job_id,
        cv_ids=[cv.id for cv in cvs],
    )

    # --- FAST PATH: every CV has a fresh stored row -> no deterministic recompute.
    all_fresh = all(
        (row := stored.get(cv.id)) is not None
        and fit_store.is_fresh(row, cv_version=cv.version, job_version=job_version)
        for cv in cvs
    )

    rows: dict[uuid.UUID, CvJobFitScore]
    signal: str
    if all_fresh:
        rows = stored
        # Signal is identical across a job's rows (JD-derived); take any.
        signal = next(iter(rows.values())).signal
    else:
        # --- SLOW PATH: recompute all (cheap, deterministic) + upsert each.
        cv_inputs = [await _build_cv_input(session, cv=cv, now=now) for cv in cvs]
        # Cross-lingual (VN↔EN) matching: translate every JD/CV skill term to
        # canonical English and append the English forms before scoring, so the
        # lexical tier matches "supply chain management" against "quản lý chuỗi
        # cung ứng". Gated + best-effort: offline / error -> inputs unchanged ->
        # pure lexical. Runs only here on the compute path; the store persists the
        # resulting score, so cache hits above never re-translate. The upsert stays
        # keyed on the ORIGINAL cv/job versions (augmentation doesn't change them).
        aug_job, aug_cv_inputs, aug_complete = await skill_translation.english_augment(
            job, cv_inputs
        )
        outcome = job_fit.evaluate(aug_job, aug_cv_inputs, stale_days=_stale_days())
        signal = outcome.signal
        rows = {}
        for fit in outcome.results:
            cv = cv_by_id[fit.cv_id]
            payload = _fit_to_result_payload(fit, signal=outcome.signal)
            # When AI was on but a translation failed, persist the (degraded lexical)
            # score PROVISIONALLY so the next read retries once AI recovers, rather
            # than caching the degraded score as final.
            row = await fit_store.upsert_result(
                session,
                user_id=principal.user_id,
                cv_id=cv.id,
                job_id=job_id,
                result=payload,
                cv_version=cv.version,
                job_version=job_version,
                provisional=not aug_complete,
            )
            rows[cv.id] = row

    # Rank exactly like the deterministic ``job_fit.evaluate`` did: highest score
    # first, tie-broken by the most recently updated CV (lowest ``last_updated_days``)
    # then cv_id for stability. ``results[0]`` IS the recommended CV, so both the
    # ordered list and ``recommended_cv_id`` stay consistent on the fast path.
    ordered_rows = sorted(
        rows.values(),
        key=lambda r: (-r.score, -r.avg_skill_level, r.last_updated_days, str(r.cv_id)),
    )
    recommended_cv_id: str | None = None
    recommended_row: CvJobFitScore | None = None
    if ordered_rows:
        recommended_row = ordered_rows[0]
        recommended_cv_id = str(recommended_row.cv_id)

    return {
        "job": job,
        "job_public": job_public,
        "job_version": job_version,
        "cv_by_id": cv_by_id,
        "titles": titles,
        "ordered_rows": ordered_rows,
        "recommended_row": recommended_row,
        "recommended_cv_id": recommended_cv_id,
        "signal": signal,
        "now": now,
        "has_cvs": True,
    }


async def job_fit_for_job(
    session: AsyncSession,
    *,
    principal: Principal,
    job_id: uuid.UUID,
    with_explanation: bool = False,
) -> dict:
    """Score the caller's active CVs against ``job_id`` and recommend the best.

    Scoring is two-tier, but the two tiers have strictly separate jobs:
    - Deterministic (always): the 6-criteria HR score from ``app.ai.cv.job_fit`` IS
      the product score. Same CV + same JD -> identical number, every reload.
    - Semantic (opt-in via ``with_explanation``, recommended CV only): the LLM
      produces ONLY the natural-language ``explanation`` for the recommended CV.
      It never moves the number (owner decision 2026-07-06). Falls back to
      ``explanation: null`` when the provider is unavailable or the gate is off.

    ``with_explanation`` defaults to ``False`` so the fast, deterministic-only
    result returns without EVER waiting on the LLM (the 20-30s job-detail stall
    fix): the AI explanation is loaded separately by ``fit_explanation_for_job``
    (``GET /jobs/{job_id}/fit-explanation``). When ``True`` this keeps the legacy
    inline behavior (compute/reuse the explanation for the recommended CV).

    Results are PERSISTED in ``cv_job_fit_scores``, stamped with the CV/JD content
    versions. A reload with unchanged versions reuses the stored score AND (when
    ``with_explanation``) the stored explanation, so the deterministic recompute is
    skipped and the LLM is NOT re-invoked (owner requirement 2026-07-06). The
    score/explanation are recomputed only when the CV or JD content version changes.
    """

    core = await _score_active_cvs(session, principal=principal, job_id=job_id)

    if not core["has_cvs"]:
        # Student has no active CVs: 200 with empty results (UI prompts "create a
        # CV"); never 404.
        return {
            "job": core["job_public"],
            "recommended_cv_id": None,
            "results": [],
            "signal": core["signal"],
            "ai_explanation_available": False,
        }

    ordered_rows: list[CvJobFitScore] = core["ordered_rows"]
    recommended_cv_id: str | None = core["recommended_cv_id"]
    recommended_row: CvJobFitScore | None = core["recommended_row"]
    titles: dict[str, str] = core["titles"]

    # --- EXPLANATION: recommended CV only, opt-in, gated, reuse-or-generate once.
    # ``with_explanation=False`` (default) skips the LLM entirely so the caller
    # returns fast (deterministic-only); the async ``fit_explanation_for_job``
    # endpoint fills it in separately.
    explanation: str | None = None
    ai_available = False
    if with_explanation and recommended_row is not None and recommended_cv_id is not None:
        explanation, ai_available = await _resolve_explanation_for_row(
            session,
            job=core["job"],
            job_id=job_id,
            job_version=core["job_version"],
            recommended_row=recommended_row,
            best_cv=core["cv_by_id"][recommended_cv_id],
            now=core["now"],
        )

    # Persist upserts + explanation writes (read endpoint that now caches rows).
    await session.commit()

    results = [
        _present_from_row(
            row,
            title=titles.get(str(row.cv_id), ""),
            explanation=explanation if str(row.cv_id) == recommended_cv_id else None,
        )
        for row in ordered_rows
    ]
    return {
        "job": core["job_public"],
        "recommended_cv_id": recommended_cv_id,
        "results": results,
        "signal": core["signal"],
        "ai_explanation_available": ai_available,
    }


async def fit_explanation_for_job(
    session: AsyncSession,
    *,
    principal: Principal,
    job_id: uuid.UUID,
    cv_id: uuid.UUID | None = None,
) -> dict:
    """Async AI explanation for the recommended (or a chosen) CV against a job.

    This is the SLOW half that ``job_fit_for_job(with_explanation=False)`` no
    longer does inline: the deterministic score/bands return instantly from the
    student-intelligence endpoint, and the frontend fires THIS separately to fill
    in the AI narrative once it is ready.

    The explanation is produced by the exact same shared block
    (``_resolve_explanation_for_row``) as the legacy inline path — fresh-row
    reuse, cross-CV learning cache, the two AI gates, and the 20s timeout — so
    there is no behavioral drift between the two entry points.

    ``cv_id`` (optional): explain THAT CV when it belongs to the caller and is
    scored; otherwise fall back to the recommended CV (mirrors
    ``student_intelligence`` selected-CV semantics — an unknown/foreign CV never
    404s here, it degrades to the recommendation). Hidden/closed/missing jobs
    still 404 (via ``_score_active_cvs``); no active CVs -> null explanation.

    Returns ``{"cv_id": str|None, "explanation": str|None,
    "ai_explanation_available": bool}``. Never raises for AI-off/failure.
    """
    core = await _score_active_cvs(session, principal=principal, job_id=job_id)

    ordered_rows: list[CvJobFitScore] = core["ordered_rows"]
    if not core["has_cvs"] or not ordered_rows:
        await session.commit()
        return {"cv_id": None, "explanation": None, "ai_explanation_available": False}

    # Resolve the target row: the requested cv_id when it is one of the caller's
    # scored CVs, else the recommended CV.
    by_cv_id = {str(r.cv_id): r for r in ordered_rows}
    target_cv_id: str | None = None
    if cv_id is not None and str(cv_id) in by_cv_id:
        target_cv_id = str(cv_id)
    else:
        target_cv_id = core["recommended_cv_id"]

    target_row = by_cv_id.get(target_cv_id) if target_cv_id else None
    if target_row is None or target_cv_id is None:
        await session.commit()
        return {"cv_id": None, "explanation": None, "ai_explanation_available": False}

    explanation, ai_available = await _resolve_explanation_for_row(
        session,
        job=core["job"],
        job_id=job_id,
        job_version=core["job_version"],
        recommended_row=target_row,
        best_cv=core["cv_by_id"][target_cv_id],
        now=core["now"],
    )

    # Persist any explanation writes (row explanation + cross-CV cache seed).
    await session.commit()

    return {
        "cv_id": target_cv_id,
        "explanation": explanation,
        "ai_explanation_available": ai_available,
    }


def _stale_days() -> int:
    return get_settings().cv_stale_after_days
