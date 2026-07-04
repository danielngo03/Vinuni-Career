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
    stmt = apply_visible_filter(
        select(Job).where(Job.id == job_id), levels=levels, now=_now()
    )
    job = (await session.execute(stmt)).scalar_one_or_none()
    if job is None:
        return None

    org = await org_reporting_facade.summary_for(session, job.org_id)

    jd_text = " ".join(
        part for part in (job.description, job.requirements, job.benefits) if part
    )
    return {
        "id": str(job.id),
        "title": job.title,
        "company": {"display_name": org.display_name if org else None},
        "required_skills": list(job.required_skills or []),
        "preferred_skills": list(job.preferred_skills or []),
        "experience_min_years": job.experience_min_years,
        "degree_required": job.degree_required,
        "location_type": job.location_type,
        "location_city": job.location_city,
        "location_country": job.location_country,
        "jd_text": jd_text,
    }
