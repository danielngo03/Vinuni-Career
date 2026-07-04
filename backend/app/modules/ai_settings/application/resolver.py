"""Resolution facade: merge the DB row + env into the runtime snapshot (ADR-0011 §2).

This is the ONE place that owns the env-ceiling / DB-toggle precedence and the
one-way push into the gateway (``runtime_config.publish``). The gateway never
imports this module or the ``ai_settings`` ORM — dependency flows module → infra
only.

Precedence (env gate is the HARD CEILING; DB/provider keys determine readiness):

    env_real    = AI_REAL_CALLS_ENABLED            (env hard-gate)
    key_ready   = selected provider aliases have encrypted DB key, env key, or local no-key
    db_real     = row.real_calls_enabled AND row.rollout_state == 'enabled'
    real_calls_active = env_real AND key_ready AND db_real       # AND, never OR

→ No selected-provider key ⇒ ``real_calls_active`` is forced ``False`` regardless
of the DB row. Admin can manage encrypted provider keys, but still cannot bypass
the process-level ``AI_REAL_CALLS_ENABLED`` deploy gate.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.gateway import runtime_config
from app.ai.gateway.runtime_config import EffectiveAiConfig
from app.core.config import get_settings
from app.modules.ai_settings.domain.models import ROLLOUT_ENABLED, AiSettings
from app.modules.ai_settings.infrastructure import repository


def build_effective_config(
    row: AiSettings,
    provider_routes: dict[str, tuple[str, str, str]] | None = None,
    provider_key_ciphertexts: dict[str, str] | None = None,
    provider_route_chains: dict[str, list[tuple[str, str, str]]] | None = None,
) -> EffectiveAiConfig:
    """Apply the env-ceiling / DB-toggle precedence and build the snapshot.

    Reads env via ``get_settings`` for the hard ceiling (real-calls gate + key
    presence); plaintext API keys never enter the snapshot (ADR-0011 §3).

    ``provider_routes`` is the DB-loaded alias → (provider_name, base_url, model_id)
    map from the provider registry. When ``None``, the bootstrap routes from
    ``runtime_config._BUILTIN_ROUTES`` are used instead.

    ``provider_route_chains`` is the DB-loaded ORDERED fallback chain per alias
    (AI_PRODUCT_SPEC §5.2, ``provider_registry.load_active_route_chains``).
    Aliases absent from it default to a single-hop chain built from
    ``merged_routes``, so every alias always resolves to a chain.
    """

    settings = get_settings()
    env_real = bool(settings.ai_real_calls_enabled)
    db_real = bool(row.real_calls_enabled) and row.rollout_state == ROLLOUT_ENABLED

    # Merge DB routes into a copy of the bootstrap routes so built-in aliases
    # are always present even if DB hasn't been seeded yet.
    from app.ai.gateway.runtime_config import _BUILTIN_ROUTES
    merged_routes: dict[str, tuple[str, str, str]] = dict(_BUILTIN_ROUTES)
    if provider_routes:
        merged_routes.update(provider_routes)
    encrypted_keys = dict(provider_key_ciphertexts or {})
    # Every alias defaults to a single-hop chain from its merged route; DB
    # fallback chains (when present) override the alias's entry wholesale.
    merged_chains: dict[str, list[tuple[str, str, str]]] = {
        alias: [route] for alias, route in merged_routes.items()
    }
    merged_chains.update(provider_route_chains or {})
    chat_alias = row.chat_model_alias or settings.ai_default_model_alias
    reasoning_alias = row.reasoning_model_alias or settings.ai_reasoning_model_alias
    embedding_alias = row.embedding_model_alias or settings.ai_embedding_model_alias
    rerank_alias = row.rerank_model_alias or settings.ai_rerank_model_alias
    eval_alias = row.eval_model_alias or settings.ai_eval_model_alias
    selected = (
        chat_alias,
        reasoning_alias,
        embedding_alias,
        rerank_alias,
        eval_alias,
    )
    real_calls_active = bool(
        env_real
        and db_real
        and runtime_config.selected_aliases_accessible(
            selected, merged_routes, encrypted_keys
        )
    )

    return EffectiveAiConfig(
        real_calls_active=real_calls_active,
        chat_model_alias=chat_alias,
        reasoning_model_alias=reasoning_alias,
        embedding_model_alias=embedding_alias,
        rerank_model_alias=rerank_alias,
        eval_model_alias=eval_alias,
        cv_llm_structuring_enabled=bool(row.cv_llm_structuring_enabled),
        job_fit_ai_explanation_enabled=bool(row.job_fit_ai_explanation_enabled),
        daily_budget_usd=float(row.daily_budget_usd),
        provider_routes=merged_routes,
        provider_route_chains=merged_chains,
        provider_key_ciphertexts=encrypted_keys,
    )


async def resolve_and_publish(session: AsyncSession) -> EffectiveAiConfig:
    """Load the singleton (seeding it if absent), build, and publish the snapshot.

    Called on app startup and after every admin PATCH / kill switch. One-way push.
    Also seeds built-in providers and aliases via the provider registry.
    """
    from app.ai.gateway import provider_registry
    from app.ai.gateway.provider_route_chains import load_active_route_chains

    row = await repository.get_or_create_platform(session)
    await provider_registry.ensure_defaults(session)
    await session.flush()
    provider_routes = await provider_registry.load_active_routes(session)
    provider_route_chains = await load_active_route_chains(session)
    provider_key_ciphertexts = await provider_registry.load_active_key_ciphertexts(session)
    cfg = build_effective_config(
        row,
        provider_routes=provider_routes,
        provider_key_ciphertexts=provider_key_ciphertexts,
        provider_route_chains=provider_route_chains,
    )
    runtime_config.publish(cfg)
    return cfg
