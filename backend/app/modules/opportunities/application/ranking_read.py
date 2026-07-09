"""Read facade: ranking *candidate data* for the discovery recommendation layer.

The ``discovery`` module owns the ranking POLICY (organic scoring, reason codes,
diversity, sponsored-slot separation) but must NOT deep-import the ``Job`` ORM or
re-implement the public-visibility predicate. This facade is the single allowed
surface: it returns already-eligibility-filtered candidate DTOs that carry both

- the enriched public ``summary`` (company block, labels) that is safe to return
  to the client, and
- the extra scoring-only fields (raw skills, JD text, recency, popularity counts,
  verified-employer flag) the ranker needs but the client never sees directly.

Every query runs through the **same** :func:`visibility.apply_visible_filter`
predicate as ``GET /jobs`` at the caller's persona tier, so a hidden, unpublished,
closed, past-deadline, or unmoderated job can never leak into a recommendation.
No scoring, taxonomy, or reason-code logic lives here — that is the ranker's job.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.opportunities.api import presenters
from app.modules.opportunities.application.visibility import apply_visible_filter
from app.modules.opportunities.domain import lifecycle
from app.modules.opportunities.domain.models import Job
from app.modules.organization.application.org_reporting_facade import (
    OrgSummary,
    summaries_for,
)


@dataclass(frozen=True, slots=True)
class RankingCandidate:
    """One eligible job + the fields the ranker needs (and the safe summary)."""

    job_id: uuid.UUID
    org_id: uuid.UUID
    title: str
    description: str
    requirements: str | None
    benefits: str | None
    required_skills: list[str]
    preferred_skills: list[str]
    employment_type: str
    location_type: str
    location_city: str | None
    location_country: str
    locations: list[dict]
    experience_min_years: int | None
    experience_max_years: int | None
    experience_mode: str | None
    degree_required: str | None
    seniority_level: str | None
    candidate_requirements: dict
    application_deadline: datetime | None
    published_at: datetime | None
    application_count: int
    view_count: int
    is_verified_employer: bool
    has_logo: bool
    jd_text: str
    summary: dict  # enriched public projection — the only part returned to clients

    def as_fit_job(self) -> dict:
        """Project to the requirements dict shape :mod:`app.ai.cv.job_fit` expects."""

        return {
            "id": str(self.job_id),
            "title": self.title,
            "description": self.description,
            "requirements": self.requirements,
            "benefits": self.benefits,
            "required_skills": list(self.required_skills),
            "preferred_skills": list(self.preferred_skills),
            "employment_type": self.employment_type,
            "experience_min_years": self.experience_min_years,
            "experience_max_years": self.experience_max_years,
            "experience_mode": self.experience_mode,
            "degree_required": self.degree_required,
            "seniority_level": self.seniority_level,
            "candidate_requirements": dict(self.candidate_requirements),
            "location_type": self.location_type,
            "location_city": self.location_city,
            "location_country": self.location_country,
            "locations": list(self.locations),
            "jd_text": self.jd_text,
        }


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _levels(persona: str, *, is_authenticated: bool) -> frozenset[str]:
    return lifecycle.visible_levels_for(persona, is_authenticated=is_authenticated)


def _visible(stmt, *, persona: str, is_authenticated: bool):
    return apply_visible_filter(
        stmt,
        levels=_levels(persona, is_authenticated=is_authenticated),
        now=_now(),
    )


async def _orgs_for(session: AsyncSession, jobs: list[Job]) -> dict[uuid.UUID, OrgSummary]:
    org_ids = {j.org_id for j in jobs}
    if not org_ids:
        return {}
    return await summaries_for(session, org_ids)


def _to_candidate(job: Job, org: OrgSummary | None, *, locale: str) -> RankingCandidate:
    jd_text = " ".join(
        part for part in (job.title, job.description, job.requirements, job.benefits) if part
    )
    return RankingCandidate(
        job_id=job.id,
        org_id=job.org_id,
        title=job.title,
        description=job.description,
        requirements=job.requirements,
        benefits=job.benefits,
        required_skills=list(job.required_skills or []),
        preferred_skills=list(job.preferred_skills or []),
        employment_type=job.employment_type,
        location_type=job.location_type,
        location_city=job.location_city,
        location_country=job.location_country,
        locations=list(job.locations or []),
        experience_min_years=job.experience_min_years,
        experience_max_years=job.experience_max_years,
        experience_mode=job.experience_mode,
        degree_required=job.degree_required,
        seniority_level=job.seniority_level,
        candidate_requirements=dict(job.candidate_requirements or {}),
        application_deadline=job.application_deadline,
        published_at=job.published_at,
        application_count=job.application_count or 0,
        view_count=job.view_count or 0,
        is_verified_employer=bool(org.is_verified) if org is not None else False,
        has_logo=bool(org is not None and org.has_logo),
        jd_text=jd_text,
        summary=presenters.public_job_summary(job, company=org, locale=locale),
    )


async def _materialize(
    session: AsyncSession, jobs: list[Job], *, locale: str
) -> list[RankingCandidate]:
    orgs = await _orgs_for(session, jobs)
    return [_to_candidate(j, orgs.get(j.org_id), locale=locale) for j in jobs]


async def list_candidates(
    session: AsyncSession,
    *,
    persona: str,
    is_authenticated: bool,
    limit: int,
    exclude_ids: set[uuid.UUID] | None = None,
    locale: str = "vi",
) -> list[RankingCandidate]:
    """Recency-ordered eligible candidate pool for the ranker (cap ``limit``)."""

    stmt = _visible(select(Job), persona=persona, is_authenticated=is_authenticated)
    if exclude_ids:
        stmt = stmt.where(Job.id.notin_(exclude_ids))
    stmt = stmt.order_by(Job.published_at.desc(), Job.id.desc()).limit(max(limit, 0))
    jobs = list((await session.execute(stmt)).scalars().all())
    return await _materialize(session, jobs, locale=locale)


async def load_candidate(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    persona: str,
    is_authenticated: bool,
    locale: str = "vi",
) -> RankingCandidate | None:
    """A single eligible candidate (the similar-jobs seed), or ``None`` if hidden."""

    stmt = _visible(
        select(Job).where(Job.id == job_id),
        persona=persona,
        is_authenticated=is_authenticated,
    )
    job = (await session.execute(stmt)).scalar_one_or_none()
    if job is None:
        return None
    (candidate,) = await _materialize(session, [job], locale=locale)
    return candidate


async def load_candidates_by_ids(
    session: AsyncSession,
    *,
    job_ids: list[uuid.UUID],
    persona: str,
    is_authenticated: bool,
    locale: str = "vi",
) -> dict[uuid.UUID, RankingCandidate]:
    """Eligibility-filtered lookup of specific jobs (sponsored-slot resolution).

    Returns a ``{job_id: candidate}`` map containing ONLY the ids that are still
    publicly visible — a sponsored placement whose target job has since been
    hidden/closed/expired is silently dropped (no leak), so the caller simply
    skips that sponsored slot.
    """

    if not job_ids:
        return {}
    stmt = _visible(
        select(Job).where(Job.id.in_(job_ids)),
        persona=persona,
        is_authenticated=is_authenticated,
    )
    jobs = list((await session.execute(stmt)).scalars().all())
    cands = await _materialize(session, jobs, locale=locale)
    return {c.job_id: c for c in cands}
