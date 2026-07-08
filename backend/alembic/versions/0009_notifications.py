"""notifications: in-app Notification Center feed

Adds the canonical ``notifications`` in-app feed table (``docs/DATA_MODEL.md``
§14, ``docs/API_CONTRACTS.md`` Notifications section). This is the bell-center
feed with per-row read state — distinct from ``notification_outbox`` (async
email/push dispatch). A product event may insert a row here AND enqueue an outbox
row in the same transaction.

``channels`` (list) and ``delivered_at`` (``{channel: timestamp}``) are stored as
JSONB rather than a native PG ``VARCHAR[]`` so the ORM ``JsonType`` model runs
identically on PostgreSQL (runtime) and SQLite (unit tests), matching every other
list/map column in the schema. The covering index orders ``created_at DESC`` for
the newest-first feed query.

The SQLite unit-test path builds the schema from ORM metadata and never runs this
migration.

Revision ID: 0009_notifications
Revises: 0008_cv_ai_suggestions
Create Date: 2026-06-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_notifications"
down_revision: str | None = "0008_cv_ai_suggestions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    uuid_default = sa.text("gen_random_uuid()") if is_postgres else None
    json_type = postgresql.JSONB() if is_postgres else sa.JSON()

    op.create_table(
        "notifications",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=uuid_default,
        ),
        sa.Column(
            "recipient_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "sender_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("notif_type", sa.String(100), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("action_url", sa.String(500), nullable=True),
        sa.Column(
            "is_read",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "channels",
            json_type,
            nullable=False,
            server_default=sa.text("'[]'::jsonb") if is_postgres else sa.text("'[]'"),
        ),
        sa.Column(
            "delivered_at",
            json_type,
            nullable=False,
            server_default=sa.text("'{}'::jsonb") if is_postgres else sa.text("'{}'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )

    if is_postgres:
        op.create_index(
            "idx_notif_recipient",
            "notifications",
            ["recipient_id", "is_read", sa.text("created_at DESC")],
        )
    else:
        op.create_index(
            "idx_notif_recipient",
            "notifications",
            ["recipient_id", "is_read", "created_at"],
        )


def downgrade() -> None:
    op.drop_index("idx_notif_recipient", table_name="notifications")
    op.drop_table("notifications")
