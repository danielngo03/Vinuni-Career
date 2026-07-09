from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.application.context import RequestContext
from app.modules.workflow.application import flow_service
from app.modules.workflow.application.errors import (
    FlowNotActivatableError,
    InvalidGraphError,
    MissingActivationCapabilitiesError,
)
from app.modules.workflow.domain.graph import required_capability_for_node
from app.modules.workflow.domain.models import WorkflowFlow
from app.modules.workflow.domain.validation import validate_graph
from app.shared.audit import write_audit
from app.shared.permissions import Principal, permission_checker


def _missing_capabilities(principal: Principal, graph: dict) -> list[str]:
    """Every action a flow can execute must be inside the activator's grants
    (docs/PARTNER_RBAC_ANALYTICS_SPEC.md: "Activation requires RBAC grants for
    every action the flow can execute"). Superadmins always pass. Nodes with
    no mapped/overridden capability are skipped — the platform cannot invent a
    permission for a custom action, so it falls back on the ``workflow:activate``
    check already required to call this function at all.
    """

    if principal.is_superadmin:
        return []

    missing: list[str] = []
    for node in graph.get("nodes", []):
        capability = required_capability_for_node(node)
        if capability is None:
            continue
        resource_type, action = capability
        if not permission_checker.can(
            principal, resource_type, action, resource_org_id=principal.org_id
        ):
            label = f"{resource_type}:{action}"
            if label not in missing:
                missing.append(label)
    return missing


async def activate_flow(
    session: AsyncSession, *, principal: Principal, flow_id: uuid.UUID, ctx: RequestContext
) -> WorkflowFlow:
    permission_checker.require(principal, "workflow", "activate", resource_org_id=principal.org_id)
    flow = await flow_service.get_flow(session, principal=principal, flow_id=flow_id)

    if flow.status not in ("DRAFT", "PAUSED"):
        raise FlowNotActivatableError(from_status=flow.status)

    # Re-validate the graph at the activation gate, not only at write time: a flow
    # persisted before a validation rule tightened (or otherwise reaching ACTIVE
    # with a stale/invalid graph) must not go live.
    graph_errors = validate_graph(flow.graph)
    if graph_errors:
        raise InvalidGraphError(graph_errors)

    missing = _missing_capabilities(principal, flow.graph)
    if missing:
        raise MissingActivationCapabilitiesError(missing)

    from_status = flow.status
    flow.status = "ACTIVE"
    if flow.activated_at is None:
        flow.activated_at = datetime.now(tz=UTC)
    await session.flush()

    await write_audit(
        session,
        action="workflow.flow_activated",
        resource_type="workflow_flow",
        resource_id=flow.id,
        context=flow_service._audit_ctx(principal, ctx),
        before={"status": from_status},
        after={"status": "ACTIVE", "trigger_type": flow.trigger_type},
    )
    await session.commit()
    return flow


async def pause_flow(
    session: AsyncSession, *, principal: Principal, flow_id: uuid.UUID, ctx: RequestContext
) -> WorkflowFlow:
    """Temporarily suspend an ACTIVE flow. Unlike archive, this keeps the
    flow's identity/version as the org's "current" flow for this trigger —
    ``activate_flow`` can resume it directly from PAUSED.
    """

    permission_checker.require(principal, "workflow", "activate", resource_org_id=principal.org_id)
    flow = await flow_service.get_flow(session, principal=principal, flow_id=flow_id)

    if flow.status != "ACTIVE":
        raise FlowNotActivatableError(from_status=flow.status)

    flow.status = "PAUSED"
    await session.flush()
    await write_audit(
        session,
        action="workflow.flow_paused",
        resource_type="workflow_flow",
        resource_id=flow.id,
        context=flow_service._audit_ctx(principal, ctx),
        before={"status": "ACTIVE"},
        after={"status": "PAUSED"},
    )
    await session.commit()
    return flow


async def archive_flow(
    session: AsyncSession, *, principal: Principal, flow_id: uuid.UUID, ctx: RequestContext
) -> WorkflowFlow:
    """Soft-retire a flow permanently. Unlike pause, an archived flow cannot be
    reactivated in place — a new draft (``clone_flow``) is required.
    """

    permission_checker.require(principal, "workflow", "activate", resource_org_id=principal.org_id)
    flow = await flow_service.get_flow(session, principal=principal, flow_id=flow_id)

    before_status = flow.status
    flow.status = "ARCHIVED"
    await session.flush()
    await write_audit(
        session,
        action="workflow.flow_archived",
        resource_type="workflow_flow",
        resource_id=flow.id,
        context=flow_service._audit_ctx(principal, ctx),
        before={"status": before_status},
        after={"status": "ARCHIVED"},
    )
    await session.commit()
    return flow


async def deactivate_flow(
    session: AsyncSession, *, principal: Principal, flow_id: uuid.UUID, ctx: RequestContext
) -> WorkflowFlow:
    """Legacy alias kept for the existing ``/workflows/{id}/deactivate`` route
    and docs/API_CONTRACTS.md contract — behaves as ``archive_flow``.
    """

    return await archive_flow(session, principal=principal, flow_id=flow_id, ctx=ctx)


async def create_new_draft_version(
    session: AsyncSession,
    *,
    principal: Principal,
    flow_id: uuid.UUID,
    graph: dict,
    ctx: RequestContext,
) -> WorkflowFlow:
    """An ACTIVE flow can never be edited in place. This creates a brand-new
    flow row carrying the next version number, left in DRAFT until separately
    activated (which then archives the prior ACTIVE version — left to the
    caller/UI flow, not auto-archived here, since a review step is expected
    per docs/BACKLOG.md B-394 dry-run gate before promotion).
    """

    original = await flow_service.get_flow(session, principal=principal, flow_id=flow_id)
    return await flow_service.create_draft_flow(
        session,
        principal=principal,
        name=original.name,
        description=original.description,
        trigger_type=original.trigger_type,
        graph=graph,
        ctx=ctx,
        version=original.version + 1,
        cloned_from_id=original.id,
    )
