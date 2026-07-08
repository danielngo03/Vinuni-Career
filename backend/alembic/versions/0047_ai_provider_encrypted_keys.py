"""Store encrypted AI provider API keys."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0047_ai_provider_encrypted_keys"
down_revision = "0046_cv_template_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ai_provider_configs",
        sa.Column("api_key_ciphertext", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("ai_provider_configs", "api_key_ciphertext")
