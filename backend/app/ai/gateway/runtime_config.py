"""Effective AI runtime configuration — the load-bearing resolution facade.

The gateway is sync, hot-path, and **ORM-free** (``docs/ARCHITECTURE.md`` §8): it
must not query a domain module's database. ``ai_settings`` therefore does NOT make
the gateway read the DB. Instead the ``ai_settings`` resolver **publishes** a
resolved, immutable snapshot into this pure in-memory holder, mirroring
``structuring.set_llm_structuring_adapter`` and ``advertising → sponsorship_facade``
(one-way: module → infra, never the reverse). See ADR-0011 §2.

Bootstrap vs published mode
---------------------------
The holder is **env-bootstrapped at import** so the gateway works correctly before
``ai_settings`` ever loads (offline, real calls off — byte-identical to today's
env-only behaviour). Until the resolver calls :func:`publish` (on app startup and
after every admin PATCH), :func:`current` reflects **live env** (``get_settings``);
once a snapshot is published, :func:`current` returns it. This keeps env-driven
tests behaviour-preserving while letting the admin surface drive the runtime once
the resolver has run.

SECRECY: API keys NEVER enter :class:`EffectiveAiConfig` in plaintext. The
snapshot carries alias names, booleans, budget, provider routing info, and
optional encrypted provider-key ciphertexts. ``factory.get_provider_for_alias``
decrypts only at request time (or falls back to env) and never serializes keys.

Multi-provider routing (ADR-0011 §6):
``provider_routes`` maps alias_name → (provider_name, base_url, model_id).
The base_url is stored here so the factory doesn't need a DB call per request.
Only encrypted key ciphertexts travel in the snapshot; plaintext is resolved by
the factory immediately before the upstream call.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from app.core.config import get_settings

# Keys that mean "no usable key configured" (mirrors ``gateway.factory``).
_PLACEHOLDER_KEYS = frozenset({"", "replace-with-local-key", "replace-with-local-secret"})

# Built-in provider routes (used when no DB snapshot is available).
# Format: alias_name → (provider_name, base_url, model_id)
_BUILTIN_ROUTES: dict[str, tuple[str, str, str]] = {
    # Function slots — concrete model is overridden from config at bootstrap
    # (``_bootstrap_from_env``); these literals are the pre-config fallback.
    "chat_default": ("openrouter", "https://openrouter.ai/api/v1", "deepseek/deepseek-v4-flash"),
    "reasoning_default": ("openrouter", "https://openrouter.ai/api/v1", "deepseek/deepseek-r1"),
    "embedding_default": ("openrouter", "https://openrouter.ai/api/v1", "text-embedding-3-small"),
    "rerank_default": ("openrouter", "https://openrouter.ai/api/v1", "deepseek/deepseek-v4-flash"),
    "eval_default": ("openrouter", "https://openrouter.ai/api/v1", "deepseek/deepseek-v4-flash"),
    "vision_default": ("openrouter", "https://openrouter.ai/api/v1", "google/gemini-2.5-flash"),
    # Mock Interview conversational brain + coaching report. Fast, Vietnamese-
    # capable, cheap — bound to ``ai_interview_model`` at bootstrap.
    "interview_default": ("openrouter", "https://openrouter.ai/api/v1", "google/gemini-2.5-flash"),
    # Legacy aliases — resolvable synonyms (removed from allowlist/UI).
    "chat_cheap": ("openrouter", "https://openrouter.ai/api/v1", "deepseek/deepseek-chat"),
    "chat_free": ("openrouter", "https://openrouter.ai/api/v1", "deepseek/deepseek-chat"),
    "chat_mini": ("openrouter", "https://openrouter.ai/api/v1", "meta-llama/llama-3.1-8b-instruct"),
    "reasoning_cheap": ("openrouter", "https://openrouter.ai/api/v1", "deepseek/deepseek-r1"),
    "eval_cheap": ("openrouter", "https://openrouter.ai/api/v1", "deepseek/deepseek-chat"),
    # Cheap multimodal model for CV image / scanned-PDF extraction (OCR+structuring
    # in one call). Gemini 2.5 Flash reads Vietnamese diacritics and multi-column
    # layouts well at a low price point (~$0.30/1M input). Swap to
    # google/gemini-2.5-flash-lite for ~5x cheaper output when accuracy allows.
    "vision_cheap": ("openrouter", "https://openrouter.ai/api/v1", "google/gemini-2.5-flash"),
    "embedding_cheap": ("openrouter", "https://openrouter.ai/api/v1", "text-embedding-3-small"),
    "rerank_cheap": ("openrouter", "https://openrouter.ai/api/v1", "deepseek/deepseek-chat"),
    "chat_openai_fast": ("openai", "https://api.openai.com/v1", "gpt-4o-mini"),
    "chat_openai_best": ("openai", "https://api.openai.com/v1", "gpt-4o"),
    "embedding_openai": ("openai", "https://api.openai.com/v1", "text-embedding-3-small"),
    "rerank_openai_fast": ("openai", "https://api.openai.com/v1", "gpt-4o-mini"),
    "chat_local": ("ollama-local", "http://localhost:11434/v1", "llama3.2"),
    "chat_local_large": ("ollama-local", "http://localhost:11434/v1", "llama3.1:70b"),
    "reasoning_local": ("ollama-local", "http://localhost:11434/v1", "llama3.2"),
    "eval_local": ("ollama-local", "http://localhost:11434/v1", "llama3.2"),
    "embedding_local": ("ollama-local", "http://localhost:11434/v1", "nomic-embed-text"),
    "rerank_local": ("ollama-local", "http://localhost:11434/v1", "llama3.2"),
}


@dataclass(frozen=True, slots=True)
class EffectiveAiConfig:
    """Immutable, resolved AI runtime snapshot consumed by the gateway.

    ``real_calls_active`` is FINAL (post-precedence): it already encodes the
    env-ceiling AND db-toggle AND key-presence decision made in the resolver, so
    consumers just read this boolean — they never re-derive policy.

    ``provider_routes``: alias_name → (provider_name, base_url, model_id).
    ``provider_route_chains``: alias_name → ORDERED list of
    ``(provider_name, base_url, model_id)`` fallback hops (AI_PRODUCT_SPEC
    §5.2). Index 0 is always the same route as ``provider_routes[alias_name]``.
    Aliases with no configured fallback still have a chain of length 1, so the
    factory can always use this map without a separate single-route branch.
    ``provider_key_ciphertexts``: provider_name → Fernet ciphertext. Plaintext
    keys are never stored in this snapshot.
    """

    real_calls_active: bool
    chat_model_alias: str
    reasoning_model_alias: str
    embedding_model_alias: str
    rerank_model_alias: str
    eval_model_alias: str
    cv_llm_structuring_enabled: bool
    job_fit_ai_explanation_enabled: bool
    daily_budget_usd: float
    provider_routes: dict[str, tuple[str, str, str]] = field(default_factory=dict)
    provider_route_chains: dict[str, list[tuple[str, str, str]]] = field(default_factory=dict)
    provider_key_ciphertexts: dict[str, str] = field(default_factory=dict)


def key_present(api_key: str) -> bool:
    """True when ``api_key`` is a real (non-placeholder) key. Never logs the key."""

    return api_key not in _PLACEHOLDER_KEYS


def provider_accessible(
    provider_name: str,
    provider_key_ciphertexts: dict[str, str] | None = None,
) -> bool:
    """True when a provider has credentials or is explicitly no-key local."""

    if provider_name in {"ollama-local", "ollama"}:
        return True
    cipher = (provider_key_ciphertexts or {}).get(provider_name)
    if cipher:
        from app.ai.gateway.provider_key_crypto import decrypt_provider_api_key

        if key_present(decrypt_provider_api_key(cipher)):
            return True
    env_var = f"AI_PROVIDER_{provider_name.upper().replace('-', '_').replace(' ', '_')}_API_KEY"
    key = os.environ.get(env_var, "")
    settings = get_settings()
    if not key_present(key):
        if provider_name == "openrouter":
            key = settings.openrouter_api_key
        elif provider_name == "openai":
            key = settings.openai_api_key
        elif provider_name in {"azure-openai", "azure_openai"}:
            key = settings.azure_openai_api_key
    return key_present(key)


def selected_aliases_accessible(
    aliases: tuple[str, ...],
    routes: dict[str, tuple[str, str, str]],
    provider_key_ciphertexts: dict[str, str] | None = None,
) -> bool:
    """True when every selected alias resolves to an accessible provider."""

    for alias in aliases:
        route = routes.get(alias)
        if route is None or not provider_accessible(route[0], provider_key_ciphertexts):
            return False
    return True


def _bootstrap_from_env() -> EffectiveAiConfig:
    """Build the snapshot purely from process env (no DB).

    Equivalent to today's env-only behaviour: real calls only when
    ``AI_REAL_CALLS_ENABLED`` is on AND a non-placeholder key is present;
    ``job_fit_ai_explanation_enabled`` defaults on (its only real gate today is
    ``real_calls_active``). The built-in provider routes are included so the
    factory works before DB-backed routes are published.
    """

    s = get_settings()
    # Override built-in openrouter base_url from env if configured
    routes = dict(_BUILTIN_ROUTES)
    openrouter_url = getattr(s, "openai_compatible_base_url", "https://openrouter.ai/api/v1")
    for alias, (pname, _, model) in list(routes.items()):
        if pname == "openrouter":
            routes[alias] = (pname, openrouter_url, model)
    # Bind the six function slots to their concrete config models. Admin/.env is
    # authoritative for which real model backs each slot; the slot name stays
    # leak-safe. The default provider serves all slots (one shared key); admins
    # can rebind a slot to another provider from the admin UI (DB routes win).
    _prov = s.ai_default_provider
    _base = (
        openrouter_url
        if _prov == "openrouter"
        else _BUILTIN_ROUTES.get("chat_cheap", (_prov, "", ""))[1]
    )
    routes["chat_default"] = (_prov, _base, s.ai_chat_model)
    routes["reasoning_default"] = (_prov, _base, s.ai_reasoning_model)
    routes["embedding_default"] = (_prov, _base, s.ai_embedding_model)
    routes["rerank_default"] = (_prov, _base, s.ai_rerank_model)
    routes["eval_default"] = (_prov, _base, s.ai_eval_model)
    routes["vision_default"] = (_prov, _base, s.ai_vision_model)
    routes["interview_default"] = (_prov, _base, s.ai_interview_model)
    selected = (
        s.ai_default_model_alias,
        s.ai_reasoning_model_alias,
        s.ai_embedding_model_alias,
        s.ai_rerank_model_alias,
        s.ai_eval_model_alias,
    )
    return EffectiveAiConfig(
        real_calls_active=bool(
            s.ai_real_calls_enabled and selected_aliases_accessible(selected, routes)
        ),
        chat_model_alias=s.ai_default_model_alias,
        reasoning_model_alias=s.ai_reasoning_model_alias,
        embedding_model_alias=s.ai_embedding_model_alias,
        rerank_model_alias=s.ai_rerank_model_alias,
        eval_model_alias=s.ai_eval_model_alias,
        cv_llm_structuring_enabled=bool(s.cv_llm_structuring_enabled),
        job_fit_ai_explanation_enabled=True,
        daily_budget_usd=float(s.ai_daily_cost_limit_usd),
        provider_routes=routes,
        # Bootstrap mode has no DB-configured fallback chains — every alias is
        # a single-hop chain, identical to today's behaviour.
        provider_route_chains={alias: [route] for alias, route in routes.items()},
        provider_key_ciphertexts={},
    )


# The published override; ``None`` means "bootstrap mode" -> read live env.
_override: EffectiveAiConfig | None = None


def current() -> EffectiveAiConfig:
    """Return the active snapshot — never ``None``.

    Bootstrap mode (no publish yet) reads live env; published mode returns the
    resolver's snapshot.
    """

    return _override if _override is not None else _bootstrap_from_env()


def publish(cfg: EffectiveAiConfig) -> None:
    """Install a resolved snapshot. The ONLY writer (called by the resolver)."""

    global _override
    _override = cfg


def reset_to_bootstrap() -> None:
    """Test seam: drop the published snapshot and fall back to live env.

    Not used in production code — the resolver only ever calls :func:`publish`.
    """

    global _override
    _override = None
