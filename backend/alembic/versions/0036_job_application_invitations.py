"""Add job_application_invitations table.

Revision ID: 0036_job_application_invitations
Revises: 0035_job_alerts
Create Date: 2026-06-30

Partners can invite talent-pool students to apply to a specific job.
One active (non-deleted, non-terminal) invitation per (job_id, student_id)
is enforced by a partial unique index on Postgres. Status flow:
  pending → accepted | declined | expired
Soft-deleted rows keep historical data. When accepted the service creates
a real Application.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0036_job_application_invitations"
down_revision = "0035_job_alerts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "job_application_invitations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("job_id", sa.UUID(), nullable=False),
        sa.Column("student_id", sa.UUID(), nullable=False),
        sa.Column("inviting_org_id", sa.UUID(), nullable=False),
        sa.Column("inviting_user_id", sa.UUID(), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["inviting_org_id"], ["organizations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["inviting_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_job_application_invitations_job_id",
        "job_application_invitations",
        ["job_id"],
    )
    op.create_index(
        "ix_job_application_invitations_student_id",
        "job_application_invitations",
        ["student_id"],
    )
    op.create_index(
        "ix_job_application_invitations_inviting_org_id",
        "job_application_invitations",
        ["inviting_org_id"],
    )
    # Postgres-only partial unique: one active invitation per (job, student).
    # SQLite tests rely on the service guard (no partial index on SQLite).
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.create_index(
            "uq_job_invitation_active",
            "job_application_invitations",
            ["job_id", "student_id"],
            unique=True,
            postgresql_where=sa.text(
                "deleted_at IS NULL AND status = 'pending'"
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.drop_index(
            "uq_job_invitation_active", table_name="job_application_invitations"
        )
    op.drop_index(
        "ix_job_application_invitations_inviting_org_id",
        table_name="job_application_invitations",
    )
    op.drop_index(
        "ix_job_application_invitations_student_id",
        table_name="job_application_invitations",
    )
    op.drop_index(
        "ix_job_application_invitations_job_id",
        table_name="job_application_invitations",
    )
    op.drop_table("job_application_invitations")
