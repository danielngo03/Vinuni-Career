"""Merge divergent alembic heads accumulated from parallel workstreams.

Four heads existed prior to this revision (``0055_moderation_workflow_
enhancements``, ``0055_salary_experience_modes``, ``0057_auth_throttle_oidc_
accounts``, ``0058_career_services_workspace``) — a pre-existing branching
issue from concurrent agent work, not caused by this migration. This is a
no-op merge revision (no schema changes) so ``alembic upgrade head`` /
``alembic downgrade`` resolve to a single linear chain again.

Revision ID: 0059_merge_heads
Revises: 0055_moderation_workflow_enhancements, 0055_salary_experience_modes,
         0057_auth_throttle_oidc_accounts, 0058_career_services_workspace
Create Date: 2026-07-04
"""

from __future__ import annotations

revision = "0059_merge_heads"
down_revision = (
    "0055_moderation_workflow_enhancements",
    "0055_salary_experience_modes",
    "0057_auth_throttle_oidc_accounts",
    "0058_career_services_workspace",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
