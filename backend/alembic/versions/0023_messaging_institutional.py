"""messaging: institutional in-app threads (ADR-0012)

The ``messaging`` module owns three tables backing a governed institutional channel
(university↔student, university↔partner, partner↔candidate) — never a peer social
inbox:

- ``message_threads`` — a ``direct`` thread or a one-way ``announcement``, bound to
  a governing context (``application``/``support``/``team``) and scoped by
  ``org_id`` (tenant isolation). ``is_anonymous`` is denormalized from the bound
  application and drives partner-side identity masking at projection time.
- ``message_thread_participants`` — per-user membership + read-state (``last_read_at``
  for unread), ``can_reply`` (announcement recipients are one-way), ``muted``.
- ``messages`` — one posted message; ``sender_id`` null = system; ``client_dedupe_key``
  makes a retried POST idempotent.

Postgres-only constructs are guarded by ``is_postgres``:

- partial indexes (``WHERE deleted_at IS NULL`` / ``removed_at IS NULL``)
- the partial unique on the idempotent dedupe key
  (``WHERE client_dedupe_key IS NOT NULL``)
- the partial unique enforcing one direct thread per (application context, org)
- the ``set_updated_at`` trigger on ``message_threads``

The SQLite unit-test path builds the schema from ORM metadata and never runs this
migration; the partial uniques there are enforced by the service-layer guards.

Revision ID: 0023_messaging_institutional
Revises: 0022_ai_settings
Create Date: 2026-06-28
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0023_messaging_institutional"
down_revision: str | None = "0022_ai_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    uuid_default = sa.text("gen_random_uuid()") if is_postgres else None

    # ------------------------------------------------------- message_threads
    op.create_table(
        "message_threads",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=uuid_default),
        sa.Column("kind", sa.String(20), nullable=False, server_default="direct"),
        sa.Column("context_type", sa.String(20), nullable=True),
        # FK-by-convention to applications.id (no hard cross-module FK).
        sa.Column("context_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("subject", sa.String(300), nullable=True),
        sa.Column("is_anonymous", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column("created_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )

    # -------------------------------------------- message_thread_participants
    op.create_table(
        "message_thread_participants",
        sa.Column("thread_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("message_threads.id", ondelete="CASCADE"),
                  primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("role_in_thread", sa.String(20), nullable=False,
                  server_default="member"),
        sa.Column("can_reply", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("muted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # --------------------------------------------------------------- messages
    op.create_table(
        "messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=uuid_default),
        sa.Column("thread_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("message_threads.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("sender_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("reply_to_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("messages.id", ondelete="SET NULL"), nullable=True),
        sa.Column("client_dedupe_key", sa.String(120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index(
        "idx_messages_thread", "messages", ["thread_id", "created_at"]
    )

    if is_postgres:
        op.create_index(
            "idx_threads_org", "message_threads", ["org_id", "status"],
            postgresql_where=sa.text("deleted_at IS NULL"),
        )
        op.create_index(
            "idx_threads_context", "message_threads", ["context_type", "context_id"],
        )
        op.create_index(
            "idx_threads_last_msg", "message_threads",
            [sa.text("last_message_at DESC")],
        )
        op.create_index(
            "idx_participants_user", "message_thread_participants", ["user_id"],
            postgresql_where=sa.text("removed_at IS NULL"),
        )
        # Idempotent send: one row per (thread, sender, client_dedupe_key).
        op.create_index(
            "uq_message_dedupe", "messages",
            ["thread_id", "sender_id", "client_dedupe_key"], unique=True,
            postgresql_where=sa.text("client_dedupe_key IS NOT NULL"),
        )
        # One live direct thread per (application context, org).
        op.create_index(
            "uq_thread_application", "message_threads", ["context_id", "org_id"],
            unique=True,
            postgresql_where=sa.text(
                "context_type = 'application' AND deleted_at IS NULL"
            ),
        )
        op.execute(
            "DROP TRIGGER IF EXISTS trg_message_threads_updated_at ON message_threads;"
        )
        op.execute(
            "CREATE TRIGGER trg_message_threads_updated_at BEFORE UPDATE ON "
            "message_threads FOR EACH ROW EXECUTE FUNCTION set_updated_at();"
        )
    else:
        op.create_index("idx_threads_org", "message_threads", ["org_id", "status"])
        op.create_index(
            "idx_threads_context", "message_threads", ["context_type", "context_id"]
        )
        op.create_index(
            "idx_participants_user", "message_thread_participants", ["user_id"]
        )


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        op.execute(
            "DROP TRIGGER IF EXISTS trg_message_threads_updated_at ON message_threads;"
        )
        op.drop_index("uq_thread_application", table_name="message_threads")
        op.drop_index("uq_message_dedupe", table_name="messages")
        op.drop_index("idx_participants_user", table_name="message_thread_participants")
        op.drop_index("idx_threads_last_msg", table_name="message_threads")
        op.drop_index("idx_threads_context", table_name="message_threads")
        op.drop_index("idx_threads_org", table_name="message_threads")
    else:
        op.drop_index("idx_participants_user", table_name="message_thread_participants")
        op.drop_index("idx_threads_context", table_name="message_threads")
        op.drop_index("idx_threads_org", table_name="message_threads")

    op.drop_index("idx_messages_thread", table_name="messages")
    op.drop_table("messages")
    op.drop_table("message_thread_participants")
    op.drop_table("message_threads")
