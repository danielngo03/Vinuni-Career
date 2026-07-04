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

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.cv import job_fit
from app.ai.cv.llm import generate_note
from app.ai.gateway import runtime_config
from app.ai.gateway.factory import real_provider_active
from app.ai.prompts.cv_recommend import v1 as recommend_prompt
from app.core.config import get_settings
from app.modules.documents.application import _cv_core, _shared
from app.modules.documents.domain import catalog
from app.modules.documents.domain.models import CvProfile, CvSection
from app.modules.opportunities.application import job_fit_read
from app.shared.exceptions import AIUnavailableError, ResourceNotFoundError
from app.shared.permissions import Principal, permission_checker

_RESOURCE = _shared.RESOURCE
TASK_TYPE = "recommend_cv_for_job"


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


async def _load_active_cvs(
    session: AsyncSession, *, user_id: uuid.UUID
) -> list[CvProfile]:
    """The caller's active CV library: not soft-deleted, not archived."""

    stmt = (
        select(CvProfile)
        .where(
            CvProfile.user_id == user_id,
            CvProfile.deleted_at.is_(None),
            CvProfile.status != catalog.CV_ARCHIVED,
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


async def _build_cv_input(
    session: AsyncSession, *, cv: CvProfile, now: datetime
) -> job_fit.CvInput:
    sections = await _cv_core._load_sections(session, cv_id=cv.id)
    return job_fit.CvInput(
        cv_id=str(cv.id),
        title=cv.title,
        language=cv.language or "vi",
        sections=[_section_dict(s) for s in sections],
        last_updated_days=_last_updated_days(cv, sections, now=now),
    )


def _explanation_context(job: dict, fit: job_fit.CvFit, *, output_language: str) -> str:
    """Grounded CONTEXT block for the optional explanation (no internals).

    Structural labels are internal English scaffolding; ``OUTPUT_LANGUAGE`` carries
    the resolved user-facing language so the answer matches the recommended CV.
    """

    none = "(không có)" if output_language == "vi" else "(none)"
    matched = ", ".join(fit.matched_skills) or none
    gaps = ", ".join(fit.gaps) or none
    return (
        f"CONTEXT\nOUTPUT_LANGUAGE: {output_language}\n"
        f"JOB_TITLE: {job.get('title') or ''}\n"
        f"MATCHED_SKILLS: {matched}\n"
        f"MISSING_SKILLS: {gaps}\n"
    )


async def _maybe_explain(
    job: dict,
    results: list[job_fit.CvFit],
    recommended_id: str | None,
    *,
    output_language: str = "vi",
) -> tuple[str | None, bool]:
    """Return ``(explanation, available)`` for the recommended CV.

    Only one model call is made (for the recommended CV) to avoid wasting model
    calls. When no real provider is active, or the call fails, degrade silently.
    The user-facing explanation is written in ``output_language`` (resolved from
    the recommended CV's language) while the prompt instructions stay English.
    """

    # Two AND-guards: the real-provider gate (env+key+db) AND the admin feature
    # flag for job-fit AI explanations (ADR-0011 §2). Either off -> degrade to
    # ``explanation: null`` with the deterministic score still returned.
    if (
        not recommended_id
        or not real_provider_active()
        or not runtime_config.current().job_fit_ai_explanation_enabled
    ):
        return None, False
    fit = next((r for r in results if r.cv_id == recommended_id), None)
    if fit is None:
        return None, False
    try:
        text = await generate_note(
            task_type=TASK_TYPE,
            system_prompt=recommend_prompt.build_system_prompt(output_language),
            user_content=_explanation_context(job, fit, output_language=output_language),
        )
    except AIUnavailableError:
        return None, False
    text = (text or "").strip()
    return (text or None), bool(text)


def _present_result(fit: job_fit.CvFit, *, explanation: str | None) -> dict:
    return {
        "cv_id": fit.cv_id,
        "title": fit.title,
        "score": fit.score,
        "bands": fit.bands.as_dict(),
        "matched_skills": fit.matched_skills,
        "gaps": fit.gaps,
        "stale": fit.stale,
        "last_updated_days": fit.last_updated_days,
        "explanation": explanation,
    }


async def job_fit_for_job(
    session: AsyncSession,
    *,
    principal: Principal,
    job_id: uuid.UUID,
) -> dict:
    """Score the caller's active CVs against ``job_id`` and recommend the best."""

    permission_checker.require(principal, _RESOURCE, "read")
    assert principal.user_id is not None

    job = await job_fit_read.load_job_for_fit(
        session, job_id=job_id, persona=principal.persona
    )
    if job is None:
        # Hidden / closed / unpublished / missing -> non-enumerable 404.
        raise ResourceNotFoundError()

    now = datetime.now(tz=UTC)
    cvs = await _load_active_cvs(session, user_id=principal.user_id)

    if not cvs:
        # Student has no active CVs: 200 with empty results (UI prompts "create a
        # CV"); never 404.
        return {
            "job": {"id": job["id"], "title": job["title"], "company": job["company"]},
            "recommended_cv_id": None,
            "results": [],
            "signal": job_fit.evaluate(job, [], stale_days=_stale_days()).signal,
            "ai_explanation_available": False,
        }

    cv_inputs = [await _build_cv_input(session, cv=cv, now=now) for cv in cvs]
    outcome = job_fit.evaluate(job, cv_inputs, stale_days=_stale_days())

    # The explanation follows the recommended CV's own (detected/declared) language.
    output_language = next(
        (ci.language for ci in cv_inputs if ci.cv_id == outcome.recommended_cv_id),
        "vi",
    )
    explanation, ai_available = await _maybe_explain(
        job, outcome.results, outcome.recommended_cv_id, output_language=output_language
    )

    results = [
        _present_result(
            fit,
            explanation=explanation if fit.cv_id == outcome.recommended_cv_id else None,
        )
        for fit in outcome.results
    ]
    return {
        "job": {"id": job["id"], "title": job["title"], "company": job["company"]},
        "recommended_cv_id": outcome.recommended_cv_id,
        "results": results,
        "signal": outcome.signal,
        "ai_explanation_available": ai_available,
    }


def _stale_days() -> int:
    return get_settings().cv_stale_after_days
