"""Backfill AI-registry + knowledge-base columns the ORM models expect but the
submission migration lineage never added (model drifted ahead of migrations).

These columns (provider/alias health, alias rotation/fallback, KB document file
metadata + soft-delete) were introduced on feature branches whose migrations were
never merged into this line, so a from-scratch ``alembic upgrade head`` produced a
schema the ORM could not query (e.g. ``ai_provider_configs.last_health_status does
not exist``), breaking the dev seed and the app on a fresh reset. This additive,
idempotent backfill (``ADD COLUMN IF NOT EXISTS``) makes the migrated schema match
the models. Defaults mirror the model python-side defaults so it is also safe on a
populated table.

Revision ID: 0094_ai_kb_column_backfill
Revises: 0093_application_assignee
Create Date: 2026-07-09
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0094_ai_kb_column_backfill"
down_revision: str | None = "0093_application_assignee"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ADDS: list[tuple[str, str, str]] = [
    ("ai_provider_configs", "last_health_status", "VARCHAR(20)"),
    ("ai_provider_configs", "last_health_checked_at", "TIMESTAMP WITH TIME ZONE"),
    ("ai_model_aliases", "rotation_strategy", "VARCHAR(20) NOT NULL DEFAULT 'priority'"),
    ("ai_model_aliases", "fallback_bindings", "JSONB"),
    ("ai_model_aliases", "last_health_status", "VARCHAR(20)"),
    ("ai_model_aliases", "last_health_checked_at", "TIMESTAMP WITH TIME ZONE"),
    ("knowledge_base_documents", "file_path", "TEXT"),
    ("knowledge_base_documents", "file_size_bytes", "INTEGER"),
    ("knowledge_base_documents", "page_count", "INTEGER"),
    ("knowledge_base_documents", "chunking_mode", "VARCHAR(20) NOT NULL DEFAULT 'auto'"),
    ("knowledge_base_documents", "error_message", "TEXT"),
    ("knowledge_base_documents", "uploaded_at", "TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()"),
    ("knowledge_base_documents", "processed_at", "TIMESTAMP WITH TIME ZONE"),
    ("knowledge_base_documents", "is_deleted", "BOOLEAN NOT NULL DEFAULT false"),
    ("knowledge_base_chunks", "is_deleted", "BOOLEAN NOT NULL DEFAULT false"),
]


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return  # SQLite test schema is built from model metadata, not migrations
    for table, column, ddl in _ADDS:
        op.execute(f'ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {ddl}')


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for table, column, _ddl in reversed(_ADDS):
        op.execute(f'ALTER TABLE {table} DROP COLUMN IF EXISTS {column}')
