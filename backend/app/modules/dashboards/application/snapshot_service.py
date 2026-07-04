"""Market-intelligence read-model governance (B-558): refresh + stale-read + reconcile.

Three operations, one snapshot row (``MarketIntelligenceSnapshot``, singleton):

- :func:`refresh` — recompute the report from the source aggregates and upsert
  the snapshot with a fresh ``computed_at``. Called by the scheduled sweep
  (``automation.scheduler.jobs``) on a fixed interval — the refresh strategy.
- :func:`read_for_display` — the fallback-UI contract: prefer the snapshot when
  it exists and is within the freshness window; when it is missing or stale,
  compute live (so the surface is never empty) AND opportunistically persist
  that live compute as the new snapshot. If the live compute itself fails, fall
  back to the last known snapshot (however old) with ``stale=True`` rather than
  a 500 — a dashboard degrades, it never breaks.
- :func:`reconcile` — the reconciliation check: recompute live and compare
  against the stored snapshot's ``active_jobs`` count (the cheapest sentinel
  field); returns a drift report for the ops sweep to log (never auto-writes —
  ``refresh`` already re-derives from source on its own cadence).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.dashboards.application.market_intelligence_service import build_report
from app.modules.dashboards.domain.models import SINGLETON_ID, MarketIntelligenceSnapshot
from app.modules.opportunities.application import job_read_facade

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _stale_after() -> timedelta:
    return timedelta(seconds=get_settings().market_intelligence_stale_after_seconds)


async def _load(session: AsyncSession) -> MarketIntelligenceSnapshot | None:
    return await session.get(MarketIntelligenceSnapshot, SINGLETON_ID)


async def _compute_report(session: AsyncSession) -> dict:
    aggregates = await job_read_facade.market_aggregates(session)
    return build_report(**aggregates)


async def refresh(session: AsyncSession, *, now: datetime | None = None) -> dict[str, int]:
    """Recompute + upsert the snapshot. The scheduled refresh strategy."""

    now = now or _now()
    report = await _compute_report(session)
    row = await _load(session)
    if row is None:
        row = MarketIntelligenceSnapshot(id=SINGLETON_ID, report=report, computed_at=now)
        session.add(row)
    else:
        row.report = report
        row.computed_at = now
    await session.flush()
    return {"refreshed": 1}


async def read_for_display(session: AsyncSession, *, now: datetime | None = None) -> dict:
    """Report + governance metadata (``computed_at``, ``stale``) for display.

    Never raises to the caller for a source-query failure once a snapshot
    exists — falls back to the last known snapshot marked ``stale=True``.
    """

    now = now or _now()
    row = await _load(session)
    fresh = row is not None and (now - _aware(row.computed_at)) <= _stale_after()
    if fresh:
        assert row is not None
        return {**row.report, "computed_at": row.computed_at.isoformat(), "stale": False}

    try:
        report = await _compute_report(session)
    except Exception:  # noqa: BLE001 — degrade to the stale snapshot, never 500
        if row is None:
            raise
        logger.warning("market_intelligence.live_compute_failed_fallback_to_snapshot")
        return {**row.report, "computed_at": row.computed_at.isoformat(), "stale": True}

    # Opportunistic refresh: persist this live compute so the next read is fresh.
    if row is None:
        session.add(MarketIntelligenceSnapshot(id=SINGLETON_ID, report=report, computed_at=now))
    else:
        row.report = report
        row.computed_at = now
    await session.flush()
    return {**report, "computed_at": now.isoformat(), "stale": False}


async def reconcile(session: AsyncSession, *, now: datetime | None = None) -> dict[str, int]:
    """Drift check: live ``active_jobs`` vs the stored snapshot's value.

    Read-only — logs drift for ops visibility; the next scheduled ``refresh``
    self-heals it. Returns ``{"checked": 1, "drift": 0|1}``.
    """

    row = await _load(session)
    if row is None:
        return {"checked": 0, "drift": 0}
    live = await _compute_report(session)
    drifted = int(live.get("active_jobs") != row.report.get("active_jobs"))
    if drifted:
        logger.warning(
            "market_intelligence.reconcile_drift",
            extra={
                "snapshot_active_jobs": row.report.get("active_jobs"),
                "live_active_jobs": live.get("active_jobs"),
            },
        )
    return {"checked": 1, "drift": drifted}


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)
