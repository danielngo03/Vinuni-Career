"""messaging V2: parties, message-request gate, attachments (owner decision 2026-07-09)

Extends the ADR-0012 institutional channel (migration ``0023``) into a full product:

- ``message_threads`` gains ``thread_kind`` (richer discriminator), the first-contact
  message-request gate (``request_state`` / ``request_message_count``) and
  ``initiator_party_id`` (FK-by-convention — no hard FK, avoids a threads<->parties cycle).
- ``messages`` gains ``sender_party_id`` + ``has_attachments``.
- ``message_thread_participants`` gains ``party_id``.
- NEW ``message_thread_parties`` — the 1–2 sides of a conversation. A ``user`` party is
  an individual; an ``org`` party is a partner/university acting as a single Page (shared
  team inbox), optionally routed to a department / assignee. ``identity_mode`` decides how
  the party renders to the other side (``org`` = masked Page, ``person`` = real name).
- NEW ``message_attachments`` — files/images bound to a message; ``storage_key`` is a
  documents-store key never returned raw (gated download re-checks thread access).

Postgres-only partial indexes are guarded by ``is_postgres``; the SQLite unit-test path
builds from ORM metadata and never runs this migration.

Revision ID: 0091_messaging_v2
Revises: 0090_chat_export_files
Create Date: 2026-07-09

Rebased onto the live ``vinuni_career`` lineage head ``0090_chat_export_files``
(was ``0084_ai_provider_health_fields``, a different fork now quarantined in
``versions_orphaned/``) so it chains as a single head after the partner-ai /
partner-chatbot migrations rather than forking Alembic.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0091_messaging_v2"
down_revision: str | None = "0090_chat_export_files"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    uuid_default = sa.text("gen_random_uuid()") if is_postgres else None

    # ------------------------------------------------ message_threads columns
    op.add_column(
        "message_threads",
        sa.Column("thread_kind", sa.String(20), nullable=True),
    )
    op.add_column(
        "message_threads",
        sa.Column(
            "request_state", sa.String(20), nullable=False, server_default="accepted"
        ),
    )
    op.add_column(
        "message_threads",
        sa.Column(
            "request_message_count", sa.Integer(), nullable=False, server_default="0"
        ),
    )
    op.add_column(
        "message_threads",
        sa.Column("initiator_party_id", postgresql.UUID(as_uuid=True), nullable=True),
    )

    # -------------------------------------------------------- messages columns
    op.add_column(
        "messages",
        sa.Column("sender_party_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "messages",
        sa.Column(
            "has_attachments", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )

    # --------------------------------------- message_thread_participants column
    op.add_column(
        "message_thread_participants",
        sa.Column("party_id", postgresql.UUID(as_uuid=True), nullable=True),
    )

    # ------------------------------------------------- message_thread_parties
    op.create_table(
        "message_thread_parties",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True,
            server_default=uuid_default,
        ),
        sa.Column(
            "thread_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("message_threads.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("party_kind", sa.String(10), nullable=False),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column(
            "org_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=True,
        ),
        sa.Column(
            "identity_mode", sa.String(10), nullable=False, server_default="person"
        ),
        sa.Column(
            "assigned_department_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("departments.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column(
            "assigned_user_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column(
            "assignment_state", sa.String(12), nullable=False,
            server_default="unassigned",
        ),
        sa.Column("last_read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("muted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index("idx_parties_thread", "message_thread_parties", ["thread_id"])
    op.create_index(
        "idx_parties_org", "message_thread_parties", ["org_id", "assignment_state"]
    )
    op.create_index(
        "idx_parties_assignee", "message_thread_parties", ["assigned_user_id"]
    )
    op.create_index("idx_parties_user", "message_thread_parties", ["user_id"])

    # ----------------------------------------------------- message_attachments
    op.create_table(
        "message_attachments",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True,
            server_default=uuid_default,
        ),
        sa.Column(
            "message_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("messages.id", ondelete="CASCADE"), nullable=True,
        ),
        sa.Column(
            "thread_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("message_threads.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "uploader_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("file_name", sa.String(300), nullable=False),
        sa.Column("content_type", sa.String(120), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("storage_key", sa.String(500), nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_attachments_message", "message_attachments", ["message_id"])
    op.create_index("idx_attachments_thread", "message_attachments", ["thread_id"])

    if is_postgres:
        op.create_index(
            "idx_threads_request", "message_threads", ["request_state"],
            postgresql_where=sa.text("deleted_at IS NULL"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        op.drop_index("idx_threads_request", table_name="message_threads")

    op.drop_index("idx_attachments_thread", table_name="message_attachments")
    op.drop_index("idx_attachments_message", table_name="message_attachments")
    op.drop_table("message_attachments")

    op.drop_index("idx_parties_user", table_name="message_thread_parties")
    op.drop_index("idx_parties_assignee", table_name="message_thread_parties")
    op.drop_index("idx_parties_org", table_name="message_thread_parties")
    op.drop_index("idx_parties_thread", table_name="message_thread_parties")
    op.drop_table("message_thread_parties")

    op.drop_column("message_thread_participants", "party_id")
    op.drop_column("messages", "has_attachments")
    op.drop_column("messages", "sender_party_id")
    op.drop_column("message_threads", "initiator_party_id")
    op.drop_column("message_threads", "request_message_count")
    op.drop_column("message_threads", "request_state")
    op.drop_column("message_threads", "thread_kind")
