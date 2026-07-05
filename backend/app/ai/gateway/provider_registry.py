"""AI provider registry: seed, resolve, and CRUD for multi-provider configuration.

Implements ADR-0011 §6 (multi-provider admin):
- Built-in providers are seeded on first run and marked ``is_builtin=True``.
- Admin can add custom providers (name + base_url) and custom aliases.
- The registry publishes a fresh ``EffectiveAiConfig`` snapshot into
  ``runtime_config`` whenever the provider list changes.
- API keys may be stored encrypted in DB for admin-managed providers. Env vars
  remain a deployment fallback: ``AI_PROVIDER_{UPPERCASE_NAME}_API_KEY`` plus
  legacy OPENROUTER_API_KEY / OPENAI_API_KEY fallbacks for built-ins.
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.ai.gateway.provider_key_crypto import (
    decrypt_provider_api_key,
    encrypt_provider_api_key,
)
from app.ai.gateway.provider_models import AiModelAlias, AiProviderConfig
from app.ai.gateway.provider_route_chains import normalize_fallback_payload, parse_fallback_names
from app.core.config import get_settings

logger = logging.getLogger("ai.provider_registry")

# ---------------------------------------------------------------------------
# Built-in defaults (seeded into DB on first run)
# ---------------------------------------------------------------------------

_DEFAULT_PROVIDERS: list[dict[str, Any]] = [
    {
        "name": "openrouter",
        "provider_type": "openai_compatible",
        "base_url": "https://openrouter.ai/api/v1",
        "description": "OpenRouter aggregator — access 100+ models via one key",
    },
    {
        "name": "openai",
        "provider_type": "openai_compatible",
        "base_url": "https://api.openai.com/v1",
        "description": "OpenAI direct — GPT-4o, GPT-4o-mini, text-embedding-3-*",
    },
    {
        "name": "ollama-local",
        "provider_type": "ollama",
        "base_url": "http://localhost:11434/v1",
        "description": "Local Ollama instance — no API key required",
    },
    {
        "name": "azure-openai",
        "provider_type": "azure_openai",
        "base_url": "",  # Admin must fill in the Azure endpoint
        "description": "Azure OpenAI Service — requires endpoint + encrypted API key",
    },
]

# alias_name → (provider_name, model_id, task_families, description)
_DEFAULT_ALIASES: list[dict[str, Any]] = [
    {
        "alias_name": "chat_cheap",
        "model_id": "deepseek/deepseek-chat",
        "provider_name": "openrouter",
        "task_families": "chat,eval",
        "description": "Ultra-cheap chat model via OpenRouter (~$0.00001/call)",
    },
    {
        "alias_name": "chat_free",
        "model_id": "deepseek/deepseek-chat",
        "provider_name": "openrouter",
        "task_families": "chat",
        "description": "Dev/smoke-test alias (same model as chat_cheap)",
    },
    {
        "alias_name": "chat_mini",
        "model_id": "meta-llama/llama-3.1-8b-instruct",
        "provider_name": "openrouter",
        "task_families": "chat",
        "description": "Lightweight 8B model for low-cost completions",
    },
    {
        "alias_name": "reasoning_cheap",
        "model_id": "deepseek/deepseek-r1",
        "provider_name": "openrouter",
        "task_families": "reasoning",
        "description": "DeepSeek-R1 reasoning model for structured analysis",
    },
    {
        "alias_name": "reasoning_local",
        "model_id": "llama3.2",
        "provider_name": "ollama-local",
        "task_families": "reasoning",
        "description": "Local reasoning fallback through Ollama-compatible chat",
    },
    {
        "alias_name": "eval_cheap",
        "model_id": "deepseek/deepseek-chat",
        "provider_name": "openrouter",
        "task_families": "eval",
        "description": "Alias for offline CI evaluation harness",
    },
    {
        "alias_name": "eval_local",
        "model_id": "llama3.2",
        "provider_name": "ollama-local",
        "task_families": "eval",
        "description": "Local evaluation assistant through Ollama-compatible chat",
    },
    {
        "alias_name": "embedding_cheap",
        "model_id": "text-embedding-3-small",
        "provider_name": "openrouter",
        "task_families": "embedding",
        "description": "OpenAI text-embedding-3-small via OpenRouter",
    },
    {
        "alias_name": "rerank_cheap",
        "model_id": "deepseek/deepseek-chat",
        "provider_name": "openrouter",
        "task_families": "rerank",
        "description": "Low-cost listwise reranker for job/search candidates",
    },
    # OpenAI-direct aliases (active only when OPENAI_API_KEY is set)
    {
        "alias_name": "chat_openai_fast",
        "model_id": "gpt-4o-mini",
        "provider_name": "openai",
        "task_families": "chat",
        "description": "GPT-4o-mini direct from OpenAI",
    },
    {
        "alias_name": "chat_openai_best",
        "model_id": "gpt-4o",
        "provider_name": "openai",
        "task_families": "chat",
        "description": "GPT-4o direct from OpenAI — highest quality",
    },
    {
        "alias_name": "embedding_openai",
        "model_id": "text-embedding-3-small",
        "provider_name": "openai",
        "task_families": "embedding",
        "description": "OpenAI text-embedding-3-small direct",
    },
    {
        "alias_name": "embedding_local",
        "model_id": "nomic-embed-text",
        "provider_name": "ollama-local",
        "task_families": "embedding",
        "description": "Local embedding model through Ollama-compatible embeddings",
    },
    {
        "alias_name": "rerank_openai_fast",
        "model_id": "gpt-4o-mini",
        "provider_name": "openai",
        "task_families": "rerank",
        "description": "GPT-4o-mini listwise reranker",
    },
    # Local Ollama aliases (active only when Ollama is running)
    {
        "alias_name": "chat_local",
        "model_id": "llama3.2",
        "provider_name": "ollama-local",
        "task_families": "chat",
        "description": "Local Llama 3.2 via Ollama — free, private, no API key",
    },
    {
        "alias_name": "chat_local_large",
        "model_id": "llama3.1:70b",
        "provider_name": "ollama-local",
        "task_families": "chat",
        "description": "Local Llama 3.1 70B via Ollama — high quality, slow",
    },
    {
        "alias_name": "rerank_local",
        "model_id": "llama3.2",
        "provider_name": "ollama-local",
        "task_families": "rerank",
        "description": "Local listwise reranking through Ollama-compatible chat",
    },
]


# ---------------------------------------------------------------------------
# Key resolution
# ---------------------------------------------------------------------------

def get_api_key_for_provider(provider_name: str) -> str:
    """Return the API key for a named provider from env fallback only.

    Convention: ``AI_PROVIDER_{UPPERCASE_NAME}_API_KEY``
    Legacy fallbacks for built-in names.
    """
    env_var = f"AI_PROVIDER_{provider_name.upper().replace('-', '_').replace(' ', '_')}_API_KEY"
    key = os.environ.get(env_var, "")
    if key in {"", "replace-with-local-key", "replace-with-local-secret"}:
        # Legacy fallback for built-in names
        if provider_name == "openrouter":
            key = os.environ.get("OPENROUTER_API_KEY", "") or get_settings().openrouter_api_key
        elif provider_name == "openai":
            key = os.environ.get("OPENAI_API_KEY", "") or get_settings().openai_api_key
        elif provider_name in ("azure-openai", "azure_openai"):
            key = (
                os.environ.get("AZURE_OPENAI_API_KEY", "")
                or get_settings().azure_openai_api_key
            )
    return key


def has_api_key(provider_name: str) -> bool:
    """True when a non-empty API key is available for the provider."""
    if provider_name in {"ollama-local", "ollama"}:
        return True
    cipher = runtime_ciphertexts().get(provider_name)
    if cipher and decrypt_provider_api_key(cipher) not in {
        "",
        "replace-with-local-key",
        "replace-with-local-secret",
    }:
        return True
    key = get_api_key_for_provider(provider_name)
    placeholder = {"", "replace-with-local-key", "replace-with-local-secret"}
    return key not in placeholder


def runtime_ciphertexts() -> dict[str, str]:
    """Return encrypted provider keys from the current runtime snapshot."""

    from app.ai.gateway import runtime_config

    return runtime_config.current().provider_key_ciphertexts


# ---------------------------------------------------------------------------
# Seeding
# ---------------------------------------------------------------------------

async def ensure_defaults(db: AsyncSession) -> None:
    """Upsert built-in providers and aliases if they don't exist yet.

    Safe to call on every startup — idempotent. Only inserts rows that are
    missing; never overwrites admin-edited rows.
    """
    # Upsert providers
    for p in _DEFAULT_PROVIDERS:
        existing = (
            await db.execute(
                select(AiProviderConfig).where(AiProviderConfig.name == p["name"])
            )
        ).scalar_one_or_none()
        if existing is None:
            row = AiProviderConfig(
                id=uuid.uuid4(),
                name=p["name"],
                provider_type=p["provider_type"],
                base_url=p["base_url"],
                description=p.get("description"),
                is_active=True,
                is_builtin=True,
            )
            db.add(row)
    await db.flush()

    # Build provider name → id map
    provider_rows = (
        await db.execute(select(AiProviderConfig))
    ).scalars().all()
    provider_map = {r.name: r.id for r in provider_rows}

    # Upsert aliases
    for a in _DEFAULT_ALIASES:
        pname = a["provider_name"]
        if pname not in provider_map:
            logger.warning(
                "provider_not_found_for_alias",
                extra={"alias": a["alias_name"], "provider": pname},
            )
            continue
        existing_alias = (
            await db.execute(
                select(AiModelAlias).where(AiModelAlias.alias_name == a["alias_name"])
            )
        ).scalar_one_or_none()
        if existing_alias is None:
            alias_row = AiModelAlias(
                id=uuid.uuid4(),
                alias_name=a["alias_name"],
                model_id=a["model_id"],
                provider_id=provider_map[pname],
                task_families=a.get("task_families"),
                fallback_provider_names=a.get("fallback_provider_names"),
                description=a.get("description"),
                is_active=True,
                is_builtin=True,
            )
            db.add(alias_row)
    await db.flush()

    # Seed the six function-slot bindings from concrete config models. Admin/.env
    # is authoritative for which real model backs each slot; the slot name is the
    # leak-safe handle stored on the ai_settings row. Bound to the default
    # provider (one shared key); admin can rebind a slot to another provider.
    s = get_settings()
    default_slots: list[tuple[str, str, str, str]] = [
        ("chat_default", s.ai_chat_model, "chat", "Default chat model (admin-managed)"),
        ("reasoning_default", s.ai_reasoning_model, "reasoning", "Default reasoning model"),
        ("embedding_default", s.ai_embedding_model, "embedding", "Default embedding model"),
        ("rerank_default", s.ai_rerank_model, "rerank", "Default rerank model"),
        ("eval_default", s.ai_eval_model, "eval", "Default eval model"),
        ("vision_default", s.ai_vision_model, "vision", "Default vision model"),
    ]
    default_provider_id = provider_map.get(s.ai_default_provider)
    if default_provider_id is not None:
        for slot_name, model_id, family, desc in default_slots:
            existing_slot = (
                await db.execute(
                    select(AiModelAlias).where(AiModelAlias.alias_name == slot_name)
                )
            ).scalar_one_or_none()
            if existing_slot is None:
                db.add(
                    AiModelAlias(
                        id=uuid.uuid4(),
                        alias_name=slot_name,
                        model_id=model_id,
                        provider_id=default_provider_id,
                        task_families=family,
                        description=desc,
                        is_active=True,
                        is_builtin=True,
                    )
                )
        await db.flush()


# ---------------------------------------------------------------------------
# Resolution — used by the factory to build provider routes
# ---------------------------------------------------------------------------

async def load_active_routes(db: AsyncSession) -> dict[str, tuple[str, str, str]]:
    """Return all active alias routes for the runtime snapshot.

    Returns: {alias_name: (provider_name, base_url, model_id)}
    """
    rows = (
        await db.execute(
            select(
                AiModelAlias.alias_name,
                AiModelAlias.model_id,
                AiProviderConfig.name,
                AiProviderConfig.base_url,
            )
            .join(AiProviderConfig, AiModelAlias.provider_id == AiProviderConfig.id)
            .where(
                AiModelAlias.is_active.is_(True),
                AiProviderConfig.is_active.is_(True),
            )
        )
    ).all()

    routes: dict[str, tuple[str, str, str]] = {}
    for alias_name, model_id, provider_name, base_url in rows:
        routes[alias_name] = (provider_name, base_url, model_id)
    return routes


async def load_active_key_ciphertexts(db: AsyncSession) -> dict[str, str]:
    """Return active provider encrypted keys for the runtime snapshot."""

    rows = (
        await db.execute(
            select(AiProviderConfig.name, AiProviderConfig.api_key_ciphertext).where(
                AiProviderConfig.is_active.is_(True),
                AiProviderConfig.api_key_ciphertext.is_not(None),
            )
        )
    ).all()
    return {name: cipher for name, cipher in rows if cipher}


async def list_providers(db: AsyncSession) -> list[dict]:
    """List all providers for the admin API response."""
    rows = (
        await db.execute(select(AiProviderConfig).order_by(AiProviderConfig.name))
    ).scalars().all()
    return [_serialize_provider(r) for r in rows]


async def list_aliases(db: AsyncSession) -> list[dict]:
    """List all model aliases for the admin API response."""
    rows = (
        await db.execute(
            select(AiModelAlias)
            .options(selectinload(AiModelAlias.provider))
            .order_by(AiModelAlias.alias_name)
        )
    ).scalars().all()
    return [_serialize_alias(r) for r in rows]


async def create_provider(
    db: AsyncSession,
    *,
    payload: dict,
    created_by: uuid.UUID | None = None,
) -> dict:
    """Create a new custom provider config (admin action)."""
    name = (payload.get("name") or "").strip().lower().replace(" ", "-")
    base_url = (payload.get("base_url") or "").strip()
    if not name or not base_url:
        raise ValueError("name and base_url are required")
    api_key = (payload.get("api_key") or "").strip()
    row = AiProviderConfig(
        id=uuid.uuid4(),
        name=name,
        provider_type=payload.get("provider_type") or "openai_compatible",
        base_url=base_url,
        api_key_ciphertext=encrypt_provider_api_key(api_key) if api_key else None,
        description=payload.get("description"),
        is_active=bool(payload.get("is_active", True)),
        is_builtin=False,
        created_by=created_by,
    )
    db.add(row)
    await db.flush()
    await db.refresh(row)
    return _serialize_provider(row)


async def update_provider(db: AsyncSession, provider_id: uuid.UUID, *, payload: dict) -> dict:
    """Update a provider config (admin action). Built-in base_url/name can still be changed."""
    row = (
        await db.execute(select(AiProviderConfig).where(AiProviderConfig.id == provider_id))
    ).scalar_one_or_none()
    if row is None:
        raise LookupError("provider_not_found")
    if "base_url" in payload and payload["base_url"]:
        row.base_url = payload["base_url"].strip()
    if "description" in payload:
        row.description = payload["description"]
    if "is_active" in payload:
        row.is_active = bool(payload["is_active"])
    if "provider_type" in payload and payload["provider_type"]:
        row.provider_type = payload["provider_type"]
    if payload.get("clear_api_key"):
        row.api_key_ciphertext = None
    elif "api_key" in payload:
        api_key = (payload.get("api_key") or "").strip()
        if api_key:
            row.api_key_ciphertext = encrypt_provider_api_key(api_key)
    await db.flush()
    await db.refresh(row)
    return _serialize_provider(row)


async def create_alias(
    db: AsyncSession,
    *,
    payload: dict,
    created_by: uuid.UUID | None = None,
) -> dict:
    """Create a new model alias (admin action)."""
    alias_name = (payload.get("alias_name") or "").strip().lower().replace(" ", "_")
    model_id = (payload.get("model_id") or "").strip()
    provider_id = payload.get("provider_id")
    if not alias_name or not model_id or not provider_id:
        raise ValueError("alias_name, model_id, and provider_id are required")
    provider_uuid = uuid.UUID(str(provider_id))
    provider = (
        await db.execute(select(AiProviderConfig).where(AiProviderConfig.id == provider_uuid))
    ).scalar_one_or_none()
    if provider is None:
        raise ValueError("provider_not_found")
    row = AiModelAlias(
        id=uuid.uuid4(),
        alias_name=alias_name,
        model_id=model_id,
        provider_id=provider_uuid,
        task_families=payload.get("task_families"),
        fallback_provider_names=normalize_fallback_payload(
            payload.get("fallback_provider_names")
        ),
        description=payload.get("description"),
        is_active=bool(payload.get("is_active", True)),
        is_builtin=False,
        created_by=created_by,
    )
    db.add(row)
    await db.flush()
    await db.refresh(row)
    return _serialize_alias(row, provider_name=provider.name)


async def update_alias(db: AsyncSession, alias_id: uuid.UUID, *, payload: dict) -> dict:
    """Update a model alias (admin action). Cannot change alias_name of built-in aliases."""
    row = (
        await db.execute(select(AiModelAlias).where(AiModelAlias.id == alias_id))
    ).scalar_one_or_none()
    if row is None:
        raise LookupError("alias_not_found")
    if "model_id" in payload and payload["model_id"]:
        row.model_id = payload["model_id"].strip()
    if "provider_id" in payload and payload["provider_id"]:
        provider_uuid = uuid.UUID(str(payload["provider_id"]))
        provider = (
            await db.execute(select(AiProviderConfig).where(AiProviderConfig.id == provider_uuid))
        ).scalar_one_or_none()
        if provider is None:
            raise ValueError("provider_not_found")
        row.provider_id = provider_uuid
    if "task_families" in payload:
        row.task_families = payload["task_families"]
    if "fallback_provider_names" in payload:
        row.fallback_provider_names = normalize_fallback_payload(
            payload["fallback_provider_names"]
        )
    if "description" in payload:
        row.description = payload["description"]
    if "is_active" in payload:
        row.is_active = bool(payload["is_active"])
    await db.flush()
    await db.refresh(row)
    provider_name = (
        await db.execute(
            select(AiProviderConfig.name).where(AiProviderConfig.id == row.provider_id)
        )
    ).scalar_one_or_none()
    return _serialize_alias(row, provider_name=provider_name)


# ---------------------------------------------------------------------------
# Serializers (safe — no API keys, no model_id exposed externally)
# ---------------------------------------------------------------------------

def _serialize_provider(r: AiProviderConfig) -> dict:
    has_db_key = bool(
        r.api_key_ciphertext and decrypt_provider_api_key(r.api_key_ciphertext)
    )
    return {
        "id": str(r.id),
        "name": r.name,
        "provider_type": r.provider_type,
        "base_url": r.base_url,
        "description": r.description,
        "is_active": r.is_active,
        "is_builtin": r.is_builtin,
        "has_api_key": has_db_key or has_api_key(r.name),
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }


def _serialize_alias(r: AiModelAlias, *, provider_name: str | None = None) -> dict:
    resolved_provider_name = provider_name
    if resolved_provider_name is None and r.provider is not None:
        resolved_provider_name = r.provider.name
    return {
        "id": str(r.id),
        "alias_name": r.alias_name,
        "provider_id": str(r.provider_id),
        "provider_name": resolved_provider_name,
        "task_families": r.task_families,
        "fallback_provider_names": parse_fallback_names(r.fallback_provider_names),
        "description": r.description,
        "is_active": r.is_active,
        "is_builtin": r.is_builtin,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        # model_id intentionally excluded — never expose to admin UI
    }
