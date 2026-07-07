"""Platform Admin ORM models.

Tables:
  feature_flag — generalised feature flag registry (superadmin-managed).
                 Additive; the existing hardcoded AI booleans in ai_settings
                 are NOT migrated here; they can be folded in later.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import Base


class FeatureFlag(Base):
    """A named feature toggle with optional staged-rollout support.

    ``rollout_percentage`` is an integer 0-100:
      - 0   → always disabled (unless ``enabled`` is False, which also → disabled)
      - 100 → always enabled for all subjects
      - 1-99 → deterministic per-subject bucketing via SHA-256 hash

    ``updated_by`` records the superadmin UUID who made the last change.
    """

    __tablename__ = "feature_flags"
    __table_args__ = (UniqueConstraint("key", name="uq_feature_flags_key"),)

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
        default=uuid.uuid4,
    )
    key: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false", default=False
    )
    rollout_percentage: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0", default=0
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True, default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
