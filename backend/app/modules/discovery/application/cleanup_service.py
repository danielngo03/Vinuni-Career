"""TTL cleanup sweep: prune expired sessions + old events (ADR-0003 registry).

Registered as ``discovery.session_cleanup`` (daily). Idempotent and time-gated: a
re-tick over an already-clean window prunes nothing. Flush-only — the scheduler job
(:mod:`app.modules.automation.scheduler.runner`) owns the commit.

Retention is config-driven: sessions past ``expires_at`` are dropped (short TTL);
events AND recommendation snapshots older than ``discovery_event_retention_days``
are dropped (longer analytics window). Pruning a session leaves its longer-lived
events/snapshots intact (the FK is ``ON DELETE SET NULL`` in Postgres).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast

from sqlalchemy import CursorResult, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.discovery.domain.models import (
    DiscoveryEvent,
    DiscoverySession,
    RecommendationSnapshot,
)


def _now() -> datetime:
    return datetime.now(tz=UTC)


async def session_cleanup(
    session: AsyncSession, *, now: datetime | None = None
) -> dict[str, int]:
    """Prune expired sessions + out-of-retention events/snapshots. Flush-only."""

    now = now or _now()
    retention = timedelta(days=get_settings().discovery_event_retention_days)
    event_cutoff = now - retention

    sessions_result = cast(
        "CursorResult[object]",
        await session.execute(
            delete(DiscoverySession).where(DiscoverySession.expires_at <= now)
        ),
    )
    events_result = cast(
        "CursorResult[object]",
        await session.execute(
            delete(DiscoveryEvent).where(DiscoveryEvent.created_at < event_cutoff)
        ),
    )
    snapshots_result = cast(
        "CursorResult[object]",
        await session.execute(
            delete(RecommendationSnapshot).where(
                RecommendationSnapshot.created_at < event_cutoff
            )
        ),
    )
    await session.flush()
    return {
        "sessions_pruned": sessions_result.rowcount or 0,
        "events_pruned": events_result.rowcount or 0,
        "snapshots_pruned": snapshots_result.rowcount or 0,
    }
