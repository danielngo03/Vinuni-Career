"""Notification template governance: track last editor.

Adds ``notification_templates.updated_by`` so admin CRUD
(``docs/NOTIFICATIONS_COMMUNICATIONS_SPEC.md`` §4,
``notifications.application.template_admin_service``) can audit who last
touched a draft in addition to ``created_by``. The table itself (key/channel/
locale/version/status/owner_scope/owner_org_id) already exists from
``0001_baseline`` and already supports multi-version rows via
``uq_notification_templates_identity``.

Revision ID: 0056_notification_template_governance
Revises: 0055_cv_canvas_photo
Create Date: 2026-07-04
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0056_notification_template_governance"
down_revision = "0055_cv_canvas_photo"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "notification_templates",
        sa.Column("updated_by", UUID(as_uuid=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("notification_templates", "updated_by")
