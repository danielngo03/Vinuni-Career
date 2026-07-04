"""Identity-core ORM models: users, identities, and account preferences.

Schema follows ``docs/DATA_MODEL.md`` §4 (``users``, ``identities``) and §33/§34
(``user_preferences``, ``notification_preferences``). Types use the shared
cross-database variants so the same models run on PostgreSQL (runtime) and SQLite
(narrow unit tests).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import Base, JsonType


class User(Base):
    """A login account. May hold multiple identities (personas)."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_superadmin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    preferred_language: Mapped[str] = mapped_column(String(5), nullable=False, default="vi")
    timezone: Mapped[str] = mapped_column(
        String(50), nullable=False, default="Asia/Ho_Chi_Minh"
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    login_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    @property
    def is_email_verified(self) -> bool:
        return self.email_verified_at is not None


class Identity(Base):
    """A persona a user can act as (student / partner_member / staff / alumni)."""

    __tablename__ = "identities"
    __table_args__ = (
        UniqueConstraint("user_id", "persona", "org_id", name="uq_identities_identity"),
    )

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    persona: Mapped[str] = mapped_column(String(30), nullable=False)
    org_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class UserPreference(Base):
    """Per-user account preferences (locale/timezone/theme/quiet-hours)."""

    __tablename__ = "user_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    locale: Mapped[str] = mapped_column(String(5), nullable=False, default="vi")
    timezone: Mapped[str] = mapped_column(
        String(100), nullable=False, default="Asia/Ho_Chi_Minh"
    )
    theme: Mapped[str] = mapped_column(String(20), nullable=False, default="system")
    quiet_hours: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)
    notification_settings: Mapped[dict] = mapped_column(
        JsonType, nullable=False, default=dict
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class NotificationPreference(Base):
    """Per-user, per-category notification channel preferences."""

    __tablename__ = "notification_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    category: Mapped[str] = mapped_column(String(100), primary_key=True)
    in_app_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    email_setting: Mapped[str] = mapped_column(
        String(20), nullable=False, default="immediate"
    )  # off | immediate | daily | weekly | mandatory
    push_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
