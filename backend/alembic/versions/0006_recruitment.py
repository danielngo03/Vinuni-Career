"""recruitment: applications + anonymous-apply reveal requests

Phase 1e: the ``recruitment`` module owns ``applications`` (a student's submitted
application to a job, carrying the immutable CV snapshot link + screening answers
+ anonymous flag) and ``application_reveal_requests`` (the anonymous-apply reveal
handshake: partner asks, student accepts/declines, 72h auto-expire).

This migration also finalizes the deferred constraints on
``application_cv_snapshots`` that ``0005_documents`` left open because the
``applications`` table did not exist yet:

- FK ``application_cv_snapshots.application_id -> applications(id)`` (CASCADE)
- ``application_cv_snapshots.application_id`` becomes ``NOT NULL``
- the partial-unique index ``uq_app_cv_snapshots_app`` created in 0005 becomes an
  effective one-snapshot-per-application guarantee once the column is NOT NULL.

Any pre-existing snapshot rows with a NULL ``application_id`` are orphans (no
``applications`` table existed before this migration) and are deleted before the
NOT NULL is applied so the live upgrade cannot fail.

Postgres-only constructs are guarded by ``is_postgres``:

- partial discovery / idempotency indexes (``WHERE deleted_at IS NULL`` / ``IS NOT NULL``)
- the partial unique index preventing a duplicate ACTIVE application per (job, applicant)
- the ``set_updated_at`` trigger on ``applications``
- the deferred ``application_cv_snapshots`` FK + NOT NULL

The SQLite unit-test path builds the schema from ORM metadata and never runs this
migration.

Revision ID: 0006_recruitment
Revises: 0005_documents
Create Date: 2026-06-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_recruitment"
down_revision: str | None = "0005_documents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FK_SNAPSHOT_APP = "fk_app_cv_snapshots_application"


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    uuid_default = sa.text("gen_random_uuid()") if is_postgres else None

    # ----------------------------------------------------------- applications
    op.create_table(
        "applications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=uuid_default),
        sa.Column("job_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("jobs.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("applicant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        # Denormalized from jobs.org_id so partner application reads are scoped to
        # the caller's org without joining jobs on every list.
        sa.Column("org_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="submitted"),
        sa.Column("cover_letter", sa.Text(), nullable=True),
        sa.Column("screening_answers", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("is_anonymous", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("application_cv_snapshots.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("reveal_approved_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reveal_approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.String(50), nullable=True),
        sa.Column("rejection_note", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(200), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("last_status_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )

    # ------------------------------------------- application_reveal_requests
    op.create_table(
        "application_reveal_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=uuid_default),
        sa.Column("application_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("applications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("requester_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("requester_org_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.UniqueConstraint("application_id", "requester_org_id",
                            name="uq_reveal_app_org"),
    )

    if is_postgres:
        op.create_index(
            "idx_applications_student", "applications", ["applicant_id", "status"],
            postgresql_where=sa.text("deleted_at IS NULL"),
        )
        op.create_index(
            "idx_applications_job", "applications", ["job_id", "status"],
            postgresql_where=sa.text("deleted_at IS NULL"),
        )
        op.create_index(
            "idx_applications_org", "applications", ["org_id", "job_id", "status"],
            postgresql_where=sa.text("deleted_at IS NULL"),
        )
        op.create_index(
            "idx_applications_idem", "applications", ["applicant_id", "idempotency_key"],
            postgresql_where=sa.text("idempotency_key IS NOT NULL"),
        )
        # One ACTIVE application per (job, applicant); a withdrawn/soft-deleted row
        # frees the slot so the student may re-apply.
        op.create_index(
            "uq_applications_active", "applications", ["job_id", "applicant_id"],
            unique=True,
            postgresql_where=sa.text("deleted_at IS NULL AND status <> 'withdrawn'"),
        )
        op.create_index(
            "idx_reveal_requests_app", "application_reveal_requests",
            ["application_id", "status"],
        )

        op.execute("DROP TRIGGER IF EXISTS trg_applications_updated_at ON applications;")
        op.execute(
            "CREATE TRIGGER trg_applications_updated_at BEFORE UPDATE ON applications "
            "FOR EACH ROW EXECUTE FUNCTION set_updated_at();"
        )

        # ---- Finalize the deferred application_cv_snapshots constraints. ----
        # Orphan snapshots (no application could have existed yet) are removed so
        # the SET NOT NULL below cannot fail on the live DB.
        op.execute("DELETE FROM application_cv_snapshots WHERE application_id IS NULL;")
        op.create_foreign_key(
            _FK_SNAPSHOT_APP, "application_cv_snapshots", "applications",
            ["application_id"], ["id"], ondelete="CASCADE",
        )
        op.alter_column(
            "application_cv_snapshots", "application_id",
            existing_type=postgresql.UUID(as_uuid=True), nullable=False,
        )
    else:
        op.create_index(
            "idx_applications_student", "applications", ["applicant_id", "status"]
        )
        op.create_index("idx_applications_job", "applications", ["job_id", "status"])
        op.create_index(
            "idx_reveal_requests_app", "application_reveal_requests",
            ["application_id", "status"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        # Revert the deferred application_cv_snapshots constraints to the 0005 state.
        op.alter_column(
            "application_cv_snapshots", "application_id",
            existing_type=postgresql.UUID(as_uuid=True), nullable=True,
        )
        op.drop_constraint(
            _FK_SNAPSHOT_APP, "application_cv_snapshots", type_="foreignkey"
        )

        op.execute("DROP TRIGGER IF EXISTS trg_applications_updated_at ON applications;")
        op.drop_index("idx_reveal_requests_app", table_name="application_reveal_requests")
        op.drop_index("uq_applications_active", table_name="applications")
        op.drop_index("idx_applications_idem", table_name="applications")
        op.drop_index("idx_applications_org", table_name="applications")
        op.drop_index("idx_applications_job", table_name="applications")
        op.drop_index("idx_applications_student", table_name="applications")
    else:
        op.drop_index("idx_reveal_requests_app", table_name="application_reveal_requests")
        op.drop_index("idx_applications_job", table_name="applications")
        op.drop_index("idx_applications_student", table_name="applications")

    op.drop_table("application_reveal_requests")
    op.drop_table("applications")
