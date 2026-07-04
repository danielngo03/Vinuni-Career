"""Sponsored-slot frequency capping — the anti-fatigue guard for paid inventory.

A viewer (session or logged-in user) must never see the same sponsored
placement an unbounded number of times in a short window. This module answers
one question, read-only, from the existing ``discovery_events`` ledger (no new
table): "which placements has this viewer already seen ``cap`` or more times in
the last ``window_hours`` hours?"

The caller (``ranking_service`` / ``marketplace.overview_service``) excludes the
returned placement ids from ``inventory_facade.list_active_sponsored`` — the cap
never fabricates organic content in place of a capped sponsored slot, it simply
lets that slot go unfilled (hide-if-empty, same discipline as everywhere else in
discovery). Anonymous viewers with neither a session nor a user id are always
uncapped (there is nothing to key the count on).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.discovery.domain.models import DiscoveryEvent

DEFAULT_CAP = 3
DEFAULT_WINDOW_HOURS = 24


async def over_capped_placements(
    session: AsyncSession,
    *,
    session_id: uuid.UUID | None,
    user_id: uuid.UUID | None,
    cap: int = DEFAULT_CAP,
    window_hours: int = DEFAULT_WINDOW_HOURS,
    now: datetime | None = None,
) -> set[uuid.UUID]:
    """Placement ids at/over the impression cap for this viewer, right now."""

    if session_id is None and user_id is None:
        return set()

    now = now or datetime.now(tz=UTC)
    since = now - timedelta(hours=window_hours)
    viewer_match = []
    if session_id is not None:
        viewer_match.append(DiscoveryEvent.session_id == session_id)
    if user_id is not None:
        viewer_match.append(DiscoveryEvent.user_id == user_id)

    stmt = (
        select(DiscoveryEvent.placement_id, func.count(DiscoveryEvent.id))
        .where(
            DiscoveryEvent.event_type == "impression",
            DiscoveryEvent.placement_id.isnot(None),
            DiscoveryEvent.created_at >= since,
            or_(*viewer_match),
        )
        .group_by(DiscoveryEvent.placement_id)
        .having(func.count(DiscoveryEvent.id) >= cap)
    )
    rows = (await session.execute(stmt)).all()
    return {row[0] for row in rows if row[0] is not None}
