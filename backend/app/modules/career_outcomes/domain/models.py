"""Career-outcomes ORM models (ADR-0007 deferred consumer; DATA_MODEL §27).

``career_outcome_records`` is the read/reporting landing table for student career
outcomes. This slice ships its **first source**: the ``offer.accepted`` outbox
event seam, materialized at ``trust_level=4`` / ``source='system_estimate'`` (an
estimated outcome derived from the application -> offer-accepted flow, per
``docs/BUSINESS_LOGIC.md`` §13). The materializer consumes only the event payload
(NO recruitment ORM import, NO student PII, NO salary), so the columns this slice
creates are the privacy-safe subset the seam carries plus the bookkeeping needed
for idempotency.

Columns documented in DATA_MODEL §27 but NOT created here — ``student_id``,
``salary_amount``/``salary_currency``, ``employment_type``, ``end_date``,
``cohort_year``, ``consent_given`` — belong to the higher-trust sources
(partner-confirmed hire, survey, LinkedIn import) and are added by a later
migration when those sources land. They are deliberately absent because the
``offer.accepted`` event carries none of them; inventing them here would create
fake, unauditable data.

Types use the shared cross-database variants so the model runs on PostgreSQL
(runtime) and SQLite (unit tests). Postgres-only constructs (indexes, unique
constraint) live in the migration; the SQLite test path enforces the unique
``source_event_id`` invariant via the ORM unique constraint declared here.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    SmallInteger,
    String,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import Base

# Trust levels (DATA_MODEL §27 / BUSINESS_LOGIC §13): 1=partner_confirmed,
# 2=linkedin_verified, 3=self_reported, 4=estimated (this seam).
TRUST_LEVEL_ESTIMATED = 4
SOURCE_SYSTEM_ESTIMATE = "system_estimate"
OUTCOME_HIRED = "hired"


class CareerOutcomeRecord(Base):
    """A materialized student career outcome (one row per source event).

    The ``offer.accepted`` seam produces ``outcome_type='hired'``,
    ``trust_level=4``, ``source='system_estimate'`` rows. ``source_event_id`` is
    the originating :class:`OutboxEvent` id and is UNIQUE — the materializer's
    belt-and-suspenders idempotency guard (in addition to the event's
    ``published_at`` processed marker).
    """

    __tablename__ = "career_outcome_records"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # From the offer.accepted payload (no FK: cross-module, consumed as data).
    application_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False
    )
    offer_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    org_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    employer_org_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False
    )
    position_title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    outcome_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default=OUTCOME_HIRED
    )
    trust_level: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=TRUST_LEVEL_ESTIMATED
    )
    source: Mapped[str] = mapped_column(
        String(30), nullable=False, default=SOURCE_SYSTEM_ESTIMATE
    )
    # Originating OutboxEvent.id — UNIQUE for idempotent materialization.
    source_event_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False, unique=True
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
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
