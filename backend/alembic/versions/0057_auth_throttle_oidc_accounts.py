"""Add auth_throttles (resend/forgot-password rate limiting) and oidc_accounts
(Google/Facebook social login linking).

Revision ID: 0057_auth_throttle_oidc_accounts
Revises: 0056_application_timeline_events
Create Date: 2026-07-04

NOTE: the migration history already had three parallel heads before this
change (0055_cv_canvas_photo, 0055_salary_experience_modes,
0056_application_timeline_events all off 0054). This revision continues from
0056 only — it does not attempt to merge the existing heads, which is outside
this task's scope. Use ``alembic upgrade heads`` (plural) locally until those
branches are merged.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0057_auth_throttle_oidc_accounts"
down_revision = "0056_application_timeline_events"
branch_labels = None
depends_on = None

_JSON = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "auth_throttles",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("scope", sa.String(50), nullable=False),
        sa.Column("key_hash", sa.String(128), nullable=False),
        sa.Column(
            "window_started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "last_attempt_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("scope", "key_hash", name="uq_auth_throttles_scope_key"),
    )

    op.create_table(
        "oidc_accounts",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("provider_user_id", sa.String(255), nullable=False),
        sa.Column("extra_claims", _JSON, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "provider", "provider_user_id", name="uq_oidc_accounts_provider_user"
        ),
    )
    op.create_index("ix_oidc_accounts_user_id", "oidc_accounts", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_oidc_accounts_user_id", table_name="oidc_accounts")
    op.drop_table("oidc_accounts")
    op.drop_table("auth_throttles")
