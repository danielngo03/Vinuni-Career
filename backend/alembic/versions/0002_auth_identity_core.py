"""auth identity core: users, identities, sessions, security + preferences

Creates the Phase 1a identity-core tables and wires the deferred foreign keys that
the Phase 0 baseline left as plain UUID columns:

- ``users``, ``identities``
- ``user_preferences``, ``notification_preferences``
- ``sessions``, ``refresh_tokens``, ``email_verifications``
- ``security_events``, ``user_totp``
- deferred FKs: ``audit_logs.actor_id/session_id``, ``outbox_events.actor_id``,
  ``notification_templates.created_by``, ``notification_outbox.recipient_id``

Revision ID: 0002_auth_identity_core
Revises: 0001_baseline
Create Date: 2026-06-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_auth_identity_core"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TRIGGER_TABLES = ["users", "user_preferences", "notification_preferences"]


def _attach_updated_at_trigger(table: str) -> None:
    op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_updated_at ON {table};")
    op.execute(
        f"CREATE TRIGGER trg_{table}_updated_at "
        f"BEFORE UPDATE ON {table} "
        f"FOR EACH ROW EXECUTE FUNCTION set_updated_at();"
    )


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    uuid_default = sa.text("gen_random_uuid()") if is_postgres else None

    # --------------------------------------------------------------------- users
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=uuid_default),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("password_hash", sa.String(255), nullable=True),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_superadmin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("preferred_language", sa.String(5), nullable=False, server_default="vi"),
        sa.Column("timezone", sa.String(50), nullable=False,
                  server_default="Asia/Ho_Chi_Minh"),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("login_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_users_email", "users", ["email"],
                    postgresql_where=sa.text("deleted_at IS NULL"))

    # ---------------------------------------------------------------- identities
    op.create_table(
        "identities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=uuid_default),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("persona", sa.String(30), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.UniqueConstraint("user_id", "persona", "org_id",
                            name="uq_identities_identity"),
    )
    op.create_index("idx_identities_user", "identities", ["user_id"])

    # ----------------------------------------------------------- user_preferences
    op.create_table(
        "user_preferences",
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("locale", sa.String(5), nullable=False, server_default="vi"),
        sa.Column("timezone", sa.String(100), nullable=False,
                  server_default="Asia/Ho_Chi_Minh"),
        sa.Column("theme", sa.String(20), nullable=False, server_default="system"),
        sa.Column("quiet_hours", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("notification_settings", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )

    # --------------------------------------------------- notification_preferences
    op.create_table(
        "notification_preferences",
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("category", sa.String(100), primary_key=True),
        sa.Column("in_app_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("email_setting", sa.String(20), nullable=False,
                  server_default="immediate"),
        sa.Column("push_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )

    # ------------------------------------------------------------------- sessions
    op.create_table(
        "sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=uuid_default),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("identity_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("identities.id"), nullable=False),
        sa.Column("device_hint", sa.String(200), nullable=True),
        sa.Column("ip_hash", sa.String(128), nullable=True),
        sa.Column("city_level_location", sa.String(200), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_reason", sa.String(50), nullable=True),
    )
    op.create_index("idx_sessions_user", "sessions", ["user_id"],
                    postgresql_where=sa.text("revoked_at IS NULL"))

    # ------------------------------------------------------------- refresh_tokens
    op.create_table(
        "refresh_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=uuid_default),
        sa.Column("session_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(128), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("refresh_tokens.id"), nullable=True),
    )
    op.create_index("idx_refresh_tokens_session", "refresh_tokens", ["session_id"])

    # -------------------------------------------------------- email_verifications
    op.create_table(
        "email_verifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=uuid_default),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(128), nullable=False, unique=True),
        sa.Column("purpose", sa.String(30), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )
    op.create_index("idx_email_verifications_user", "email_verifications", ["user_id"])

    # ------------------------------------------------------------ security_events
    op.create_table(
        "security_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=uuid_default),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("sessions.id"), nullable=True),
        sa.Column("device_hint", sa.String(200), nullable=True),
        sa.Column("ip_hash", sa.String(128), nullable=True),
        sa.Column("city_level_location", sa.String(200), nullable=True),
        sa.Column("event_metadata", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )
    op.create_index("idx_security_events_user", "security_events",
                    ["user_id", "created_at"])

    # ------------------------------------------------------------------ user_totp
    op.create_table(
        "user_totp",
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("secret", sa.String(64), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )

    # ----------------------------------------------- deferred FKs from baseline
    if is_postgres:
        op.create_foreign_key("fk_audit_logs_actor", "audit_logs", "users",
                              ["actor_id"], ["id"], ondelete="SET NULL")
        op.create_foreign_key("fk_audit_logs_session", "audit_logs", "sessions",
                              ["session_id"], ["id"], ondelete="SET NULL")
        op.create_foreign_key("fk_outbox_actor", "outbox_events", "users",
                              ["actor_id"], ["id"], ondelete="SET NULL")
        op.create_foreign_key("fk_notif_templates_created_by",
                              "notification_templates", "users",
                              ["created_by"], ["id"], ondelete="SET NULL")
        op.create_foreign_key("fk_notif_outbox_recipient", "notification_outbox",
                              "users", ["recipient_id"], ["id"], ondelete="SET NULL")
        for table in _TRIGGER_TABLES:
            _attach_updated_at_trigger(table)


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        for table in _TRIGGER_TABLES:
            op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_updated_at ON {table};")
        op.drop_constraint("fk_notif_outbox_recipient", "notification_outbox",
                           type_="foreignkey")
        op.drop_constraint("fk_notif_templates_created_by", "notification_templates",
                           type_="foreignkey")
        op.drop_constraint("fk_outbox_actor", "outbox_events", type_="foreignkey")
        op.drop_constraint("fk_audit_logs_session", "audit_logs", type_="foreignkey")
        op.drop_constraint("fk_audit_logs_actor", "audit_logs", type_="foreignkey")

    op.drop_table("user_totp")
    op.drop_index("idx_security_events_user", table_name="security_events")
    op.drop_table("security_events")
    op.drop_index("idx_email_verifications_user", table_name="email_verifications")
    op.drop_table("email_verifications")
    op.drop_index("idx_refresh_tokens_session", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
    op.drop_index("idx_sessions_user", table_name="sessions")
    op.drop_table("sessions")
    op.drop_table("notification_preferences")
    op.drop_table("user_preferences")
    op.drop_index("idx_identities_user", table_name="identities")
    op.drop_table("identities")
    op.drop_index("idx_users_email", table_name="users")
    op.drop_table("users")
