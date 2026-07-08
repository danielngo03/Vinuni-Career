"""Masked presentation of ``ai_settings`` (ADR-0011 §3 — SECRECY non-negotiable).

Exposes alias NAMES + feature flags + budget + DERIVED status only. NEVER the raw
key, base URL, concrete provider/model id, prompt, latency, or token counts. This
layer never echoes env or DB secrets — it surfaces only the boolean
``key_configured`` and the tri-state ``real_calls`` so an admin understands *why*
AI is off without seeing the provider/model/key.
"""

from __future__ import annotations

from app.ai.gateway import runtime_config
from app.core.config import get_settings
from app.modules.ai_settings.application import resolver
from app.modules.ai_settings.domain import aliases
from app.modules.ai_settings.domain.models import AiSettings

# Derived real-calls states.
REAL_CALLS_OFFLINE = "offline"
REAL_CALLS_AVAILABLE = "available"
REAL_CALLS_ENABLED = "enabled"


def _real_calls_status(row: AiSettings) -> tuple[bool, str]:
    """Return ``(key_configured, real_calls)`` derived status — no secret echoed.

    - ``offline``   = env gate off OR no key (env-blocked; admin cannot override).
    - ``available`` = env+key OK but the DB toggle/rollout keeps real calls off.
    - ``enabled``   = real calls are fully active (post-precedence).
    """

    settings = get_settings()
    env_real = bool(settings.ai_real_calls_enabled)
    active = runtime_config.current()
    routes = active.provider_routes
    provider_key_ciphertexts = active.provider_key_ciphertexts
    cfg = resolver.build_effective_config(
        row,
        provider_routes=routes,
        provider_key_ciphertexts=provider_key_ciphertexts,
    )
    selected = (
        row.chat_model_alias,
        row.reasoning_model_alias,
        row.embedding_model_alias,
        row.rerank_model_alias,
        row.eval_model_alias,
    )
    providers_ready = runtime_config.selected_aliases_accessible(
        selected, routes, provider_key_ciphertexts
    )
    real_calls_active = cfg.real_calls_active

    if not (env_real and providers_ready):
        status = REAL_CALLS_OFFLINE
    elif real_calls_active:
        status = REAL_CALLS_ENABLED
    else:
        status = REAL_CALLS_AVAILABLE
    return providers_ready, status


def settings_view(row: AiSettings) -> dict:
    """Masked, admin-facing view of the effective AI settings."""

    key_configured, real_calls = _real_calls_status(row)
    return {
        "scope": row.scope,
        "models": {
            "chat": row.chat_model_alias,
            "reasoning": row.reasoning_model_alias,
            "embedding": row.embedding_model_alias,
            "rerank": row.rerank_model_alias,
            "eval": row.eval_model_alias,
        },
        # Alias NAMES the admin may select per family (frontend selectors). No
        # provider/model id is ever included.
        "allowed_aliases": {
            family: list(values) for family, values in aliases.ALIAS_ALLOWLIST.items()
        },
        "feature_flags": {
            "cv_llm_structuring_enabled": row.cv_llm_structuring_enabled,
            "job_fit_ai_explanation_enabled": row.job_fit_ai_explanation_enabled,
        },
        "daily_budget_usd": f"{row.daily_budget_usd:.2f}",
        "per_org_daily_budget_usd": (
            f"{row.per_org_daily_budget_usd:.2f}"
            if row.per_org_daily_budget_usd is not None
            else None
        ),
        "rollout_state": row.rollout_state,
        "real_calls_enabled": row.real_calls_enabled,
        # DERIVED status only — never the key/base_url/provider/model.
        "key_configured": key_configured,
        "real_calls": real_calls,
        "version": row.version,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }
