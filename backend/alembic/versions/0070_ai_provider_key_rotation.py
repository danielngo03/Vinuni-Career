"""AI provider key rotation metadata: ai_provider_configs.api_key_last4 + key_version.

Encryption hardening (design spec 2026-07-06): admin AI provider keys are now
encrypted with a rotatable MultiFernet key list. Two non-secret columns support
this without ever storing key material:

- ``api_key_last4 VARCHAR(8) NULL`` — last 4 chars of the plaintext key, for a
  safe UI hint (``sk-…4f2a``); the plaintext itself is never stored/returned.
- ``key_version VARCHAR(32) NULL`` — short fingerprint of the encryption key
  generation that wrote the ciphertext, so the rotation routine can find rows
  still encrypted under a retired key.

Both are nullable and backfilled lazily (next key write stamps them), so no data
migration is required. Downgrade drops both columns.

Revision ID: 0070_ai_provider_key_rotation
Revises: 0069_identity_only_student_profile
Create Date: 2026-07-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0070_ai_provider_key_rotation"
down_revision: str | None = "0069_identity_only_student_profile"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ai_provider_configs",
        sa.Column("api_key_last4", sa.String(length=8), nullable=True),
    )
    op.add_column(
        "ai_provider_configs",
        sa.Column("key_version", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("ai_provider_configs", "key_version")
    op.drop_column("ai_provider_configs", "api_key_last4")
