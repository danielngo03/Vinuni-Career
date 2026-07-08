"""Request schemas for the admin AI-settings surface (ADR-0011 §6).

Inputs accept alias NAMES + flags + budget + toggles. Provider CRUD accepts API
keys only on create/update; keys are encrypted immediately and never returned.
Alias allowlist + rollout vocabulary + budget range are enforced in the service
layer so the error envelope and audit stay consistent.
"""

from __future__ import annotations

import re
import uuid
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ProviderType = Literal["openai_compatible", "ollama", "azure_openai"]

_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,58}[a-z0-9]$")
_ALIAS_RE = re.compile(r"^[a-z][a-z0-9_]{2,59}$")
_MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{1,199}$")


def _normalize_provider_name(value: str) -> str:
    name = value.strip().lower().replace(" ", "-")
    if not _NAME_RE.fullmatch(name):
        raise ValueError("provider name must be a slug")
    return name


def _normalize_alias(value: str) -> str:
    alias = value.strip().lower().replace(" ", "_")
    if not _ALIAS_RE.fullmatch(alias):
        raise ValueError("alias must use lowercase letters, numbers, and underscores")
    return alias


def _clean_url(value: str) -> str:
    url = value.strip().rstrip("/")
    if not (url.startswith("https://") or url.startswith("http://")):
        raise ValueError("base_url must start with http:// or https://")
    return url


def _clean_model_id(value: str) -> str:
    model_id = value.strip()
    if not _MODEL_RE.fullmatch(model_id):
        raise ValueError("model_id contains unsupported characters")
    return model_id


class AiSettingsUpdateRequest(BaseModel):
    """Partial update — only provided fields change (PATCH semantics)."""

    model_config = ConfigDict(extra="forbid")

    chat_model_alias: str | None = None
    reasoning_model_alias: str | None = None
    embedding_model_alias: str | None = None
    rerank_model_alias: str | None = None
    eval_model_alias: str | None = None
    cv_llm_structuring_enabled: bool | None = None
    job_fit_ai_explanation_enabled: bool | None = None
    real_calls_enabled: bool | None = None
    rollout_state: str | None = None
    daily_budget_usd: Decimal | None = Field(default=None, ge=Decimal("0"))
    per_org_daily_budget_usd: Decimal | None = Field(default=None, ge=Decimal("0"))
    clear_per_org_budget: bool | None = None
    notes: str | None = Field(default=None, max_length=2000)


class AiSettingsDisableRequest(BaseModel):
    """Kill-switch payload (optional rationale captured in the audit + notes)."""

    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=2000)


class AiProviderCreateRequest(BaseModel):
    """Create an admin-managed provider endpoint.

    ``api_key`` is write-only: backend encrypts it at rest and responses expose
    only ``has_api_key``.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=3, max_length=60)
    provider_type: ProviderType = "openai_compatible"
    base_url: str = Field(min_length=8, max_length=500)
    api_key: str | None = Field(default=None, max_length=10000)
    description: str | None = Field(default=None, max_length=1000)
    is_active: bool = True

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return _normalize_provider_name(value)

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        return _clean_url(value)


class AiProviderUpdateRequest(BaseModel):
    """Patch a provider endpoint without allowing unknown raw fields."""

    model_config = ConfigDict(extra="forbid")

    provider_type: ProviderType | None = None
    base_url: str | None = Field(default=None, min_length=8, max_length=500)
    api_key: str | None = Field(default=None, max_length=10000)
    clear_api_key: bool | None = None
    description: str | None = Field(default=None, max_length=1000)
    is_active: bool | None = None

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str | None) -> str | None:
        return _clean_url(value) if value is not None else None


class AiModelAliasCreateRequest(BaseModel):
    """Create a logical model alias for task-family routing."""

    model_config = ConfigDict(extra="forbid")

    alias_name: str = Field(min_length=3, max_length=60)
    model_id: str = Field(min_length=2, max_length=200)
    provider_id: uuid.UUID
    task_families: str | None = Field(
        default=None,
        max_length=200,
        description="Comma-separated task families, e.g. chat,eval.",
    )
    description: str | None = Field(default=None, max_length=1000)
    is_active: bool = True

    @field_validator("alias_name")
    @classmethod
    def validate_alias_name(cls, value: str) -> str:
        return _normalize_alias(value)

    @field_validator("model_id")
    @classmethod
    def validate_model_id(cls, value: str) -> str:
        return _clean_model_id(value)

    @field_validator("task_families")
    @classmethod
    def validate_task_families(cls, value: str | None) -> str | None:
        return _normalize_task_families(value)


class AiModelAliasUpdateRequest(BaseModel):
    """Patch a model alias; alias names remain stable once created."""

    model_config = ConfigDict(extra="forbid")

    model_id: str | None = Field(default=None, min_length=2, max_length=200)
    provider_id: uuid.UUID | None = None
    task_families: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    is_active: bool | None = None

    @field_validator("model_id")
    @classmethod
    def validate_model_id(cls, value: str | None) -> str | None:
        return _clean_model_id(value) if value is not None else None

    @field_validator("task_families")
    @classmethod
    def validate_task_families(cls, value: str | None) -> str | None:
        return _normalize_task_families(value)


def _normalize_task_families(value: str | None) -> str | None:
    if value is None:
        return None
    families = [item.strip().lower() for item in value.split(",") if item.strip()]
    allowed = {"chat", "reasoning", "embedding", "rerank", "eval"}
    unknown = [item for item in families if item not in allowed]
    if unknown:
        raise ValueError("unsupported task family")
    return ",".join(dict.fromkeys(families)) or None
