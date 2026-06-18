from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.database.models.base import TimestampMixin, now_utc, uuid_str
from app.platform.database.session import Base


class SystemWebhook(Base, TimestampMixin):
    __tablename__ = "system_webhooks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    target_url: Mapped[str] = mapped_column(Text, nullable=False)
    secret_key: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)





class FeatureFlag(Base, TimestampMixin):
    __tablename__ = "feature_flags"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    flag_key: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_enabled_global: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled_for_orgs: Mapped[list] = mapped_column(JSON, default=list)


class SystemConfig(Base):
    __tablename__ = "system_configs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    config_key: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    config_value: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Translation(Base):
    __tablename__ = "translations"
    __table_args__ = (
        UniqueConstraint(
            "entity_type",
            "entity_id",
            "language_code",
            name="uq_translation_entity_lang",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    entity_type: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    language_code: Mapped[str] = mapped_column(String(12), nullable=False)
    translated_content: Mapped[dict] = mapped_column(JSON, default=dict)





class LegalDocument(Base):
    __tablename__ = "legal_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    document_type: Mapped[str] = mapped_column(String(120), nullable=False)
    version: Mapped[str] = mapped_column(String(80), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class UserConsent(Base):
    __tablename__ = "user_consents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("legal_documents.id"), index=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
