"""totp_secret_encryption: widen user_totp.secret for Fernet ciphertext

The TOTP shared secret is now encrypted at rest with Fernet
(``docs/SECURITY_PRIVACY.md`` §8). Fernet ciphertext is longer than the raw
base32 secret, so the ``user_totp.secret`` column is widened from ``String(64)``
to ``String(255)``. No data transform is needed at the schema level: existing dev
rows (raw base32) remain valid and the application re-encrypts them
opportunistically on next verify (legacy-tolerant decrypt path).

The SQLite unit-test path builds the schema from ORM metadata and never runs this
migration; on SQLite ``ALTER COLUMN`` is wrapped in a batch operation for safety.

Revision ID: 0010_totp_secret_encryption
Revises: 0009_notifications
Create Date: 2026-06-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_totp_secret_encryption"
down_revision: str | None = "0009_notifications"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.alter_column(
            "user_totp",
            "secret",
            existing_type=sa.String(64),
            type_=sa.String(255),
            existing_nullable=False,
        )
    else:
        with op.batch_alter_table("user_totp") as batch:
            batch.alter_column(
                "secret",
                existing_type=sa.String(64),
                type_=sa.String(255),
                existing_nullable=False,
            )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.alter_column(
            "user_totp",
            "secret",
            existing_type=sa.String(255),
            type_=sa.String(64),
            existing_nullable=False,
        )
    else:
        with op.batch_alter_table("user_totp") as batch:
            batch.alter_column(
                "secret",
                existing_type=sa.String(255),
                type_=sa.String(64),
                existing_nullable=False,
            )
