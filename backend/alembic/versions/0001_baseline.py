"""baseline: extensions, updated_at trigger, cross-cutting infra tables

Creates the Phase 0 cross-cutting infrastructure:

- PostgreSQL extensions (tolerant: ``vector`` only when ``PGVECTOR_ENABLED=true``)
- ``set_updated_at()`` trigger function
- ``outbox_events`` (domain event outbox)
- ``audit_logs`` (append-only audit trail; IP/UA hashes only)
- ``notification_templates`` (versioned templates)
- ``notification_outbox`` (notification dispatch queue)

Revision ID: 0001_baseline
Revises:
Create Date: 2026-06-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from app.core.config import get_settings
from sqlalchemy.dialects import postgresql

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Extensions guaranteed available on the local Postgres (see ENVIRONMENT facts).
_BASE_EXTENSIONS = ["uuid-ossp", "pg_trgm", "unaccent", "btree_gin"]

_UPDATED_AT_FN = """
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

# Mutable tables that carry an updated_at column and need the trigger.
_TRIGGER_TABLES = ["notification_templates"]


def _attach_updated_at_trigger(table: str) -> None:
    op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_updated_at ON {table};")
    op.execute(
        f"CREATE TRIGGER trg_{table}_updated_at "
        f"BEFORE UPDATE ON {table} "
        f"FOR EACH ROW EXECUTE FUNCTION set_updated_at();"
    )


def _pg_extension_available(name: str) -> bool:
    result = op.get_bind().execute(
        sa.text("SELECT 1 FROM pg_available_extensions WHERE name = :name"),
        {"name": name},
    )
    return result.fetchone() is not None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        for ext in _BASE_EXTENSIONS:
            op.execute(f'CREATE EXTENSION IF NOT EXISTS "{ext}";')
        # pgvector only when explicitly enabled AND installed in the cluster.
        if get_settings().pgvector_enabled and _pg_extension_available("vector"):
            op.execute('CREATE EXTENSION IF NOT EXISTS "vector";')
        op.execute(_UPDATED_AT_FN)

    uuid_default = sa.text("gen_random_uuid()") if is_postgres else None

    # ----------------------------------------------------------------- outbox
    op.create_table(
        "outbox_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=uuid_default),
        sa.Column("aggregate_type", sa.String(100), nullable=False),
        sa.Column("aggregate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(200), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )
    op.create_index(
        "idx_outbox_unpublished",
        "outbox_events",
        ["created_at"],
        postgresql_where=sa.text("published_at IS NULL"),
    )

    # ------------------------------------------------------------- audit_logs
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_org_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(100), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("before_snapshot", postgresql.JSONB(), nullable=True),
        sa.Column("after_snapshot", postgresql.JSONB(), nullable=True),
        sa.Column("ip_hash", sa.String(64), nullable=True),
        sa.Column("user_agent_hash", sa.String(64), nullable=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )
    op.create_index("idx_audit_actor", "audit_logs", ["actor_id", "occurred_at"])
    op.create_index(
        "idx_audit_resource", "audit_logs", ["resource_type", "resource_id", "occurred_at"]
    )

    # ------------------------------------------------- notification_templates
    op.create_table(
        "notification_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=uuid_default),
        sa.Column("owner_scope", sa.String(20), nullable=False),
        sa.Column("owner_org_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("key", sa.String(150), nullable=False),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("locale", sa.String(5), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("subject", sa.String(500), nullable=True),
        sa.Column("title", sa.String(500), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("variables_schema", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.UniqueConstraint(
            "owner_scope", "owner_org_id", "key", "channel", "locale", "version",
            name="uq_notification_templates_identity",
        ),
    )
    op.create_index(
        "idx_notification_templates_active",
        "notification_templates",
        ["key", "channel", "locale"],
        postgresql_where=sa.text("status = 'active'"),
    )

    # ---------------------------------------------------- notification_outbox
    op.create_table(
        "notification_outbox",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=uuid_default),
        sa.Column("recipient_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("template_key", sa.String(150), nullable=False),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("locale", sa.String(5), nullable=False, server_default="vi"),
        sa.Column("variables", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("dedupe_key", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "idx_notification_outbox_pending",
        "notification_outbox",
        ["created_at"],
        postgresql_where=sa.text("status = 'pending'"),
    )

    if is_postgres:
        for table in _TRIGGER_TABLES:
            _attach_updated_at_trigger(table)


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        for table in _TRIGGER_TABLES:
            op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_updated_at ON {table};")

    op.drop_index("idx_notification_outbox_pending", table_name="notification_outbox")
    op.drop_table("notification_outbox")

    op.drop_index(
        "idx_notification_templates_active", table_name="notification_templates"
    )
    op.drop_table("notification_templates")

    op.drop_index("idx_audit_resource", table_name="audit_logs")
    op.drop_index("idx_audit_actor", table_name="audit_logs")
    op.drop_table("audit_logs")

    op.drop_index("idx_outbox_unpublished", table_name="outbox_events")
    op.drop_table("outbox_events")

    if is_postgres:
        op.execute("DROP FUNCTION IF EXISTS set_updated_at();")
        # Extensions are left in place on downgrade — they are shared cluster
        # objects and may be used by other schemas.
