"""Draft routing-graph CRUD: RBAC + structural validation + audit. Activation
(compile into ai_model_aliases + republish EffectiveAiConfig) lives in
``routing_activation_service`` (Task 4) since it has a different permission
surface and side effect (mutating the live gateway config).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai_settings.application import settings_service
from app.modules.ai_settings.application.routing_errors import (
    InvalidRoutingGraphError,
    RoutingGraphNotEditableError,
)
from app.modules.ai_settings.domain.routing_models import AiRoutingGraph
from app.modules.ai_settings.domain.routing_validation import validate_routing_graph
from app.modules.auth.application.context import RequestContext
from app.shared.audit import AuditContext, write_audit
from app.shared.exceptions import ResourceNotFoundError
from app.shared.permissions import Principal


def _audit_ctx(principal: Principal, ctx: RequestContext) -> AuditContext:
    return AuditContext(
        actor_id=principal.user_id,
        actor_org_id=principal.org_id,
        ip=ctx.ip,
        user_agent=ctx.user_agent,
    )


async def create_draft_graph(
    session: AsyncSession,
    *,
    principal: Principal,
    task_family: str,
    graph: dict,
    ctx: RequestContext,
) -> AiRoutingGraph:
    settings_service.require_platform_superadmin(principal)

    errors = validate_routing_graph(graph)
    if errors:
        raise InvalidRoutingGraphError(errors)

    row = AiRoutingGraph(
        task_family=task_family,
        graph=graph,
        status="DRAFT",
        version=1,
        created_by=principal.user_id,
        created_at=datetime.now(tz=UTC),
    )
    session.add(row)
    await session.flush()

    await write_audit(
        session,
        action="ai_settings.routing_graph_created",
        resource_type="ai_routing_graph",
        resource_id=row.id,
        context=_audit_ctx(principal, ctx),
        after={"task_family": task_family, "status": "DRAFT"},
    )
    await session.commit()
    return row


async def update_draft_graph(
    session: AsyncSession,
    *,
    principal: Principal,
    graph_id: uuid.UUID,
    graph: dict,
    ctx: RequestContext,
) -> AiRoutingGraph:
    settings_service.require_platform_superadmin(principal)
    row = await get_graph(session, principal=principal, graph_id=graph_id)

    if row.status != "DRAFT":
        raise RoutingGraphNotEditableError()

    errors = validate_routing_graph(graph)
    if errors:
        raise InvalidRoutingGraphError(errors)

    before = {"graph": row.graph}
    row.graph = graph
    await session.flush()
    await write_audit(
        session,
        action="ai_settings.routing_graph_updated",
        resource_type="ai_routing_graph",
        resource_id=row.id,
        context=_audit_ctx(principal, ctx),
        before=before,
        after={"graph": graph},
    )
    await session.commit()
    return row


async def get_graph(
    session: AsyncSession, *, principal: Principal, graph_id: uuid.UUID
) -> AiRoutingGraph:
    settings_service.require_platform_superadmin(principal)
    row = await session.get(AiRoutingGraph, graph_id)
    if row is None:
        raise ResourceNotFoundError()
    return row


async def list_graphs(
    session: AsyncSession, *, principal: Principal, task_family: str | None = None
) -> list[AiRoutingGraph]:
    settings_service.require_platform_superadmin(principal)
    stmt = select(AiRoutingGraph).order_by(AiRoutingGraph.created_at.desc())
    if task_family is not None:
        stmt = stmt.where(AiRoutingGraph.task_family == task_family)
    result = await session.execute(stmt)
    return list(result.scalars().all())
