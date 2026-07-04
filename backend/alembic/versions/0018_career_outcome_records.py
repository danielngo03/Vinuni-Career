"""career_outcomes: career_outcome_records (ADR-0007 deferred materializer)

The read/reporting landing table for student career outcomes (DATA_MODEL §27).
This slice ships its FIRST source: the non-blocking ``offer.accepted`` outbox
event, materialized at ``trust_level=4`` / ``source='system_estimate'`` (an
estimated outcome from the application -> offer-accepted flow, BUSINESS_LOGIC §13).

The columns here are exactly the privacy-safe subset the ``offer.accepted`` payload
carries (application_id, offer_id, org_id, employer_org_id, position_title,
start_date) plus bookkeeping: ``outcome_type``, ``trust_level``, ``source``,
``source_event_id`` (UNIQUE — the originating OutboxEvent id, the materializer's
idempotency guard) and ``recorded_at``. NO salary and NO student_id/PII — those
DATA_MODEL §27 columns belong to higher-trust partner-confirmed / survey sources
and are added by a later migration when those sources land.

Postgres-only constructs (the ``set_updated_at`` trigger) are guarded by
``is_postgres``; the SQLite unit-test path creates the schema from ORM metadata.

Revision ID: 0018_career_outcome_records
Revises: 0017_advertising_placements
Create Date: 2026-06-28
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018_career_outcome_records"
down_revision: str | None = "0017_advertising_placements"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    uuid_default = sa.text("gen_random_uuid()") if is_postgres else None
    now_default = sa.text("NOW()") if is_postgres else sa.func.now()

    op.create_table(
        "career_outcome_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=uuid_default),
        # From the offer.accepted payload (no FK: cross-module, consumed as data).
        sa.Column("application_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("offer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employer_org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position_title", sa.String(300), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("outcome_type", sa.String(30), nullable=False,
                  server_default="hired"),
        sa.Column("trust_level", sa.SmallInteger(), nullable=False,
                  server_default="4"),
        sa.Column("source", sa.String(30), nullable=False,
                  server_default="system_estimate"),
        sa.Column("source_event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=now_default),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=now_default),
    )

    # Idempotency guard for the materializer: one record per source event.
    op.create_unique_constraint(
        "uq_career_outcomes_source_event", "career_outcome_records",
        ["source_event_id"],
    )
    # Reporting indexes: by employer (with recency) and by recency alone.
    op.create_index(
        "idx_career_outcomes_employer", "career_outcome_records",
        ["employer_org_id", "recorded_at"],
    )
    op.create_index(
        "idx_career_outcomes_recorded", "career_outcome_records", ["recorded_at"],
    )

    if is_postgres:
        op.execute(
            "DROP TRIGGER IF EXISTS trg_career_outcome_records_updated_at "
            "ON career_outcome_records;"
        )
        op.execute(
            "CREATE TRIGGER trg_career_outcome_records_updated_at BEFORE UPDATE ON "
            "career_outcome_records FOR EACH ROW EXECUTE FUNCTION set_updated_at();"
        )


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        op.execute(
            "DROP TRIGGER IF EXISTS trg_career_outcome_records_updated_at "
            "ON career_outcome_records;"
        )

    op.drop_index("idx_career_outcomes_recorded", table_name="career_outcome_records")
    op.drop_index("idx_career_outcomes_employer", table_name="career_outcome_records")
    op.drop_constraint(
        "uq_career_outcomes_source_event", "career_outcome_records", type_="unique"
    )
    op.drop_table("career_outcome_records")
