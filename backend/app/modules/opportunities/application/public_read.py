"""Public-read facade for the ``opportunities`` module.

Other modules (``marketplace`` overview, ``organization`` company directory)
need read-only, guest-tier views of jobs — but must **not** deep-import the
``Job`` ORM or re-implement the visibility predicate. This facade is the single
allowed surface: it returns already-projected, enriched public summaries (or a
correlated count subquery) so callers never touch job internals.

All functions here use the **guest** visibility tier (public-tier only): the
marketplace and the unauthenticated company directory are public surfaces.
Summaries are enriched with the employer ``company`` block, batch-loading orgs
so a page of N jobs costs one extra query, never N.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import ScalarSelect, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.opportunities.api import presenters
from app.modules.opportunities.application.visibility import (
    apply_visible_filter,
    guest_levels,
)
from app.modules.opportunities.domain.models import Job
from app.modules.organization.application import org_reporting_facade


def _now() -> datetime:
    return datetime.now(tz=UTC)


async def enrich_summaries(
    session: AsyncSession,
    jobs: list[Job],
    *,
    locale: str,
    saved_ids: set[uuid.UUID] | None = None,
) -> list[dict]:
    """Project ``jobs`` to enriched public summaries, batch-loading employers.

    Pass ``saved_ids`` (a set of job UUIDs the current user saved) to inject the
    ``is_saved`` flag per summary. Omit (or pass ``None``) for guest requests.
    """

    org_ids = {j.org_id for j in jobs}
    orgs = await org_reporting_facade.summaries_for(session, org_ids)
    return [
        presenters.public_job_summary(
            j,
            company=orgs.get(j.org_id),
            locale=locale,
            is_saved=j.id in saved_ids if saved_ids is not None else False,
        )
        for j in jobs
    ]


def _visible(stmt):
    return apply_visible_filter(stmt, levels=guest_levels(), now=_now())


async def list_public_job_summaries_for_org(
    session: AsyncSession, *, org_id: uuid.UUID, limit: int, locale: str = "vi"
) -> list[dict]:
    """Guest-visible open roles for one org, newest first (enriched)."""

    stmt = _visible(select(Job).where(Job.org_id == org_id))
    stmt = stmt.order_by(Job.published_at.desc(), Job.id.desc()).limit(max(limit, 0))
    jobs = list((await session.execute(stmt)).scalars().all())
    return await enrich_summaries(session, jobs, locale=locale)


async def list_sponsored_summaries(
    session: AsyncSession, *, limit: int, locale: str = "vi"
) -> list[dict]:
    """Guest-visible jobs flagged ``is_sponsored`` (real flag — never fabricated)."""

    stmt = _visible(select(Job).where(Job.is_sponsored.is_(True)))
    stmt = stmt.order_by(Job.published_at.desc(), Job.id.desc()).limit(max(limit, 0))
    jobs = list((await session.execute(stmt)).scalars().all())
    return await enrich_summaries(session, jobs, locale=locale)


async def list_featured_summaries(
    session: AsyncSession, *, limit: int, locale: str = "vi"
) -> list[dict]:
    """Guest-visible jobs flagged ``is_featured`` (real flag — never fabricated)."""

    stmt = _visible(select(Job).where(Job.is_featured.is_(True)))
    stmt = stmt.order_by(Job.published_at.desc(), Job.id.desc()).limit(max(limit, 0))
    jobs = list((await session.execute(stmt)).scalars().all())
    return await enrich_summaries(session, jobs, locale=locale)


async def list_recent_summaries(
    session: AsyncSession, *, limit: int, locale: str = "vi"
) -> list[dict]:
    """Most recently published guest-visible jobs (enriched)."""

    stmt = _visible(select(Job))
    stmt = stmt.order_by(Job.published_at.desc(), Job.id.desc()).limit(max(limit, 0))
    jobs = list((await session.execute(stmt)).scalars().all())
    return await enrich_summaries(session, jobs, locale=locale)


async def count_visible_jobs(session: AsyncSession) -> int:
    """Total number of guest-visible jobs across the platform."""

    return (await session.execute(_visible(select(func.count(Job.id))))).scalar_one()


async def count_open_for_applications(session: AsyncSession) -> int:
    """Guest-visible jobs still accepting applications (future/null deadline).

    The visibility predicate already excludes past-deadline jobs, so this counts
    the same set; it is kept distinct so the metric reads unambiguously and stays
    correct if the predicate ever decouples listing from the apply window.
    """

    return await count_visible_jobs(session)


async def published_per_day(
    session: AsyncSession, *, start: datetime, end: datetime
) -> dict[str, int]:
    """Per-UTC-day counts of currently guest-visible jobs whose ``published_at``
    falls in ``[start, end)`` — one grouped aggregate query.

    Reuses the single :func:`_visible` predicate, so the trend can never drift
    from the live ``active_jobs`` metric: a job counts on the day it became
    publicly visible *and* only while it is still active/approved/within
    deadline (closed/expired/rejected jobs drop out, exactly like the live
    count). The day bucket uses ``func.date`` which compiles to ``date(...)`` on
    both SQLite (tests) and PostgreSQL (runtime); both normalize a UTC-stored
    timestamp to its UTC calendar day. Keys are ``YYYY-MM-DD`` strings; days with
    no jobs are simply absent (the caller zero-fills the fixed window).
    """

    day = func.date(Job.published_at)
    stmt = _visible(select(day.label("day"), func.count(Job.id).label("n"))).where(
        Job.published_at >= start, Job.published_at < end
    )
    stmt = stmt.group_by(day)
    rows = (await session.execute(stmt)).all()
    return {str(row.day): int(row.n) for row in rows}


def visible_job_count_subquery(org_id_col: Any) -> ScalarSelect[int]:
    """Correlated scalar subquery: # of guest-visible jobs for an outer org row.

    Lets the ``organization`` directory compute ``active_job_count`` in one query
    without importing the ``Job`` ORM or the visibility predicate itself.
    """

    stmt = _visible(select(func.count(Job.id))).where(Job.org_id == org_id_col)
    return stmt.correlate_except(Job).scalar_subquery()
