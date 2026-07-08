"""``job_competition_daily`` — the per-job competition read model (WS-5).

A materialized projection of the CALIBER-of-real-applicants inputs the
student-facing competition signal needs, so the hot job-detail read hits ONE
indexed row instead of a live ``applications`` × ``application_cv_snapshots``
multi-domain join (backend rule: "no dashboard with heavy live multi-domain
joins; use projections/read models").

Grain: one CURRENT-STATE row per ``job_id`` (unique). "daily" names the refresh
CADENCE (a nightly sweep keeps every active job fresh); the row is ALSO recomputed
on each apply event so a new applicant is reflected immediately. It is a
recompute-and-UPSERT projection (overwrite in place), not an incrementing counter
ledger like ``partner_job_metrics_daily`` — the inputs are a live aggregate, not a
historical event series.

Stored fields = exactly ``domain.competition_scoring.CompetitionStats`` (minus
``seats``, which the read overrides with the job's LIVE ``headcount`` so a seat
edit is reflected without waiting for a refresh) plus a ``refreshed_at`` freshness
stamp. The four ``dist_*`` buckets partition the SCORED active applicants by
caliber; NULL-fit applicants (uploaded-document applies / pre-migration history)
are counted in ``active_applications`` but excluded from every bucket — unknown
quality, never fit 0. No PII, no individual scores, no identities are ever stored
here — only coarse per-job aggregates.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import Base


class JobCompetitionDaily(Base):
    """Per-job materialized competition inputs (one row per ``job_id``)."""

    __tablename__ = "job_competition_daily"
    __table_args__ = (
        UniqueConstraint("job_id", name="uq_job_competition_daily_job"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Seats at refresh time (hiring target / headcount). The read overrides this
    # with the LIVE job headcount; kept here for the offline sweep + auditing.
    seats: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Total active (submitted | under_review, not soft-deleted) applications.
    active_applications: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    # Caliber distribution over SCORED active applicants (apply-time fit known).
    dist_developing: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dist_mixed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dist_strong: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dist_top: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    refreshed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
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
