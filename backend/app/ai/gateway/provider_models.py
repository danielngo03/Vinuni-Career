"""ORM models for admin-managed AI provider configuration.

Complements ``ai_settings`` (alias selection + toggles) with:

- ``AiProviderConfig``: a named OpenAI-compatible endpoint plus optional
  Fernet-encrypted API key. Env keys remain a deploy-time fallback.
- ``AiModelAlias``: a logical alias (e.g. ``chat_cheap``) that the gateway
  resolves to a (provider, model_id) pair at runtime.

Built-in providers/aliases are seeded via ``provider_registry.ensure_defaults``
and are marked ``is_builtin=True`` to prevent accidental deletion. University
admins can add custom providers and custom aliases that route through them.

API key convention:
  Admin-managed keys are stored in ``api_key_ciphertext`` only. Responses expose
  presence via ``has_api_key`` and never return plaintext.
  ``AI_PROVIDER_{UPPERCASE_NAME}_API_KEY`` env var overrides the provider.
  Fallback for the built-in "openrouter" provider: ``OPENROUTER_API_KEY``.
  Fallback for the built-in "openai" provider: ``OPENAI_API_KEY``.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.models import Base, JsonType


class AiProviderConfig(Base):
    """A named AI provider endpoint.

    API keys are encrypted at rest. Provider type governs how the gateway
    constructs requests; ``ollama`` is treated as no-key local infrastructure.
    """

    __tablename__ = "ai_provider_configs"

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    name: Mapped[str] = mapped_column(String(60), nullable=False, unique=True)
    provider_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default="openai_compatible"
    )
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    api_key_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Safe UI hint (last 4 chars) + fingerprint of the encryption key generation
    # that wrote the ciphertext. Neither reveals key material; ``key_version``
    # lets the rotation routine find rows still encrypted under an older key.
    api_key_last4: Mapped[str | None] = mapped_column(String(8), nullable=True)
    key_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Last health-probe outcome (admin "Test connection" action); status only.
    last_health_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    last_health_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    aliases: Mapped[list[AiModelAlias]] = relationship(
        "AiModelAlias", back_populates="provider", lazy="selectin"
    )


class AiModelAlias(Base):
    """Maps a logical alias name to a (provider, model_id) pair.

    Alias names are the only values that travel outside the AI layer
    (stored in ``ai_settings.chat_model_alias`` etc.). The concrete
    ``model_id`` is resolved here and NEVER exposed to end users.
    """

    __tablename__ = "ai_model_aliases"
    __table_args__ = (UniqueConstraint("alias_name", name="uq_ai_model_aliases_alias_name"),)

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    alias_name: Mapped[str] = mapped_column(String(60), nullable=False, unique=True)
    model_id: Mapped[str] = mapped_column(String(200), nullable=False)
    provider_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ai_provider_configs.id"), nullable=False
    )
    task_families: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        doc="Comma-separated list e.g. 'chat,eval'. NULL = usable for any task.",
    )
    fallback_provider_names: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc=(
            "Comma-separated, ORDERED list of additional provider names to try, "
            "in order, if the primary provider's circuit is open or a call fails "
            "transiently (AI_PRODUCT_SPEC §5.2 fallback chain). NULL/empty = no "
            "fallback (chain length 1, today's behaviour). Each fallback hop "
            "reuses this alias's model_id against the fallback provider's "
            "base_url — admins must only chain providers that serve an "
            "equivalent model id."
        ),
    )
    # Rotation strategy across the ordered provider chain: 'priority' (default —
    # try hops in order, failover only) or 'round_robin' (spread calls across
    # healthy hops, still failing over to the rest). Both skip circuit-open hops.
    rotation_strategy: Mapped[str] = mapped_column(String(20), nullable=False, default="priority")
    # Richer ordered fallback: a JSON list of ``{"provider_name", "model_id"}``
    # so each hop can carry its OWN model id (providers rarely share model ids).
    # When present it supersedes ``fallback_provider_names`` for chain building.
    fallback_bindings: Mapped[list | None] = mapped_column(JsonType, nullable=True)
    # Last health-probe outcome (admin "Test" action); non-secret status only.
    last_health_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    last_health_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    provider: Mapped[AiProviderConfig] = relationship("AiProviderConfig", back_populates="aliases")
