"""Per-campaign advertising analytics read model (``ad_placement_metrics_daily``).

A genuine per ``(placement, date)`` AGGREGATE projection of the privacy-safe
``discovery_events`` ledger, following the
``partner_job_metrics_daily`` / ``job_competition_daily`` projection pattern. It
lets a partner see their OWN campaign performance (impressions / clicks / CTR /
apply-starts / cost-per-apply-start) with a single indexed read instead of a heavy
scan of the event ledger on every dashboard load.

Kept in a dedicated model file (NOT ``models.py``) so the campaign-analytics slice
never collides with the placement/creative lifecycle tables. ``org_id`` is
denormalized onto the row (resolved from ``sponsored_placements`` at refresh time —
``discovery_events`` itself is org-agnostic) so a partner-scoped read never needs a
join just to enforce tenant isolation.

PRIVACY: aggregates only. There is no viewer id, session id, candidate id, raw IP,
or any other PII column here — the projection is built by COUNTING events, never by
copying an individual viewer's row. Cost-per-apply-start is derived at READ time
from the placement's already-frozen campaign price; no spend/pacing model is stored
here (that is a documented follow-up).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Integer,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import Base


class AdPlacementMetricsDaily(Base):
    """Per ``(placement_id, metric_date)`` sponsored-delivery funnel counters.

    Grain: one row per ``(placement_id, metric_date)``. Every counter is an
    absolute recomputed value (the refresh SETs, never blindly increments) so a
    re-run of the sweep is idempotent and self-healing.
    """

    __tablename__ = "ad_placement_metrics_daily"
    __table_args__ = (
        UniqueConstraint(
            "placement_id", "metric_date", name="uq_ad_placement_metrics_daily"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    placement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sponsored_placements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    metric_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    # Sponsored-delivery funnel counters (from discovery_events, sponsored surface).
    impressions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    clicks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    views: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    apply_starts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    save_intents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    event_register_intents: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
