"""Analytics ORM model: ``analytics_events`` (B-548 event contract).

This is the platform-wide, append-only product-analytics ledger — distinct from
(and complementary to) two existing ledgers that already cover their own scope:

- ``discovery_events`` (``app.modules.discovery``) — anonymous/session/user
  surface-engagement + ad-attribution signals for the ranking/ads surfaces.
  Unchanged by this module.
- ``audit_logs`` (``app.shared.audit``) — compliance/security audit trail for
  every write action (who/what/when + before/after), not analytics-shaped.
- ``outbox_events`` (``app.shared.models``) — transactional domain events with
  at-least-once consumer semantics (e.g. ``offer.accepted`` -> career_outcomes).

``analytics_events`` is for everything else B-548 lists that isn't already
covered by the above: job/application/cv/ai/event/notification/workflow
product-analytics facts consumed by dashboards and reporting read models, never
by a redelivery-sensitive consumer. Rows are terminal facts, not pending work —
there is no ``published_at``/claim semantics here.

Privacy-safe by construction: ``properties`` is a JSONB bag that MUST pass
through :mod:`app.modules.analytics.domain.taxonomy` before it is ever
constructed — the service layer is the only writer and enforces this.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import Base, JsonType


class AnalyticsEvent(Base):
    """A single privacy-safe product-analytics fact."""

    __tablename__ = "analytics_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # e.g. "job.applied", "cv.export.completed", "ai.tool.called" — see taxonomy.py.
    event_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    # The domain aggregate this fact is about (job|application|cv_export|event|
    # notification|ai_tool|workflow_execution|ad_placement).
    aggregate_type: Mapped[str] = mapped_column(String(40), nullable=False)
    aggregate_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    # Plain (FK-less) — high-volume append-only ledger, mirrors discovery_events.
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    actor_type: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )  # student|partner|university|system|guest
    session_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    # Allowlisted, metadata-only (see taxonomy.sanitize_properties). Never PII,
    # never raw CV/prompt text, never provider/model/token internals.
    properties: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_analytics_events_aggregate", "aggregate_type", "aggregate_id"),
        Index("ix_analytics_events_type_time", "event_type", "occurred_at"),
    )
