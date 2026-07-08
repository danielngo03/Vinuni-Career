"""recruitment scorecards: scorecards + scorecard_scores (ADR-0005 §5)

The evaluation layer on top of the shipped ADR-0004 stage engine:

- ``scorecards`` — ONE reviewer's evaluation of ONE candidate at ONE pipeline
  stage. Editable-in-place by the author (per-scorecard optimistic ``version``);
  withdraw is a soft ``status`` transition (``submitted`` -> ``withdrawn``). A
  Postgres PARTIAL unique index enforces "at most one ACTIVE scorecard per
  (application, stage, reviewer)" (``WHERE status = 'submitted'``); it is
  dialect-guarded so it is skipped on SQLite (unit tests rely on the
  service-layer upsert guard, mirroring ``uq_candidate_stage_active``).
- ``scorecard_scores`` — one criterion score (1..5) per scorecard (normalized,
  not JSONB). Unique ``(scorecard_id, criterion_key)``; a ``CHECK score BETWEEN
  1 AND 5`` guards the range on Postgres.

NO change to ``applications`` / ``pipeline_stages`` / ``candidate_stages`` and NO
seed data step (there are no scorecards until reviewers submit; the criteria are a
domain constant, not seeded rows). The SQLite unit-test path builds the schema
from ORM metadata and never runs this migration.

Revision ID: 0013_recruitment_scorecards
Revises: 0012_pipeline_stage_engine
Create Date: 2026-06-28
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013_recruitment_scorecards"
down_revision: str | None = "0012_pipeline_stage_engine"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UQ_REVIEWER_ACTIVE = "uq_scorecard_reviewer_active"
_IDX_APP_STAGE = "idx_scorecards_app_stage"


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    uuid_default = sa.text("gen_random_uuid()") if is_postgres else None

    # --------------------------------------------------------------- scorecards
    op.create_table(
        "scorecards",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=uuid_default),
        sa.Column("application_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("applications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stage_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("pipeline_stages.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("submitted_by_user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("recommendation", sa.String(20), nullable=False),
        sa.Column("overall_score", sa.Numeric(2, 1), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="submitted"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )
    op.create_index(_IDX_APP_STAGE, "scorecards", ["application_id", "stage_id"])
    op.create_index("idx_scorecards_org", "scorecards", ["org_id"])
    op.create_index("idx_scorecards_reviewer", "scorecards", ["submitted_by_user_id"])

    # --------------------------------------------------------- scorecard_scores
    op.create_table(
        "scorecard_scores",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=uuid_default),
        sa.Column("scorecard_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("scorecards.id", ondelete="CASCADE"), nullable=False),
        sa.Column("criterion_key", sa.String(40), nullable=False),
        sa.Column("score", sa.SmallInteger(), nullable=False),
        sa.UniqueConstraint("scorecard_id", "criterion_key", name="uq_scorecard_score_key"),
        sa.CheckConstraint("score BETWEEN 1 AND 5", name="ck_scorecard_score_range"),
    )
    op.create_index("idx_scorecard_scores_card", "scorecard_scores", ["scorecard_id"])

    if is_postgres:
        # At most one ACTIVE (submitted) scorecard per (application, stage,
        # reviewer). Partial unique index — dialect-guarded; SQLite tests rely on
        # the service-layer upsert guard. A withdrawn row is excluded, so a
        # reviewer may submit again after withdrawing.
        op.create_index(
            _UQ_REVIEWER_ACTIVE,
            "scorecards",
            ["application_id", "stage_id", "submitted_by_user_id"],
            unique=True,
            postgresql_where=sa.text("status = 'submitted'"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        op.drop_index(_UQ_REVIEWER_ACTIVE, table_name="scorecards")

    op.drop_index("idx_scorecard_scores_card", table_name="scorecard_scores")
    op.drop_table("scorecard_scores")

    op.drop_index("idx_scorecards_reviewer", table_name="scorecards")
    op.drop_index("idx_scorecards_org", table_name="scorecards")
    op.drop_index(_IDX_APP_STAGE, table_name="scorecards")
    op.drop_table("scorecards")
