"""Compiles a DRAFT routing graph into the real ai_model_aliases row the
gateway reads, then republishes EffectiveAiConfig via the same
commit -> resolve_and_publish -> commit seam ai_settings' provider/alias
endpoints already use (backend/app/modules/ai_settings/api/router.py's
``_commit_and_republish``). The graph itself never becomes a second runtime
read path.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.gateway.provider_models import AiModelAlias, AiProviderConfig
from app.modules.ai_settings.application import resolver, routing_service, settings_service
from app.modules.ai_settings.domain.aliases import ALIAS_FIELDS
from app.modules.ai_settings.domain.routing_models import AiRoutingGraph, AiRoutingGraphActivation
from app.modules.ai_settings.infrastructure import repository as ai_settings_repo
from app.modules.auth.application.context import RequestContext
from app.shared.audit import AuditContext, write_audit
from app.shared.exceptions import ResourceNotFoundError, ValidationFailedError
from app.shared.permissions import Principal

_FIELD_FOR_FAMILY = {family: field for field, family in ALIAS_FIELDS.items()}


async def activate_routing_graph(
    session: AsyncSession, *, principal: Principal, graph_id: uuid.UUID, ctx: RequestContext
) -> AiRoutingGraph:
    settings_service.require_platform_superadmin(principal)
    row = await routing_service.get_graph(session, principal=principal, graph_id=graph_id)

    settings_row = await ai_settings_repo.get_or_create_platform(session)
    field = _FIELD_FOR_FAMILY.get(row.task_family)
    alias_name = getattr(settings_row, field, None) if field else None
    if not alias_name:
        raise ValidationFailedError(
            "Chưa cấu hình alias cho nhóm tác vụ này.",
            details={"reason": "no_configured_alias", "task_family": row.task_family},
        )

    alias = (
        await session.execute(select(AiModelAlias).where(AiModelAlias.alias_name == alias_name))
    ).scalar_one_or_none()
    if alias is None:
        raise ResourceNotFoundError()

    provider_nodes = sorted(
        (n for n in row.graph["nodes"] if n.get("type") == "provider"),
        key=lambda n: n["data"]["order"],
    )
    primary_id = uuid.UUID(provider_nodes[0]["data"]["provider_id"])
    fallback_ids = [uuid.UUID(n["data"]["provider_id"]) for n in provider_nodes[1:]]

    fallback_names: list[str] = []
    if fallback_ids:
        stmt = select(AiProviderConfig).where(AiProviderConfig.id.in_(fallback_ids))
        providers = (await session.execute(stmt)).scalars().all()
        by_id = {p.id: p.name for p in providers}
        fallback_names = [by_id[pid] for pid in fallback_ids if pid in by_id]

    alias.provider_id = primary_id
    alias.fallback_provider_names = ",".join(fallback_names) if fallback_names else None
    row.compiled_alias_id = alias.id
    row.status = "ACTIVE"
    row.activated_at = datetime.now(tz=UTC)
    await session.flush()

    session.add(
        AiRoutingGraphActivation(
            id=uuid.uuid4(),
            graph_id=row.id,
            graph_version=row.version,
            activated_by=principal.user_id,
            activated_at=datetime.now(tz=UTC),
        )
    )
    await write_audit(
        session,
        action="ai_settings.routing_graph_activated",
        resource_type="ai_routing_graph",
        resource_id=row.id,
        context=AuditContext(
            actor_id=principal.user_id,
            actor_org_id=principal.org_id,
            ip=ctx.ip,
            user_agent=ctx.user_agent,
        ),
        after={"task_family": row.task_family, "alias_name": alias_name},
    )
    await session.commit()
    await resolver.resolve_and_publish(session)
    await session.commit()
    return row
