"""Internal jobs/events read facade for cross-module surfaces.

Other modules (``recruitment``, ``dashboards``) resolve job identity/labels and a
student's upcoming registered events through this seam instead of importing the
``Job`` / ``Event`` / ``EventRegistration`` ORM, so the module boundary holds
(`docs/ARCHITECTURE.md`: communicate through interfaces/read models). Only the
small projected shape a consumer needs is returned — never the full owner-only
job/event row (visibility, moderation internals, applicant answers, etc.).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.opportunities.domain.event_lifecycle import (
    REG_CANCELLED,
    event_type_label,
    format_label,
    registration_state_label,
)
from app.modules.opportunities.domain.event_models import Event, EventRegistration
from app.modules.opportunities.domain.models import Job

_UPCOMING_EVENTS_CAP = 3


@dataclass(frozen=True)
class JobRef:
    id: uuid.UUID
    org_id: uuid.UUID
    title: str
    status: str
    application_deadline: datetime | None
    created_at: datetime
    posted_by: uuid.UUID


def to_ref(job: Job) -> JobRef:
    return JobRef(
        id=job.id,
        org_id=job.org_id,
        title=job.title,
        status=job.status,
        application_deadline=job.application_deadline,
        created_at=job.created_at,
        posted_by=job.posted_by,
    )


async def get_job_title(session: AsyncSession, job_id: uuid.UUID | None) -> str | None:
    if job_id is None:
        return None
    return (
        await session.execute(select(Job.title).where(Job.id == job_id))
    ).scalar_one_or_none()


async def get_job_titles(
    session: AsyncSession, job_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, str]:
    ids = {i for i in job_ids if i is not None}
    if not ids:
        return {}
    rows = (
        await session.execute(select(Job.id, Job.title).where(Job.id.in_(ids)))
    ).all()
    return {row.id: row.title for row in rows}


async def get_job_ref(
    session: AsyncSession, job_id: uuid.UUID, *, include_deleted: bool = False
) -> JobRef | None:
    stmt = select(Job).where(Job.id == job_id)
    if not include_deleted:
        stmt = stmt.where(Job.deleted_at.is_(None))
    job = (await session.execute(stmt)).scalar_one_or_none()
    return to_ref(job) if job is not None else None


async def get_org_scoped_job_ref(
    session: AsyncSession, *, job_id: uuid.UUID, org_id: uuid.UUID, active_only: bool = False
) -> JobRef | None:
    """A job ref scoped to ``org_id``, or ``None`` if missing/deleted/cross-org."""

    from app.modules.opportunities.domain import lifecycle as job_lifecycle

    stmt = select(Job).where(
        Job.id == job_id, Job.org_id == org_id, Job.deleted_at.is_(None)
    )
    if active_only:
        stmt = stmt.where(Job.status == job_lifecycle.ACTIVE)
    job = (await session.execute(stmt)).scalar_one_or_none()
    return to_ref(job) if job is not None else None


async def list_org_job_refs(
    session: AsyncSession, *, org_id: uuid.UUID
) -> list[JobRef]:
    rows = (
        await session.execute(
            select(Job).where(Job.org_id == org_id, Job.deleted_at.is_(None))
        )
    ).scalars().all()
    return [to_ref(j) for j in rows]


async def decrement_application_count(
    session: AsyncSession, job_id: uuid.UUID, *, lock: bool = False
) -> None:
    """Decrement the denormalized ``jobs.application_count`` by one, floored at 0."""

    stmt = select(Job).where(Job.id == job_id, Job.deleted_at.is_(None))
    if lock:
        stmt = stmt.with_for_update()
    job = (await session.execute(stmt)).scalar_one_or_none()
    if job is None:
        return
    job.application_count = max(0, job.application_count - 1)


async def increment_application_count(session: AsyncSession, job_id: uuid.UUID) -> None:
    """Increment the denormalized ``jobs.application_count`` by one (no-op if missing)."""

    job = (
        await session.execute(
            select(Job).where(Job.id == job_id, Job.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if job is None:
        return
    job.application_count += 1


async def get_job_title_and_skills(
    session: AsyncSession, job_id: uuid.UUID
) -> tuple[str | None, list[str]]:
    """``(title, required_skills)`` for a job, or ``(None, [])`` if missing."""

    row = (
        await session.execute(
            select(Job.title, Job.required_skills).where(Job.id == job_id)
        )
    ).first()
    if row is None:
        return None, []
    return row.title, list(row.required_skills or [])


async def count_all_jobs(session: AsyncSession) -> int:
    """Total non-deleted jobs across the platform (university KPI reporting)."""

    from sqlalchemy import func

    return (
        await session.execute(
            select(func.count()).select_from(Job).where(Job.deleted_at.is_(None))
        )
    ).scalar_one()


async def count_published_events(session: AsyncSession) -> int:
    """Total published, non-deleted events (university KPI reporting)."""

    from sqlalchemy import func

    return (
        await session.execute(
            select(func.count()).select_from(Event).where(
                Event.status == "published", Event.deleted_at.is_(None)
            )
        )
    ).scalar_one()


async def fraud_scan_snapshot(
    session: AsyncSession, job_id: uuid.UUID
) -> dict | None:
    """Projected job shape for the moderation fraud scanner, or ``None``.

    Returns only what the scanner needs: identity, owning org, the combined
    user-visible text, and the org's posting volume in the last 7 days —
    never the full owner-only job row.
    """

    from datetime import timedelta

    from sqlalchemy import func

    job = (
        await session.execute(select(Job).where(Job.id == job_id))
    ).scalar_one_or_none()
    if job is None:
        return None

    window_start = datetime.now(UTC) - timedelta(days=7)
    org_jobs_last_7d = (
        await session.execute(
            select(func.count())
            .select_from(Job)
            .where(Job.org_id == job.org_id, Job.created_at >= window_start)
        )
    ).scalar_one()

    text = " ".join(
        part for part in (job.title, job.description, job.requirements) if part
    )
    return {
        "id": job.id,
        "org_id": job.org_id,
        "text": text,
        "org_jobs_last_7d": int(org_jobs_last_7d),
    }


async def market_aggregates(session: AsyncSession) -> dict:
    """Aggregate-only hiring stats for university market intelligence.

    No per-student, per-application, or partner-name data — counts only
    (``docs/AI_PRODUCT_SPEC.md`` §3 ``market_intelligence`` privacy shape).
    """

    from collections import Counter
    from datetime import timedelta

    from sqlalchemy import func

    from app.modules.opportunities.domain import lifecycle as job_lifecycle

    now = datetime.now(UTC)
    d30 = now - timedelta(days=30)
    d60 = now - timedelta(days=60)
    skill_scan_cap = 500  # bounded read over newest active jobs

    active_jobs = (
        await session.execute(
            select(func.count())
            .select_from(Job)
            .where(Job.status == job_lifecycle.ACTIVE)
        )
    ).scalar_one()

    jobs_last_30d = (
        await session.execute(
            select(func.count())
            .select_from(Job)
            .where(Job.published_at.is_not(None), Job.published_at >= d30)
        )
    ).scalar_one()

    jobs_prev_30d = (
        await session.execute(
            select(func.count())
            .select_from(Job)
            .where(
                Job.published_at.is_not(None),
                Job.published_at >= d60,
                Job.published_at < d30,
            )
        )
    ).scalar_one()

    et_rows = (
        await session.execute(
            select(Job.employment_type, func.count())
            .where(Job.status == job_lifecycle.ACTIVE)
            .group_by(Job.employment_type)
        )
    ).all()

    disclosed = (
        await session.execute(
            select(func.count())
            .select_from(Job)
            .where(
                Job.status == job_lifecycle.ACTIVE,
                Job.salary_is_disclosed.is_(True),
            )
        )
    ).scalar_one()

    # Skill demand: JSON-list column — portable aggregation in Python.
    skill_rows = (
        await session.execute(
            select(Job.required_skills)
            .where(Job.status == job_lifecycle.ACTIVE)
            .order_by(Job.created_at.desc())
            .limit(skill_scan_cap)
        )
    ).scalars()
    counter: Counter[str] = Counter()
    for skills in skill_rows:
        for skill in skills or []:
            if isinstance(skill, str) and skill.strip():
                counter[skill.strip().lower()] += 1

    return {
        "active_jobs": int(active_jobs),
        "jobs_last_30d": int(jobs_last_30d),
        "jobs_prev_30d": int(jobs_prev_30d),
        "employment_type_counts": {row[0]: int(row[1]) for row in et_rows},
        "skill_counts": dict(counter),
        "disclosed_salary_jobs": int(disclosed),
    }


async def list_upcoming_registered_events(
    session: AsyncSession, *, user_id: uuid.UUID, locale: str = "vi"
) -> list[dict]:
    """Up to 3 upcoming (future) registered events for a student, soonest first.

    Only active registrations (confirmed/waitlisted) for events that have not
    started are returned; cancelled/attended registrations and past events are
    excluded. No other attendee PII.
    """

    now = datetime.now(UTC)
    stmt = (
        select(EventRegistration, Event)
        .join(Event, Event.id == EventRegistration.event_id)
        .where(
            EventRegistration.user_id == user_id,
            EventRegistration.status != REG_CANCELLED,
            Event.starts_at > now,
            Event.deleted_at.is_(None),
        )
        .order_by(Event.starts_at.asc())
        .limit(_UPCOMING_EVENTS_CAP)
    )
    rows = (await session.execute(stmt)).all()
    out: list[dict] = []
    for reg, event in rows:
        out.append(
            {
                "event_id": str(event.id),
                "title": event.title,
                "event_type": event.event_type,
                "event_type_label": event_type_label(event.event_type, locale=locale),
                "format": event.format,
                "format_label": format_label(event.format, locale=locale),
                "starts_at": event.starts_at.isoformat() if event.starts_at else None,
                "ends_at": event.ends_at.isoformat() if event.ends_at else None,
                "venue_name": event.venue_name,
                "registration_status": reg.status,
                "registration_status_label": registration_state_label(
                    reg.status, locale=locale
                ),
            }
        )
    return out
