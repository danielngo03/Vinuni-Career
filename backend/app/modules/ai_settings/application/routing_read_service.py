"""Read-only view of live provider/alias/circuit-breaker state for the routing
canvas. Curated vendor_label/model_family_label are the DEFAULT display; raw
provider_internal/model_id are populated only for callers holding
ai_settings:view_provider_identity, per ADR-0011.1 (docs/API_CONTRACTS.md).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.gateway.factory import get_circuit_state
from app.ai.gateway.provider_models import AiModelAlias, AiProviderConfig
from app.modules.ai_settings.application import settings_service
from app.modules.auth.application.context import RequestContext
from app.shared.audit import AuditContext, write_audit
from app.shared.permissions import Principal

# Static, ai-engineer-maintained curated labels per provider_type — never the
# literal SDK model string. Extend this map as new provider_type values ship;
# do not derive it from provider.name (that IS the raw identifier).
_VENDOR_LABELS: dict[str, str] = {
    "openai_compatible": "OpenAI-compatible provider",
    "anthropic": "Anthropic",
    "local": "Local/self-hosted model",
}


def _has_identity_permission(principal: Principal) -> bool:
    # Single source of truth for the provider-identity reveal rule.
    return settings_service.can_view_provider_identity(principal)


def _alias_matches_family(alias: AiModelAlias, task_family: str) -> bool:
    """True when ``alias`` is usable for ``task_family``.

    Mirrors ``settings_service._allowed_aliases_for_field``'s membership rule:
    ``task_families`` is a comma-separated list (e.g. ``"chat,eval"``); ``NULL``/
    empty means the alias is usable for ANY task family. Equality-only matching
    would silently miss multi-family built-in aliases (AI_PRODUCT_SPEC §5.2).
    """

    families = {item.strip() for item in (alias.task_families or "").split(",") if item.strip()}
    return not families or task_family in families


async def get_routing_canvas_view(
    session: AsyncSession, *, principal: Principal, task_family: str, ctx: RequestContext
) -> dict:
    await settings_service._require_ai_settings_admin(session, principal, "read")

    all_aliases = (
        await session.execute(select(AiModelAlias).where(AiModelAlias.is_active.is_(True)))
    ).scalars().all()
    aliases = [a for a in all_aliases if _alias_matches_family(a, task_family)]

    provider_ids = {a.provider_id for a in aliases if a.provider_id is not None}
    providers = (
        await session.execute(select(AiProviderConfig).where(AiProviderConfig.id.in_(provider_ids)))
    ).scalars().all() if provider_ids else []

    show_raw = _has_identity_permission(principal)
    if show_raw:
        await write_audit(
            session,
            action="ai_settings.provider_identity_viewed",
            resource_type="ai_model_alias",
            context=AuditContext(
                actor_id=principal.user_id,
                actor_org_id=principal.org_id,
                ip=ctx.ip,
                user_agent=ctx.user_agent,
            ),
        )
        await session.commit()

    alias_by_provider = {a.provider_id: a for a in aliases}
    provider_entries = []
    for provider in providers:
        alias = alias_by_provider.get(provider.id)
        provider_entries.append(
            {
                "provider_id": str(provider.id),
                "vendor_label": _VENDOR_LABELS.get(provider.provider_type, "AI provider"),
                "model_family_label": task_family.capitalize(),
                "circuit_state": get_circuit_state(provider.name),
                "provider_internal": provider.name if show_raw else None,
                "model_id": (alias.model_id if alias and show_raw else None),
            }
        )

    return {"task_family": task_family, "providers": provider_entries}
