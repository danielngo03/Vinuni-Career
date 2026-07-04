"""Add job_alerts table.

Revision ID: 0035_job_alerts
Revises: 0034_student_avatar
Create Date: 2026-06-30

``job_alerts`` stores student subscriptions to new-job notifications.
The matching and dispatch logic runs in a Celery periodic task. Max 10
active alerts per user is enforced at the service layer.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0035_job_alerts"
down_revision = "0034_student_avatar"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "job_alerts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("keywords", sa.String(255), nullable=True),
        sa.Column("employment_type", sa.String(30), nullable=True),
        sa.Column("location_type", sa.String(20), nullable=True),
        sa.Column("province_code", sa.String(10), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("user_id", "name", name="uq_job_alerts_user_name"),
    )
    op.create_index("ix_job_alerts_user_id", "job_alerts", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_job_alerts_user_id", table_name="job_alerts")
    op.drop_table("job_alerts")
