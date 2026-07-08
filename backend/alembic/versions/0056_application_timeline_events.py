"""Create application_timeline_events (real student application timeline).

Revision ID: 0056_application_timeline_events
Revises: 0054_otp_and_onboarding
Create Date: 2026-07-04
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0056_application_timeline_events"
down_revision = "0054_otp_and_onboarding"
branch_labels = None
depends_on = None

_JSON = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "application_timeline_events",
        sa.Column(
            "id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(60), nullable=False),
        sa.Column("label_en", sa.String(200), nullable=False),
        sa.Column("label_vi", sa.String(200), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column(
            "metadata", _JSON, nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["application_id"], ["applications.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_application_timeline_events_application_id",
        "application_timeline_events",
        ["application_id"],
    )
    op.create_index(
        "ix_application_timeline_events_app_occurred",
        "application_timeline_events",
        ["application_id", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_application_timeline_events_app_occurred",
        table_name="application_timeline_events",
    )
    op.drop_index(
        "ix_application_timeline_events_application_id",
        table_name="application_timeline_events",
    )
    op.drop_table("application_timeline_events")
