"""chat_messages: monotonic seq + soft-delete + edited_at (conversation management).

Adds the columns the AI-assistant conversation-management endpoints (rename /
regenerate / edit-and-rerun) need:

- ``seq``        INTEGER NULL — monotonic per-session ordering index. Assigned at
                 insert time going forward; backfilled here from the existing
                 ``created_at`` order per session so old sessions gain a stable
                 order. Readers order by ``seq`` and fall back to ``created_at``
                 only when it is NULL.
- ``edited_at``  TIMESTAMPTZ NULL — set when a USER message is edited in place.
- ``is_deleted`` BOOLEAN NOT NULL DEFAULT false — soft-delete flag used by the
                 truncate-and-replay flows; every read path excludes deleted rows.

Also adds a composite index on (session_id, seq) for the ordered read path.

Backfill is Postgres-native (window function + UPDATE ... FROM). Reversible.

Revision ID: 0089_chat_message_seq_softdelete_edited
Revises: 0088_kb_audience_department
Create Date: 2026-07-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0089_chat_message_seq_softdelete_edited"
down_revision: str | None = "0088_kb_audience_department"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEX = "ix_chat_messages_session_seq"

# Backfill each session's seq from its existing created_at order (id as a stable
# tiebreaker). Runs once at upgrade time; new rows get their seq from the app.
_BACKFILL_SEQ = """
WITH ordered AS (
    SELECT
        id,
        ROW_NUMBER() OVER (
            PARTITION BY session_id
            ORDER BY created_at, id
        ) AS rn
    FROM chat_messages
)
UPDATE chat_messages AS cm
SET seq = ordered.rn
FROM ordered
WHERE cm.id = ordered.id
"""


def upgrade() -> None:
    op.add_column(
        "chat_messages",
        sa.Column("seq", sa.Integer(), nullable=True),
    )
    op.add_column(
        "chat_messages",
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "chat_messages",
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    # Backfill seq for existing rows so old sessions get a stable ordering.
    op.execute(_BACKFILL_SEQ)
    op.create_index(_INDEX, "chat_messages", ["session_id", "seq"])


def downgrade() -> None:
    op.drop_index(_INDEX, table_name="chat_messages")
    op.drop_column("chat_messages", "is_deleted")
    op.drop_column("chat_messages", "edited_at")
    op.drop_column("chat_messages", "seq")
