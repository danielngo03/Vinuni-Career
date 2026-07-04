"""Public-read facade for events (ADR-0008 §4).

The ``marketplace`` overview needs read-only, guest-tier views of events — but
must **not** deep-import the ``Event`` ORM or re-implement the visibility
predicate. This facade is the single allowed surface: it returns already-projected,
enriched public summaries so callers never touch event internals.

All functions here use the **guest** visibility tier (public-tier only): the
marketplace is a public surface. Summaries are enriched with the organizer
``company`` block, batch-loading orgs so a page of N events costs one extra query,
never N.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.opportunities.api import event_presenters as presenters
from app.modules.opportunities.application.event_visibility import (
    apply_visible_filter,
    guest_levels,
)
from app.modules.opportunities.domain.event_models import Event
from app.modules.organization.application import org_reporting_facade


def _now() -> datetime:
    return datetime.now(tz=UTC)


async def enrich_summaries(
    session: AsyncSession, events: list[Event], *, locale: str
) -> list[dict]:
    """Project ``events`` to enriched public summaries, batch-loading organizers."""

    org_ids = {e.org_id for e in events}
    orgs = await org_reporting_facade.summaries_for(session, org_ids)
    return [
        presenters.public_event_summary(e, company=orgs.get(e.org_id), locale=locale)
        for e in events
    ]


def _visible(stmt: Select) -> Select:
    return apply_visible_filter(stmt, levels=guest_levels(), now=_now())


async def list_upcoming_summaries(
    session: AsyncSession, *, limit: int, locale: str = "vi"
) -> list[dict]:
    """Soonest upcoming guest-visible events (by ``starts_at`` ascending)."""

    stmt = _visible(select(Event))
    stmt = stmt.order_by(Event.starts_at.asc(), Event.id.asc()).limit(max(limit, 0))
    events = list((await session.execute(stmt)).scalars().all())
    return await enrich_summaries(session, events, locale=locale)


async def list_sponsored_summaries(
    session: AsyncSession, *, limit: int, locale: str = "vi"
) -> list[dict]:
    """Guest-visible events flagged ``is_sponsored`` (real flag — never fabricated)."""

    stmt = _visible(select(Event).where(Event.is_sponsored.is_(True)))
    stmt = stmt.order_by(Event.starts_at.asc(), Event.id.asc()).limit(max(limit, 0))
    events = list((await session.execute(stmt)).scalars().all())
    return await enrich_summaries(session, events, locale=locale)


async def list_featured_summaries(
    session: AsyncSession, *, limit: int, locale: str = "vi"
) -> list[dict]:
    """Guest-visible events flagged ``is_featured`` (real flag — never fabricated)."""

    stmt = _visible(select(Event).where(Event.is_featured.is_(True)))
    stmt = stmt.order_by(Event.starts_at.asc(), Event.id.asc()).limit(max(limit, 0))
    events = list((await session.execute(stmt)).scalars().all())
    return await enrich_summaries(session, events, locale=locale)


async def list_related_summaries(
    session: AsyncSession,
    *,
    seed_event_ids: list[uuid.UUID],
    limit: int,
    locale: str = "vi",
) -> list[dict]:
    """Upcoming events ranked from coarse session event signals.

    This keeps personalization deterministic and free: recently viewed event
    type, format, organizer, and tags influence ordering. If no seed event is
    visible, return an empty list so callers can use their normal fallback.
    """

    page_limit = max(limit, 0)
    if page_limit == 0 or not seed_event_ids:
        return []

    seed_stmt = _visible(select(Event).where(Event.id.in_(seed_event_ids)))
    seeds = list((await session.execute(seed_stmt)).scalars().all())
    if not seeds:
        return []

    seed_types = {e.event_type for e in seeds}
    seed_formats = {e.format for e in seeds}
    seed_org_ids = {e.org_id for e in seeds}
    seed_tags = {
        str(tag).strip().lower()
        for e in seeds
        for tag in (e.tags or [])
        if str(tag).strip()
    }

    candidate_stmt = _visible(select(Event).where(Event.id.not_in(seed_event_ids)))
    candidate_stmt = candidate_stmt.order_by(Event.starts_at.asc(), Event.id.asc()).limit(
        max(page_limit * 8, 24)
    )
    candidates = list((await session.execute(candidate_stmt)).scalars().all())

    def score(event: Event) -> tuple[int, datetime, uuid.UUID]:
        tags = {
            str(tag).strip().lower()
            for tag in (event.tags or [])
            if str(tag).strip()
        }
        value = 0
        if event.event_type in seed_types:
            value += 4
        if event.format in seed_formats:
            value += 2
        if event.org_id in seed_org_ids:
            value += 3
        value += min(len(tags & seed_tags), 3)
        return (-value, event.starts_at, event.id)

    ranked = [event for event in sorted(candidates, key=score) if -score(event)[0] > 0]
    return await enrich_summaries(session, ranked[:page_limit], locale=locale)


async def count_visible_events(session: AsyncSession) -> int:
    """Total number of guest-visible (upcoming/in-progress) events."""

    from sqlalchemy import func

    return (
        await session.execute(_visible(select(func.count(Event.id))))
    ).scalar_one()
