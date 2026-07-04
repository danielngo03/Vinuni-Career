"""Partner recruiting-intelligence read models (`docs/PARTNER_RBAC_ANALYTICS_SPEC.md`
§"Recruiting Intelligence Read Models"). Kept in a dedicated module file (NOT
``models.py``) so this partner-analytics slice never collides with the sibling
platform-wide ``analytics_events`` ledger (`domain/models.py` /
``application/ingestion_service.py``) — that ledger is a separate, general
product-analytics fact stream; this file is the partner-command-center-specific
projection set defined by the RBAC/analytics spec.

Three tables, three different jobs:

- ``partner_job_metrics_daily`` — a genuine per (org, job, date) AGGREGATE read
  model. Counters are incremented in place via upsert-on-conflict at the moment
  the underlying action happens (job detail view, save, apply, share, ...) —
  this is NOT a raw event ledger, so it stays cheap to join into the partner
  dashboard and never needs an offline rebuild step to stay current.
- ``partner_job_metric_dimensions_daily`` — a companion breakdown table for the
  coarse, PII-safe dimensions the spec calls out (device class / student tier /
  major group / year group). Kept as a narrow (dimension_type, dimension_value)
  fact table instead of exploding the daily grain with dimension columns.
- ``partner_candidate_access_events`` — an APPEND-ONLY audit-style ledger (never
  aggregated in place, never updated) for sensitive candidate access: who
  opened/previewed/downloaded a CV or requested/viewed a revealed identity, and
  when. Mirrors the shape of ``audit_logs`` (bigint PK, no soft delete).

No PII, raw IP, raw user-agent, or exact location is ever stored in any of these
tables.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import Base, BigIntPk


class PartnerJobMetricDaily(Base):
    """Per (org, job, date) funnel counters + source-mix breakdown.

    Grain: one row per ``(job_id, metric_date)``. ``org_id`` is denormalized onto
    the row (same convention as ``applications.org_id``) so tenant-scoped reads
    never need a join through ``jobs`` just to filter by org.
    """

    __tablename__ = "partner_job_metrics_daily"
    __table_args__ = (
        UniqueConstraint("job_id", "metric_date", name="uq_job_metrics_daily_job_date"),
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
    metric_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    # Funnel counters (spec: impressions, detail_views, cta_clicks, apply_starts,
    # applications_submitted, save_clicks, share_clicks).
    impressions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    detail_views: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cta_clicks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    apply_starts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    applications_submitted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    save_clicks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    share_clicks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Source-mix breakdown (spec: organic, search, recommendation, sponsored,
    # invitation, direct/referral). Every event increments exactly one source
    # column in addition to whichever funnel counter(s) it also increments.
    src_organic: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    src_search: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    src_recommendation: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    src_sponsored: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    src_invitation: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    src_direct: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class PartnerJobMetricDimensionDaily(Base):
    """Per (org, job, date, dimension_type, dimension_value) coarse breakdown.

    ``dimension_type`` is one of ``device_class`` / ``student_tier`` /
    ``major_group`` / ``year_group``. ``dimension_value`` is always a coarse
    bucket (e.g. ``mobile``, ``student``, a broad major grouping, a graduation-
    year cohort bucket) — never a raw free-text field, never PII.
    """

    __tablename__ = "partner_job_metric_dimensions_daily"
    __table_args__ = (
        UniqueConstraint(
            "job_id", "metric_date", "dimension_type", "dimension_value",
            name="uq_job_metric_dim_daily",
        ),
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
    metric_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    dimension_type: Mapped[str] = mapped_column(String(20), nullable=False)
    dimension_value: Mapped[str] = mapped_column(String(40), nullable=False)
    event_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class PartnerCandidateAccessEvent(Base):
    """Append-only "who accessed which candidate" audit ledger.

    Powers the security/compliance review surface ("who viewed which CV") and the
    ``access_alerts`` dashboard widget. Never updated/soft-deleted — mirrors
    ``audit_logs``. ``candidate_id`` is stored for internal security review even
    when the application is still anonymous in the partner UI (the system already
    resolves the applicant to serve the CV file; withholding it here would defeat
    the purpose of the access log).
    """

    __tablename__ = "partner_candidate_access_events"

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    actor_department_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL"), nullable=True
    )
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # application_opened | cv_previewed | cv_downloaded | identity_reveal_requested
    # | identity_revealed_viewed
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
