"""Read facade: a job's requirements for CV-to-job fit scoring.

The ``documents`` module must score a student's CVs against a target job without
deep-importing the ``Job`` ORM or re-implementing the visibility predicate. This
is the single allowed surface: it applies the **same** visibility filter as the
public job read (``visibility.apply_visible_filter``) at the caller's persona
tier, so a job that is hidden, unpublished, closed, or past deadline is
indistinguishable from a missing one (returns ``None`` -> the caller raises a
non-enumerable 404).

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
    stmt = apply_visible_filter(select(Job).where(Job.id == job_id), levels=levels, now=_now())
    job = (await session.execute(stmt)).scalar_one_or_none()
    if job is None:
        return None

    return await _project_requirements(session, job)


async def load_job_requirements(session: AsyncSession, *, job_id: uuid.UUID) -> dict | None:
    """Ungated requirements projection for a job by id (``None`` when missing).

    Unlike :func:`load_job_for_fit` this applies NO discovery-visibility filter, so
    a closed / past-deadline job is still scorable. It is for INTERNAL partner-
    scoped use only (e.g. scoring a candidate's submitted CV against the job they
    applied to): the caller MUST have already verified org ownership before calling
    it. The projection is the same leak-safe requirements dict — no internal job
    columns (moderation notes, storage keys, raw status) cross the boundary.
    """

    job = (await session.execute(select(Job).where(Job.id == job_id))).scalar_one_or_none()
    if job is None:
        return None
    return await _project_requirements(session, job)


async def _project_requirements(session: AsyncSession, job: Job) -> dict:
    org = await org_reporting_facade.summary_for(session, job.org_id)

    jd_text = " ".join(
        part for part in (job.title, job.description, job.requirements, job.benefits) if part
    )
    return {
        "id": str(job.id),
        # Content version stamp for the persisted CV-JD fit store: bumped whenever
        # the employer edits the JD, so a stored fit row is recomputed only when
        # the JD actually changes (INTERNAL; never surfaced to end users).
        "version": job.version,
        "title": job.title,
        "company": {"display_name": org.display_name if org else None},
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
