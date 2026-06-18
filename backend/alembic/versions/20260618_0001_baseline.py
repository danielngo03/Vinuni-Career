"""Baseline current schema and harden refresh-token sessions.

Revision ID: 20260618_0001
Revises:
Create Date: 2026-06-18
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op
from app.platform.database import models  # noqa: F401
from app.platform.database.session import Base

revision = "20260618_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if "users" not in tables:
        Base.metadata.create_all(bind=bind)
        return

    if "user_sessions" not in tables:
        Base.metadata.tables["user_sessions"].create(bind=bind)
        tables.add("user_sessions")

    for table_name in ("user_oidc_accounts", "oidc_login_tickets"):
        if table_name not in tables:
            Base.metadata.tables[table_name].create(bind=bind)

    inspector = inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("user_sessions")}
    additions = {
        "family_id": sa.Column("family_id", sa.String(length=36), nullable=True),
        "created_at": sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        "rotated_at": sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
        "revoked_at": sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        "replaced_by_id": sa.Column("replaced_by_id", sa.String(length=36), nullable=True),
    }
    for name, column in additions.items():
        if name not in columns:
            op.add_column("user_sessions", column)

    op.execute(
        sa.text(
            "UPDATE user_sessions "
            "SET family_id = id WHERE family_id IS NULL"
        )
    )
    op.execute(
        sa.text(
            "UPDATE user_sessions "
            "SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL"
        )
    )

    inspector = inspect(bind)
    indexes = {index["name"] for index in inspector.get_indexes("user_sessions")}
    if "ix_user_sessions_family_id" not in indexes:
        op.create_index(
            "ix_user_sessions_family_id",
            "user_sessions",
            ["family_id"],
            unique=False,
        )
    if "ix_user_sessions_refresh_token" not in indexes:
        op.create_index(
            "ix_user_sessions_refresh_token",
            "user_sessions",
            ["refresh_token"],
            unique=True,
        )

    foreign_keys = {
        tuple(key.get("constrained_columns") or [])
        for key in inspector.get_foreign_keys("user_sessions")
    }
    if ("replaced_by_id",) not in foreign_keys and bind.dialect.name != "sqlite":
        op.create_foreign_key(
            "fk_user_sessions_replaced_by_id",
            "user_sessions",
            "user_sessions",
            ["replaced_by_id"],
            ["id"],
        )

    with op.batch_alter_table("user_sessions") as batch:
        batch.alter_column("family_id", existing_type=sa.String(length=36), nullable=False)
        batch.alter_column("created_at", existing_type=sa.DateTime(timezone=True), nullable=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "user_sessions" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("user_sessions")}
    indexes = {index["name"] for index in inspector.get_indexes("user_sessions")}
    if "ix_user_sessions_family_id" in indexes:
        op.drop_index("ix_user_sessions_family_id", table_name="user_sessions")
    if "ix_user_sessions_refresh_token" in indexes:
        op.drop_index("ix_user_sessions_refresh_token", table_name="user_sessions")
    with op.batch_alter_table("user_sessions") as batch:
        for name in ["replaced_by_id", "revoked_at", "rotated_at", "created_at", "family_id"]:
            if name in columns:
                batch.drop_column(name)
    inspector = inspect(bind)
    for table_name in ("oidc_login_tickets", "user_oidc_accounts"):
        if table_name in inspector.get_table_names():
            op.drop_table(table_name)
