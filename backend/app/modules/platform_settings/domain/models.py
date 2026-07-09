"""``platform_settings`` ORM model — singleton platform appearance/font row."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import Base

PLATFORM_SCOPE = "platform"


class PlatformSettings(Base):
    """Admin-managed platform appearance settings (single ``'platform'`` row for V1)."""

    __tablename__ = "platform_settings"

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)

    scope: Mapped[str] = mapped_column(
        String(20), nullable=False, unique=True, default=PLATFORM_SCOPE
    )

    # Admin-set Google Fonts CSS URL. Must start with https://fonts.googleapis.com/
    # The frontend injects this as a <link rel="stylesheet"> override.
    google_font_url: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # CSS font-family name matching the URL above (e.g. "Inter", "Roboto").
    # Applied via CSS variable override so the whole app adopts the custom font.
    google_font_family: Mapped[str | None] = mapped_column(String(100), nullable=True)

    updated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
