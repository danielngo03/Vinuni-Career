"""CV Studio visual canvas: add cv_profiles.canvas_json (block/photo layout).

Backs the ``PATCH /api/v1/cvs/{cv_id}/canvas`` and
``PATCH /api/v1/cvs/{cv_id}/photo`` contracts (``docs/CV_STUDIO_SPEC.md``
"Visual Canvas Editor Contract"). ``canvas_json`` is presentation/layout metadata
only (block order/position/visibility overrides + the profile-photo binding); CV
facts remain in ``cv_sections.content_json``.

Revision ID: 0055_cv_canvas_photo
Revises: 0054_otp_and_onboarding
Create Date: 2026-07-04
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0055_cv_canvas_photo"
down_revision = "0054_otp_and_onboarding"
branch_labels = None
depends_on = None

_JSON = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    op.add_column(
        "cv_profiles",
        sa.Column("canvas_json", _JSON, nullable=False, server_default=sa.text("'{}'")),
    )


def downgrade() -> None:
    op.drop_column("cv_profiles", "canvas_json")
