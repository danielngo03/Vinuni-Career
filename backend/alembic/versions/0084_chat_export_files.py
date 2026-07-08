"""chat_export_files: server-side files the assistant generates for download.

Additive migration. Creates ``chat_export_files`` — the store for AI-assistant
generated downloads (e.g. an applicants .xlsx export). Fetched only via the
RBAC-checked ``/ai/chat/exports/{id}`` endpoint (raw bytes/path never exposed).
Bound to the requesting user + org; ``expires_at`` bounds link lifetime.

Revision ID: 0084_chat_export_files
Revises: 0083_ai_billable_usage
Create Date: 2026-07-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0084_chat_export_files"
down_revision: str | None = "0083_ai_billable_usage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chat_export_files",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("org_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("filename", sa.String(length=200), nullable=False),
        sa.Column("mime", sa.String(length=120), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_chat_export_files_user_id", "chat_export_files", ["user_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_chat_export_files_user_id", table_name="chat_export_files")
    op.drop_table("chat_export_files")
