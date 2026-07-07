"""Read facade: a job's requirements for CV-to-job fit scoring.

The ``documents`` and ``recruitment`` modules must score CVs against a target job
without deep-importing the ``Job`` ORM or re-implementing the visibility
predicate. This module is the single allowed surface. It has two entry points
that share ONE projection builder so every path produces byte-identical job
dicts:

- :func:`load_job_for_fit` — the STUDENT/discovery path. Applies the **same**
  visibility filter as the public job read (``visibility.apply_visible_filter``)
  at the caller's persona tier, so a job that is hidden, unpublished, closed, or
  past deadline is indistinguishable from a missing one (returns ``None`` -> the
  caller raises a non-enumerable 404).
- :func:`load_owned_job_for_fit` — the PARTNER-owner path. Scopes strictly by
  ``org_id`` (ownership) with NO visibility filter, so a partner can score
  applicants against its OWN job even while the job is draft/closed/past-deadline.
  Cross-org / missing -> ``None`` (the caller raises a non-enumerable 404).

The returned projection is a leak-safe requirements dict (structured skills, the
JD text, work-mode/location, and the employer display name only) — no internal
job columns (moderation notes, storage keys, raw status) cross the boundary.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.opportunities.application.visibility import apply_visible_filter
from app.modules.opportunities.domain import lifecycle
from app.modules.opportunities.domain.models import Job
from app.modules.organization.application import org_reporting_facade


def _now() -> datetime:
    return datetime.now(tz=UTC)


async def load_job_for_fit(
    session: AsyncSession, *, job_id: uuid.UUID, persona: str
) -> dict | None:
    """Return the requirements projection for a job the principal may discover.

    ``None`` when the job does not exist or is not visible to ``persona`` (closed,
    unpublished, hidden tier, past deadline) — the caller maps this to 404.
    """

    levels = lifecycle.visible_levels_for(persona, is_authenticated=True)
    stmt = apply_visible_filter(
        select(Job).where(Job.id == job_id), levels=levels, now=_now()
    )
    job = (await session.execute(stmt)).scalar_one_or_none()
    if job is None:
        return None

    org = await org_reporting_facade.summary_for(session, job.org_id)
    return _projection_from_job(job, org.display_name if org else None)


async def load_owned_job_for_fit(
    session: AsyncSession, *, job_id: uuid.UUID, org_id: uuid.UUID
) -> dict | None:
    """Requirements projection for a job OWNED by ``org_id`` — no visibility filter.

    The PARTNER-owner path used by the recruitment candidate-ranking triage: a
    recruiter may score applicants against its OWN job even while that job is
    draft, closed, or past deadline, so — unlike :func:`load_job_for_fit` — there
    is NO discovery-visibility gate, only strict ownership (``org_id`` match, not
    soft-deleted). Cross-org / missing / deleted -> ``None`` (the caller raises a
    non-enumerable 404). The projection is byte-identical to the student path
    (same :func:`_projection_from_job`).
    """

    stmt = select(Job).where(
        Job.id == job_id, Job.org_id == org_id, Job.deleted_at.is_(None)
    )
    job = (await session.execute(stmt)).scalar_one_or_none()
    if job is None:
        return None
    org = await org_reporting_facade.summary_for(session, job.org_id)
    return _projection_from_job(job, org.display_name if org else None)


def _projection_from_job(job: Job, org_display_name: str | None) -> dict:
    """The single leak-safe requirements projection shared by both entry points.

    Only requirement / logistics / JD-text fields and the employer display name —
    no internal job columns (moderation notes, storage keys, raw status). The
    ``version`` is an INTERNAL content-version stamp for the persisted CV-JD fit
    store (never surfaced to end users).
    """

    jd_text = " ".join(
        part
        for part in (job.title, job.description, job.requirements, job.benefits)
        if part
    )
    return {
        "id": str(job.id),
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
