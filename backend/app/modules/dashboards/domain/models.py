"""Read-model governance ORM (B-558): the market-intelligence snapshot.

``market_intelligence_service.get_market_intelligence`` was a fully live-
composed aggregate (no cached state, recomputed every request). B-558 requires
every dashboard/recommendation/analytics/competition-intelligence read model to
define: a source (here, ``opportunities.job_read_facade.market_aggregates``), a
refresh strategy (scheduled — see ``dashboards.snapshot_service`` +
``automation.scheduler.jobs._dashboards_market_intelligence_refresh``), stale-
data behavior, a fallback UI signal, and a reconciliation check.

This table is a deliberate SINGLETON — one row, ``id=1`` — since market
intelligence is a platform-wide (not per-org) aggregate. ``computed_at`` is the
staleness clock the service layer compares against
``settings.market_intelligence_stale_after_seconds``.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import Base, JsonType

SINGLETON_ID = 1


class MarketIntelligenceSnapshot(Base):
    """The single cached market-intelligence report + when it was computed."""

    __tablename__ = "market_intelligence_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=SINGLETON_ID)
    report: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
