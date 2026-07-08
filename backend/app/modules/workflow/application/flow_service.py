"""Draft flow CRUD: RBAC + graph validation + audit. Activation lives in
``activation_service`` (Task 5) since it has different permission and
immutability rules.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.application.context import RequestContext
from app.modules.organization.application.org_reporting_facade import org_type_for
from app.modules.workflow.application.errors import FlowNotEditableError, InvalidGraphError
from app.modules.workflow.domain.models import WorkflowFlow
from app.modules.workflow.domain.validation import validate_graph
from app.shared.audit import AuditContext, write_audit
from app.shared.exceptions import ResourceNotFoundError
from app.shared.permissions import Principal, permission_checker


def _audit_ctx(principal: Principal, ctx: RequestContext) -> AuditContext:
    return AuditContext(
        actor_id=principal.user_id,
        actor_org_id=principal.org_id,
        ip=ctx.ip,
        user_agent=ctx.user_agent,
    )


async def _owner_type_for(session: AsyncSession, *, org_id: uuid.UUID | None) -> str | None:
    """Resolve ``organizations.org_type`` (partner|university) for the acting
    principal's org so every flow records who is allowed to own it
    (docs/PARTNER_RBAC_ANALYTICS_SPEC.md "Allowed flow owners"). Uses the
    approved ``org_reporting_facade`` read seam instead of importing the
    ``Organization`` ORM model directly, per the module-boundary rule
    (docs/ARCHITECTURE.md §8 / ``tests/integration/test_module_boundaries.py``).
    """

    if org_id is None:
        return None
    return await org_type_for(session, org_id)


async def create_draft_flow(
    session: AsyncSession,
    *,
    principal: Principal,
    name: str,
    description: str | None,
    trigger_type: str,
    graph: dict,
    ctx: RequestContext,
    version: int = 1,
    cloned_from_id: uuid.UUID | None = None,
) -> WorkflowFlow:
    permission_checker.require(principal, "workflow", "create", resource_org_id=principal.org_id)

    errors = validate_graph(graph)
    if errors:
        raise InvalidGraphError(errors)

    owner_type = await _owner_type_for(session, org_id=principal.org_id)

    flow = WorkflowFlow(
        name=name,
        description=description,
        trigger_type=trigger_type,
        graph=graph,
        status="DRAFT",
        version=version,
        created_by=principal.user_id,
        created_at=datetime.now(tz=UTC),
        owner_type=owner_type,
        owner_org_id=principal.org_id,
        cloned_from_id=cloned_from_id,
    )
    session.add(flow)
    await session.flush()

    await write_audit(
        session,
        action="workflow.flow_created",
        resource_type="workflow_flow",
        resource_id=flow.id,
        context=_audit_ctx(principal, ctx),
        after={
            "name": name,
            "trigger_type": trigger_type,
            "status": "DRAFT",
            "owner_type": owner_type,
        },
    )
    await session.commit()
    return flow


async def clone_flow(
    session: AsyncSession,
    *,
    principal: Principal,
    flow_id: uuid.UUID,
    ctx: RequestContext,
) -> WorkflowFlow:
    """Duplicate an existing flow (draft, active, paused, or archived) as a
    brand-new draft (version 1, its own id) — never mutates the source flow.
    """

    source = await get_flow(session, principal=principal, flow_id=flow_id)
    clone = await create_draft_flow(
        session,
        principal=principal,
        name=f"{source.name} (copy)",
        description=source.description,
        trigger_type=source.trigger_type,
        graph=source.graph,
        ctx=ctx,
        version=1,
        cloned_from_id=source.id,
    )
    await write_audit(
        session,
        action="workflow.flow_cloned",
        resource_type="workflow_flow",
        resource_id=clone.id,
        context=_audit_ctx(principal, ctx),
        after={"cloned_from_id": str(source.id)},
    )
    await session.commit()
    return clone


async def update_draft_flow(
    session: AsyncSession,
    *,
    principal: Principal,
    flow_id: uuid.UUID,
    name: str | None = None,
    description: str | None = None,
    graph: dict | None = None,
    ctx: RequestContext,
) -> WorkflowFlow:
    permission_checker.require(principal, "workflow", "update", resource_org_id=principal.org_id)
    flow = await get_flow(session, principal=principal, flow_id=flow_id)

    if flow.status != "DRAFT":
        raise FlowNotEditableError()

    before = {"name": flow.name, "graph": flow.graph}
    if graph is not None:
        errors = validate_graph(graph)
        if errors:
            raise InvalidGraphError(errors)
        flow.graph = graph
    if name is not None:
        flow.name = name
    if description is not None:
        flow.description = description

    await session.flush()
    await write_audit(
        session,
        action="workflow.flow_updated",
        resource_type="workflow_flow",
        resource_id=flow.id,
        context=_audit_ctx(principal, ctx),
        before=before,
        after={"name": flow.name, "graph": flow.graph},
    )
    await session.commit()
    return flow


async def get_flow(
    session: AsyncSession, *, principal: Principal, flow_id: uuid.UUID
) -> WorkflowFlow:
    permission_checker.require(principal, "workflow", "read", resource_org_id=principal.org_id)
    flow = await session.get(WorkflowFlow, flow_id)
    if flow is None:
        raise ResourceNotFoundError()
    # Tenant isolation: a flow owned by another org is invisible, not just
    # unwritable — return 404 rather than leaking cross-org flow existence.
    # ``owner_org_id`` is only ``None`` for pre-ownership legacy rows, which
    # only superadmins may still reach.
    if not principal.is_superadmin and flow.owner_org_id != principal.org_id:
        raise ResourceNotFoundError()
    return flow


async def list_flows(
    session: AsyncSession, *, principal: Principal, status: str | None = None
) -> list[WorkflowFlow]:
    permission_checker.require(principal, "workflow", "read", resource_org_id=principal.org_id)
    stmt = select(WorkflowFlow).order_by(WorkflowFlow.created_at.desc())
    if not principal.is_superadmin:
        stmt = stmt.where(WorkflowFlow.owner_org_id == principal.org_id)
    if status is not None:
        stmt = stmt.where(WorkflowFlow.status == status)
    result = await session.execute(stmt)
    return list(result.scalars().all())
