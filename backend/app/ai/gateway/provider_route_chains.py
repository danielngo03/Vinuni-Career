"""Ordered fallback-provider-chain resolution for AI model aliases (AI_PRODUCT_SPEC §5.2).

Split out of ``provider_registry.py`` to keep that file from ballooning
(project clean-code mandate). Owns:

- Parsing/normalizing the admin-configured ``fallback_provider_names`` column
  (comma-separated, ORDER PRESERVED) on ``AiModelAlias``.
- Loading the full ORDERED provider chain per alias for the runtime snapshot,
  used by ``app.ai.gateway.factory.get_provider_for_alias`` /
  ``app.ai.gateway.fallback_chain.FallbackChainProvider``.

This module does not build or execute providers — it only resolves data.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.gateway.provider_models import AiModelAlias, AiProviderConfig

logger = logging.getLogger("ai.provider_route_chains")


def parse_fallback_names(raw: str | None) -> list[str]:
    """Parse a comma-separated, ordered provider-name list. Order is preserved."""

    if not raw:
        return []
    return [name.strip() for name in raw.split(",") if name.strip()]


def normalize_fallback_payload(value: Any) -> str | None:
    """Normalize an admin-supplied fallback provider list into the stored form.

    Accepts either an ordered ``list[str]`` (preferred, from the admin API) or
    an already-comma-separated string. Order is preserved; blanks are dropped.
    """

    if value is None:
        return None
    if isinstance(value, str):
        names = parse_fallback_names(value)
    else:
        names = [str(name).strip() for name in value if str(name).strip()]
    return ",".join(names) if names else None


async def load_active_route_chains(
    db: AsyncSession,
) -> dict[str, list[tuple[str, str, str]]]:
    """Return the ORDERED fallback provider chain per alias (AI_PRODUCT_SPEC §5.2).

    Returns: {alias_name: [(provider_name, base_url, model_id), ...]} where index
    0 is the alias's primary provider and subsequent entries are the admin's
    configured ``fallback_provider_names`` in order. Fallback hops reuse the
    alias's ``model_id`` — the fallback provider must serve an equivalent model.
    Unknown or inactive fallback provider names are dropped silently; duplicate
    provider names (already earlier in the chain) are skipped. Aliases with no
    configured fallback still produce a chain of length 1, so callers can always
    use this map without a separate single-route special case.
    """

    provider_rows = (
        await db.execute(
            select(AiProviderConfig.name, AiProviderConfig.base_url).where(
                AiProviderConfig.is_active.is_(True)
            )
        )
    ).all()
    provider_base_urls: dict[str, str] = {row[0]: row[1] for row in provider_rows}

    alias_rows = (
        await db.execute(
            select(
                AiModelAlias.alias_name,
                AiModelAlias.model_id,
                AiModelAlias.fallback_provider_names,
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

    chains: dict[str, list[tuple[str, str, str]]] = {}
    for alias_name, model_id, fallback_raw, provider_name, base_url in alias_rows:
        chain: list[tuple[str, str, str]] = [(provider_name, base_url, model_id)]
        seen = {provider_name}
        for fallback_name in parse_fallback_names(fallback_raw):
            if fallback_name in seen:
                continue
            fallback_base_url = provider_base_urls.get(fallback_name)
            if fallback_base_url is None:
                logger.warning(
                    "fallback_provider_not_found_or_inactive",
                    extra={"alias": alias_name, "provider": fallback_name},
                )
                continue
            chain.append((fallback_name, fallback_base_url, model_id))
            seen.add(fallback_name)
        chains[alias_name] = chain
    return chains
