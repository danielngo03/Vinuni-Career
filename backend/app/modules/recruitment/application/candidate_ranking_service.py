"""Partner candidate-triage ranking — deterministic CV-JD fit over a job's pool.

A recruiter reviewing a job asks: "of everyone who applied, who best matches the
JD?" This service answers with the SAME deterministic 0-100 product score
(``app.ai.cv.job_fit``) a student sees for the same JD, ranked across the job's
applicant pool. It is:

- ADVISORY ONLY. The recruiter makes every decision; nothing is auto-advanced or
  auto-rejected. The score is a triage aid, not a verdict.
- DETERMINISTIC ONLY. No per-applicant LLM call — the batch never fans a model
  call across the pool (CLAUDE.md usage-accounting rule). The natural-language
  per-candidate narrative stays the separate, usage-safe
  ``GET /applications/{application_id}/ai-screening-brief``.
- PRIVACY / ANONYMITY SAFE. An anonymous applicant whose reveal is not accepted
  keeps the SAME masked handle used everywhere else (never name/email). The
  surfaced ``matched_skills`` / ``gaps`` are JD-derived terms only (the scorer
  never echoes raw CV text), so no candidate PII crosses the boundary. The 0-100
  number is a PRODUCT score, never model confidence/embedding/token internals.

RBAC + tenant isolation (404-not-403 for a cross-org job) are enforced HERE, in
the service layer — never the router. The applicant CV content comes from the
IMMUTABLE application snapshot (``documents`` facade); the JD requirements come
from the owner read facade (``opportunities`` facade). Neither module's ORM is
imported directly.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.cv import grounding, job_fit, skill_translation
from app.core.config import get_settings
from app.modules.auth.application.context import RequestContext
from app.modules.documents.application import snapshot_service
from app.modules.opportunities.application import job_fit_read, job_read_facade
from app.modules.recruitment.api import presenters
from app.modules.recruitment.application import _shared
from app.modules.recruitment.domain.models import Application
from app.modules.users.application import user_service
from app.shared.audit import write_audit
from app.shared.exceptions import ResourceNotFoundError
from app.shared.permissions import Principal, permission_checker

_RESOURCE = _shared.RESOURCE

# Defensive upper bound on how many applicants one ranking request scores. The
# scorer is pure and ~1 ms/CV, but a request must never fan unboundedly. Beyond
# this cap the MOST RECENT applications (``applied_at`` desc) are ranked and the
# rest omitted (documented; a recruiter triaging 500+ at once is already an edge —
# the active pool is covered first).
MAX_RANKING_APPLICANTS = 500

# Fit-band thresholds. Aligned with the STUDENT-side categories for the same JD
# (``opportunities.student_intelligence_service._FIT_LABEL_THRESHOLDS``:
# strong_fit>=85, good_fit>=70, possible_fit>=50, weak_fit>=0), so a partner and a
# student read the same 0-100 number the same way. "possible" is surfaced as
# "fair" in the recruiter triage vocabulary.
_BAND_THRESHOLDS: tuple[tuple[int, str], ...] = (
    (85, "strong"),
    (70, "good"),
    (50, "fair"),
    (0, "weak"),
)


def _fit_band(score: int) -> str:
    for threshold, band in _BAND_THRESHOLDS:
        if score >= threshold:
            return band
    return "weak"


def _stale_days() -> int:
    return get_settings().cv_stale_after_days


# --------------------------------------------------------------------------- #
# Snapshot -> scorer-section adapter                                          #
# --------------------------------------------------------------------------- #

# Title-keyword -> canonical section_type, for UPLOADED-document snapshots whose
# sections carry a display title but no ``section_type`` (builder snapshots
# already carry ``section_type``). Substring match on the normalized title; the
# more specific hints come first. The canonical types line up with the scorer's
# ``_EXPERIENCE_TYPES`` / ``_CREDENTIAL_TYPES`` / ``_SKILL_SECTION_TYPES`` sets.
_TITLE_TYPE_HINTS: tuple[tuple[str, str], ...] = (
    ("skill", "skills"),
    ("kỹ năng", "skills"),
    ("work experience", "experience"),
    ("experience", "experience"),
    ("employment", "experience"),
    ("work history", "experience"),
    ("kinh nghiệm", "experience"),
    ("quá trình công tác", "experience"),
    ("project", "projects"),
    ("dự án", "projects"),
    ("education", "education"),
    ("academic", "education"),
    ("học vấn", "education"),
    ("certif", "certifications"),
    ("license", "certifications"),
    ("chứng chỉ", "certifications"),
    ("language", "languages"),
    ("ngôn ngữ", "languages"),
    ("award", "awards"),
    ("giải thưởng", "awards"),
    ("activit", "activities"),
    ("hoạt động", "activities"),
    ("summary", "summary"),
    ("objective", "summary"),
    ("profile", "summary"),
    ("about", "summary"),
    ("mục tiêu", "summary"),
    ("giới thiệu", "summary"),
)


def _infer_section_type(title: str) -> str:
    norm = grounding.normalize(title)
    for hint, section_type in _TITLE_TYPE_HINTS:
        if hint in norm:
            return section_type
    return norm.replace(" ", "_") or "custom"


def _snapshot_to_sections(snapshot_json: dict) -> list[dict]:
    """Map a stored application CV snapshot into the scorer's section shape.

    Handles BOTH snapshot shapes and degrades safely (never raises):
      - builder CV: sections carry ``{"section_type", "title", "content_json"}``
      - uploaded doc: sections carry ``{"title", "content_json"}`` (no type)

    Produces ``{"section_type", "title", "content"}`` — the shape
    ``app.ai.cv.job_fit`` bands + ``grounding`` actually consume: the per-band
    text (``job_fit._section_text``) reads ``section_type`` + ``content``, and the
    whole-CV text (``grounding.sections_to_text``) reads ``content`` too. An
    absent/empty ``sections`` list -> ``[]`` -> the caller treats the applicant as
    unscorable (``fit_score: null``) rather than fabricating a number.
    """

    raw = snapshot_json.get("sections") if isinstance(snapshot_json, dict) else None
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for sec in raw:
        if not isinstance(sec, dict):
            continue
        title = str(sec.get("title") or "")
        content = sec.get("content")
        if not isinstance(content, dict):
            content = sec.get("content_json")
        if not isinstance(content, dict):
            content = {}
        section_type = sec.get("section_type")
        if not isinstance(section_type, str) or not section_type.strip():
            section_type = _infer_section_type(title)
        out.append({"section_type": section_type, "title": title, "content": content})
    return out


def _cv_input_from_snapshot(
    *, application_id: uuid.UUID, snapshot_json: dict, applied_days: int
) -> job_fit.CvInput | None:
    """A ``CvInput`` for the scorer, or ``None`` when the snapshot has no signal.

    A snapshot whose sections yield no evidence text (redacted / empty / unreadable
    upload) returns ``None`` so the applicant is listed with ``fit_score: null``
    instead of a fabricated number.
    """

    sections = _snapshot_to_sections(snapshot_json)
    if not grounding.sections_to_text(sections).strip():
        return None
    return job_fit.CvInput(
        cv_id=str(application_id),
        title=str(snapshot_json.get("title") or ""),
        language=str(snapshot_json.get("language") or "vi"),
        sections=sections,
        last_updated_days=applied_days,
    )


# --------------------------------------------------------------------------- #
# Main entry point                                                            #
# --------------------------------------------------------------------------- #


async def rank_job_applicants(
    session: AsyncSession,
    *,
    principal: Principal,
    job_id: uuid.UUID,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    """Rank a job's applicants by deterministic CV-JD fit (partner-only, advisory).

    Returns::

        {
          "job_id": str,
          "scored_count": int,                 # applicants with a real score
          "signal": "ok" | "low_signal" | "no_requirements",
          "items": [
            {
              "application_id": str,
              "applicant": <masked/partner identity block>,
              "status": str, "status_label": str,
              "fit_score": int(0-100) | null,  # deterministic PRODUCT score
              "fit_band": "strong"|"good"|"fair"|"weak" | null,
              "matched_skills": [...],         # JD-derived terms only
              "gaps": [...],                   # JD-derived terms only
              "stale": bool,
              "rank": int                      # 1-based over the whole list
            }, ...
          ]
        }

    Ordering: scored applicants first, in the scorer's order (``fit_score`` desc,
    tie-broken by self-rated proficiency then recency), then unscorable ones
    (null score) by recency. ``rank`` is 1-based across the whole list.
    """

    # 1. RBAC + tenant isolation — mirror ``apply_service.list_job_applications``:
    #    a cross-org job is indistinguishable from missing (404, never 403).
    job_ref = await job_read_facade.get_job_ref(session, job_id)
    if job_ref is None:
        raise ResourceNotFoundError()
    if not principal.is_superadmin and (
        principal.org_id is None or principal.org_id != job_ref.org_id
    ):
        raise ResourceNotFoundError()
    permission_checker.require(
        principal, _RESOURCE, "read", resource_org_id=job_ref.org_id
    )

    # 2. Owner JD projection (NO visibility filter — a partner may triage its OWN
    #    draft/closed job). Ownership was validated above; this returns the
    #    leak-safe requirements dict (identical shape to the student path).
    job_dict = await job_fit_read.load_owned_job_for_fit(
        session, job_id=job_id, org_id=job_ref.org_id
    )
    if job_dict is None:  # deleted between the two reads -> non-enumerable 404.
        raise ResourceNotFoundError()

    # 3. Load the job's applicants (all non-deleted, newest first, bounded).
    now = datetime.now(tz=UTC)
    apps = await _load_applicants(session, job_id=job_id)

    # 4. Build scorable inputs from each IMMUTABLE CV snapshot (batch loaded).
    snapshots = await snapshot_service.get_snapshot_json_for_applications(
        session, application_ids=[a.id for a in apps]
    )
    cv_inputs: list[job_fit.CvInput] = []
    for a in apps:
        cv_input = _cv_input_from_snapshot(
            application_id=a.id,
            snapshot_json=snapshots.get(a.id) or {},
            applied_days=_days_since(a.applied_at, now),
        )
        if cv_input is not None:
            cv_inputs.append(cv_input)

    # 5. Deterministic scoring. Cross-lingual augmentation is CACHE-ONLY
    #    (``allow_model_calls=False``), so this NEVER spends a model call per
    #    applicant — offline / cold cache it is a pure-lexical no-op.
    aug_job, aug_inputs, _ = await skill_translation.english_augment(
        job_dict, cv_inputs, allow_model_calls=False
    )
    outcome = job_fit.evaluate(aug_job, aug_inputs, stale_days=_stale_days())

    # When the JD carries no usable requirement terms at all, refuse to fabricate
    # numbers: every applicant is listed with ``fit_score: null``.
    no_requirements = outcome.requirement_count == 0
    fit_by_app: dict[str, job_fit.CvFit] = (
        {} if no_requirements else {r.cv_id: r for r in outcome.results}
    )
    signal = "no_requirements" if no_requirements else outcome.signal

    # 6. Load display identities — batch, revealed applicants ONLY (anonymity).
    reveal_user_ids = [
        a.applicant_id
        for a in apps
        if a.reveal_approved_at is not None or not a.is_anonymous
    ]
    users = await user_service.get_many(session, reveal_user_ids)

    # 7. Order: scored applicants first (scorer rank order), then null ones by
    #    recency. ``rank`` is 1-based over the whole list.
    app_by_id = {str(a.id): a for a in apps}
    ordered: list[Application] = []
    if not no_requirements:
        for r in outcome.results:  # sorted by (-score, -avg_skill_level, ...)
            candidate = app_by_id.get(r.cv_id)
            if candidate is not None:
                ordered.append(candidate)
    scored_ids = {str(a.id) for a in ordered}
    remainder = [a for a in apps if str(a.id) not in scored_ids]
    remainder.sort(key=lambda a: _shared.as_aware(a.applied_at), reverse=True)
    ordered.extend(remainder)

    items: list[dict] = []
    for rank, a in enumerate(ordered, start=1):
        fit = fit_by_app.get(str(a.id))
        fit_view: dict | None = None
        if fit is not None:
            fit_view = {
                "score": fit.score,
                "band": _fit_band(fit.score),
                "matched_skills": list(fit.matched_skills),
                "gaps": list(fit.gaps),
                "stale": fit.stale,
            }
        items.append(
            presenters.partner_ranking_item(
                a,
                user=users.get(a.applicant_id),
                fit=fit_view,
                rank=rank,
                locale=locale,
            )
        )

    scored_count = len(fit_by_app)

    # 8. ONE aggregate, metadata-only audit row. Justification: this is a BULK read
    #    over EVERY applicant's CV content for triage, worth logging for compliance
    #    (who ran triage on which job, when). It deliberately does NOT emit a
    #    per-candidate ``cv_downloaded`` / ``application_opened`` access event —
    #    that would pollute the per-CV candidate-access audit. Best-effort: an
    #    audit/commit failure never breaks the read (the pool read is otherwise
    #    side-effect-free).
    await _audit_ranking(
        session,
        principal=principal,
        ctx=ctx,
        job_id=job_id,
        org_id=job_ref.org_id,
        applicant_count=len(apps),
        scored_count=scored_count,
        signal=signal,
    )

    return {
        "job_id": str(job_id),
        "scored_count": scored_count,
        "signal": signal,
        "items": items,
    }


async def _load_applicants(
    session: AsyncSession, *, job_id: uuid.UUID
) -> list[Application]:
    stmt = (
        select(Application)
        .where(Application.job_id == job_id, Application.deleted_at.is_(None))
        .order_by(Application.applied_at.desc(), Application.id.desc())
        .limit(MAX_RANKING_APPLICANTS)
    )
    return list((await session.execute(stmt)).scalars().all())


def _days_since(applied_at: datetime, now: datetime) -> int:
    return max(0, (now - _shared.as_aware(applied_at)).days)


async def _audit_ranking(
    session: AsyncSession,
    *,
    principal: Principal,
    ctx: RequestContext,
    job_id: uuid.UUID,
    org_id: uuid.UUID,
    applicant_count: int,
    scored_count: int,
    signal: str,
) -> None:
    try:
        await write_audit(
            session,
            action="recruitment.applicants_ranked",
            resource_type="job",
            resource_id=job_id,
            context=_shared.audit_ctx(principal, ctx),
            after={
                "org_id": str(org_id),
                "applicant_count": applicant_count,
                "scored_count": scored_count,
                "signal": signal,
            },
        )
        await session.commit()
    except Exception:  # noqa: BLE001 — audit instrumentation must never break the read
        try:
            await session.rollback()
        except Exception:  # noqa: BLE001
            pass
