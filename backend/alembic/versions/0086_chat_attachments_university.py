"""chat_attachments + chat_sessions org/department scope (university control-plane).

Adds the university chatbot file/image upload + data-analysis persistence:

- ``chat_sessions.org_id`` + ``chat_sessions.department_id`` — org/department
  context captured at session-creation time so a staff chat is org-scoped and
  attributable to a department for per-department AI energy accounting. NULL for
  students / any principal without an org (additive, no backfill required).
- ``chat_attachments`` — a file/image a user attached to a chat session for AI
  analysis. Raw bytes live in signed blob storage addressed by ``storage_key``
  (INTERNAL, never returned to a client). ``analysis_json`` caches the structured,
  leakage-safe analysis result (tables + charts + summary) so a re-analysis is
  idempotent and never re-charges energy.

Merge-reconciliation note: the partner-ai-overhaul worktree ships an EQUIVALENT
``chat_attachments`` table + ``chat_sessions.org_id`` across its own migrations
(0085_chat_session_org_id and 0087_chat_attachments). This migration deliberately
uses a DISTINCT revision id (``0086_chat_attachments_university``) to avoid a
revision-string collision, and combines both changes into one revision chained off
THIS branch's head. At merge, KEEP ONE ``chat_attachments`` table + ONE
``org_id`` column — dedup the two migrations into a single revision and drop the
duplicate. This branch additionally introduces ``chat_sessions.department_id``
(not present on partner); keep it.

Revision ID: 0086_chat_attachments_university
Revises: 0085_ai_capacity_requests_and_usage_department
Create Date: 2026-07-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0086_chat_attachments_university"
down_revision: str | None = "0085_ai_capacity_requests_and_usage_department"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "chat_sessions",
        sa.Column("org_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.add_column(
        "chat_sessions",
        sa.Column("department_id", sa.Uuid(as_uuid=True), nullable=True),
    )

    op.create_table(
        "chat_attachments",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "session_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("chat_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("org_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("filename", sa.String(500), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("storage_key", sa.String(500), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="uploaded"),
        sa.Column("analysis_json", sa.JSON(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_index(
        "ix_chat_attachments_session_id", "chat_attachments", ["session_id"]
    )
    op.create_index("ix_chat_attachments_user_id", "chat_attachments", ["user_id"])
    op.create_index("ix_chat_attachments_org_id", "chat_attachments", ["org_id"])


def downgrade() -> None:
    op.drop_index("ix_chat_attachments_org_id", table_name="chat_attachments")
    op.drop_index("ix_chat_attachments_user_id", table_name="chat_attachments")
    op.drop_index("ix_chat_attachments_session_id", table_name="chat_attachments")
    op.drop_table("chat_attachments")
    op.drop_column("chat_sessions", "department_id")
    op.drop_column("chat_sessions", "org_id")
