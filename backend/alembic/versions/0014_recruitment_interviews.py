"""recruitment interviews: interviews + interview_assignees, scorecard FK, threshold (ADR-0006)

The interview + reviewer-assignee layer on top of the ADR-0004 stage engine and
the ADR-0005 scorecards:

- ``interviews`` — ONE editable-in-place interview per scheduled round, bound to an
  application + pipeline stage (the round IS the stage; the interview carries only a
  delivery ``mode ∈ {onsite, online, phone}``). ``meeting_link`` is Fernet-encrypted
  at rest (revealed only to attendees). A Postgres PARTIAL unique index enforces "at
  most one OPEN (``scheduled``) interview per (application, stage)"; it is
  dialect-guarded so it is skipped on SQLite (unit tests rely on the service-layer
  guard, mirroring ``uq_candidate_stage_active`` / ``uq_scorecard_reviewer_active``).
- ``interview_assignees`` — the interviewer membership (PERSON mode, V1). Unique
  ``(interview_id, user_id)``; index on ``user_id`` for the "my interviews" read.
  This set is the upgraded advance-gate's ``required`` denominator.
- ``scorecards.interview_id`` — the ADR-0005 §5 / DATA_MODEL §9 nullable FK
  (``ON DELETE SET NULL``), auto-linked on submit when an open interview exists.
- ``pipeline_stages.score_threshold`` — NUMERIC(2,1) NULL; meaningful only when
  ``required_action='score_threshold'`` (BUSINESS_LOGIC §3.1).

NO seed data step (there are no interviews until a partner schedules one; seeded
stages stay ``manual`` so the upgraded gate is dormant). The SQLite unit-test path
builds the schema from ORM metadata and never runs this migration.

Revision ID: 0014_recruitment_interviews
Revises: 0013_recruitment_scorecards
Create Date: 2026-06-28
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014_recruitment_interviews"
down_revision: str | None = "0013_recruitment_scorecards"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UQ_OPEN_PER_STAGE = "uq_interview_open_per_stage"
_IDX_IV_APP_STAGE = "idx_interviews_app_stage"
_IDX_IV_ORG = "idx_interviews_org"
_IDX_IVA_USER = "idx_interview_assignees_user"
_IDX_SCORECARD_IV = "idx_scorecards_interview"


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    uuid_default = sa.text("gen_random_uuid()") if is_postgres else None

    # ----------------------------------------------------------------- interviews
    op.create_table(
        "interviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=uuid_default),
        sa.Column("application_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("applications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stage_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("pipeline_stages.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("title", sa.String(150), nullable=True),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_minutes", sa.SmallInteger(), nullable=False,
                  server_default="60"),
        sa.Column("location", sa.String(500), nullable=True),
        # Fernet ciphertext (urlsafe base64) — never stored in plaintext at rest.
        sa.Column("meeting_link", sa.String(1000), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="scheduled"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )
    op.create_index(_IDX_IV_APP_STAGE, "interviews", ["application_id", "stage_id"])
    op.create_index(_IDX_IV_ORG, "interviews", ["org_id"])

    # ------------------------------------------------------- interview_assignees
    op.create_table(
        "interview_assignees",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=uuid_default),
        sa.Column("interview_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("interviews.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.UniqueConstraint("interview_id", "user_id", name="uq_interview_assignee"),
    )
    op.create_index(_IDX_IVA_USER, "interview_assignees", ["user_id"])

    # ----------------------------------------------- scorecards.interview_id (FK)
    op.add_column(
        "scorecards",
        sa.Column("interview_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_scorecards_interview",
        "scorecards",
        "interviews",
        ["interview_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(_IDX_SCORECARD_IV, "scorecards", ["interview_id"])

    # ----------------------------------------- pipeline_stages.score_threshold
    op.add_column(
        "pipeline_stages",
        sa.Column("score_threshold", sa.Numeric(2, 1), nullable=True),
    )

    if is_postgres:
        # At most one OPEN (scheduled) interview per (application, stage). Partial
        # unique index — dialect-guarded; SQLite tests rely on the service guard.
        op.create_index(
            _UQ_OPEN_PER_STAGE,
            "interviews",
            ["application_id", "stage_id"],
            unique=True,
            postgresql_where=sa.text("status = 'scheduled'"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        op.drop_index(_UQ_OPEN_PER_STAGE, table_name="interviews")

    op.drop_column("pipeline_stages", "score_threshold")

    op.drop_index(_IDX_SCORECARD_IV, table_name="scorecards")
    op.drop_constraint("fk_scorecards_interview", "scorecards", type_="foreignkey")
    op.drop_column("scorecards", "interview_id")

    op.drop_index(_IDX_IVA_USER, table_name="interview_assignees")
    op.drop_table("interview_assignees")

    op.drop_index(_IDX_IV_ORG, table_name="interviews")
    op.drop_index(_IDX_IV_APP_STAGE, table_name="interviews")
    op.drop_table("interviews")
