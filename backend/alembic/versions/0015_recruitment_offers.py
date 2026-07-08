"""recruitment offers: offers table (8-state, Fernet salary, one-live-per-app) (ADR-0007)

The terminal POSITIVE outcome layer on top of the ADR-0004 stage engine, ADR-0005
scorecards, and ADR-0006 interviews:

- ``offers`` — ONE comp offer per scheduled "round" (the Offer pipeline stage),
  with an 8-state approval/response machine (``draft | pending_approval | approved
  | sent | accepted | declined | expired | rescinded``). ``salary_amount`` holds a
  Fernet ciphertext (recruiter + owning-student only). A Postgres PARTIAL unique
  index enforces "at most one LIVE offer per application" (LIVE = draft /
  pending_approval / approved / sent); it is dialect-guarded so it is skipped on
  SQLite (unit tests rely on the service-layer guard, mirroring
  ``uq_interview_open_per_stage`` / ``uq_scorecard_reviewer_active``).

NO DDL on ``applications`` — ``status='hired'`` is a pure domain widening
(``applications.status`` is already VARCHAR(30); ``candidate_stages.exit_kind`` is
already VARCHAR(20) nullable, so ``'hired'`` is a domain vocab value only). NO seed
data (there are no offers until a partner creates one). The SQLite unit-test path
builds the schema from ORM metadata and never runs this migration.

Revision ID: 0015_recruitment_offers
Revises: 0014_recruitment_interviews
Create Date: 2026-06-28
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015_recruitment_offers"
down_revision: str | None = "0014_recruitment_interviews"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_IDX_OFFER_ORG_STATUS = "idx_offers_org_status"
_IDX_OFFER_APP = "idx_offers_application"
_IDX_OFFER_STAGE = "idx_offers_stage"
_UQ_OFFER_LIVE = "uq_offer_live_per_application"

_LIVE_STATES = "('draft', 'pending_approval', 'approved', 'sent')"


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    uuid_default = sa.text("gen_random_uuid()") if is_postgres else None

    op.create_table(
        "offers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=uuid_default),
        sa.Column("application_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("applications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stage_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("pipeline_stages.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("position_title", sa.String(255), nullable=False),
        sa.Column("department", sa.String(200), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        # Fernet ciphertext (urlsafe base64) — never stored in plaintext at rest.
        sa.Column("salary_amount", sa.String(255), nullable=True),
        sa.Column("salary_currency", sa.String(5), nullable=False, server_default="VND"),
        sa.Column("salary_period", sa.String(20), nullable=False,
                  server_default="monthly"),
        sa.Column("benefits_summary", sa.Text(), nullable=True),
        sa.Column("terms_notes", sa.Text(), nullable=True),
        sa.Column("expiry_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("approved_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("student_response_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decline_reason", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )
    op.create_index(_IDX_OFFER_ORG_STATUS, "offers", ["org_id", "status"])
    op.create_index(_IDX_OFFER_APP, "offers", ["application_id"])
    op.create_index(_IDX_OFFER_STAGE, "offers", ["stage_id"])

    if is_postgres:
        # At most one LIVE offer per application. Partial unique index — dialect-
        # guarded; SQLite tests rely on the service guard.
        op.create_index(
            _UQ_OFFER_LIVE,
            "offers",
            ["application_id"],
            unique=True,
            postgresql_where=sa.text(f"status IN {_LIVE_STATES}"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        op.drop_index(_UQ_OFFER_LIVE, table_name="offers")

    op.drop_index(_IDX_OFFER_STAGE, table_name="offers")
    op.drop_index(_IDX_OFFER_APP, table_name="offers")
    op.drop_index(_IDX_OFFER_ORG_STATUS, table_name="offers")
    op.drop_table("offers")
