"""Workflow flow HTTP routes: HTTP-only, delegates RBAC/audit to application
services, per docs/API_CONTRACTS.md's /workflows contract.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.modules.auth.api.deps import CurrentAuth, get_current_auth
from app.modules.workflow.api.schemas import (
    CreateFlowRequest,
    DryRunFlowRequest,
    ResolveFailedNodeTaskRequest,
    UpdateFlowRequest,
)
from app.modules.workflow.application import (
    activation_service,
    execution_service,
    flow_service,
    task_service,
)
from app.shared.permissions import permission_checker
from app.shared.responses import success

router = APIRouter(prefix="/workflows", tags=["workflow"])


def _task_presenter(task) -> dict:
    return {
        "id": str(task.id),
        "execution_id": str(task.execution_id),
        "flow_id": str(task.flow_id),
        "node_id": task.node_id,
        "node_type": task.node_type,
        "owner_type": task.owner_type,
        "user_safe_error": task.user_safe_error,
        "status": task.status,
        "created_at": task.created_at.isoformat(),
        "resolved_at": task.resolved_at.isoformat() if task.resolved_at else None,
    }


def _presenter(flow) -> dict:
    return {
        "id": str(flow.id),
        "name": flow.name,
        "description": flow.description,
        "trigger_type": flow.trigger_type,
        "status": flow.status,
        "version": flow.version,
        "graph": flow.graph,
        "owner_type": flow.owner_type,
        "owner_org_id": str(flow.owner_org_id) if flow.owner_org_id else None,
        "cloned_from_id": str(flow.cloned_from_id) if flow.cloned_from_id else None,
        "activated_at": flow.activated_at.isoformat() if flow.activated_at else None,
    }


@router.post("")
async def create_flow(
    body: CreateFlowRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    flow = await flow_service.create_draft_flow(
        session, principal=auth.principal, name=body.name, description=body.description,
        trigger_type=body.trigger_type, graph=body.graph, ctx=auth.ctx,
    )
    return success(_presenter(flow))


@router.patch("/{flow_id}")
async def update_flow(
    flow_id: uuid.UUID,
    body: UpdateFlowRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    flow = await flow_service.update_draft_flow(
        session, principal=auth.principal, flow_id=flow_id, name=body.name,
        description=body.description, graph=body.graph, ctx=auth.ctx,
    )
    return success(_presenter(flow))


@router.get("/{flow_id}")
async def get_flow(
    flow_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    flow = await flow_service.get_flow(session, principal=auth.principal, flow_id=flow_id)
    return success(_presenter(flow))


@router.get("")
async def list_flows(
    status_filter: str | None = Query(default=None, alias="status"),
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    flows = await flow_service.list_flows(session, principal=auth.principal, status=status_filter)
    return success([_presenter(f) for f in flows])


@router.post("/{flow_id}/activate")
async def activate_flow(
    flow_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    flow = await activation_service.activate_flow(
        session, principal=auth.principal, flow_id=flow_id, ctx=auth.ctx
    )
    return success(_presenter(flow))


@router.post("/{flow_id}/deactivate")
async def deactivate_flow(
    flow_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    flow = await activation_service.deactivate_flow(
        session, principal=auth.principal, flow_id=flow_id, ctx=auth.ctx
    )
    return success(_presenter(flow))


@router.post("/{flow_id}/pause")
async def pause_flow(
    flow_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    flow = await activation_service.pause_flow(
        session, principal=auth.principal, flow_id=flow_id, ctx=auth.ctx
    )
    return success(_presenter(flow))


@router.post("/{flow_id}/archive")
async def archive_flow(
    flow_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    flow = await activation_service.archive_flow(
        session, principal=auth.principal, flow_id=flow_id, ctx=auth.ctx
    )
    return success(_presenter(flow))


@router.post("/{flow_id}/clone")
async def clone_flow(
    flow_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    flow = await flow_service.clone_flow(
        session, principal=auth.principal, flow_id=flow_id, ctx=auth.ctx
    )
    return success(_presenter(flow))


@router.post("/{flow_id}/test")
async def dry_run_flow(
    flow_id: uuid.UUID,
    body: DryRunFlowRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    flow = await flow_service.get_flow(session, principal=auth.principal, flow_id=flow_id)
    # Dry-run availability mirrors "can edit/prepare this flow" rather than
    # "can already activate it" — an author should be able to test a draft
    # before requesting activation from someone with broader grants.
    permission_checker.require(
        auth.principal, "workflow", "update", resource_org_id=auth.principal.org_id
    )
    result = await execution_service.dry_run_flow(
        session, flow=flow, sample_event=body.sample_event
    )
    return success(result)


@router.get("/{flow_id}/executions")
async def list_flow_executions(
    flow_id: uuid.UUID,
    limit: int = Query(default=20, ge=1, le=100),
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    flow = await flow_service.get_flow(session, principal=auth.principal, flow_id=flow_id)
    executions = await execution_service.list_flow_executions(session, flow=flow, limit=limit)
    return success(executions)


@router.get("/tasks")
async def list_failed_node_tasks(
    status_filter: str | None = Query(default="open", alias="status"),
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    tasks = await task_service.list_failed_node_tasks(
        session, principal=auth.principal, status=status_filter
    )
    return success([_task_presenter(t) for t in tasks])


@router.post("/tasks/{task_id}/resolve")
async def resolve_failed_node_task(
    task_id: uuid.UUID,
    body: ResolveFailedNodeTaskRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    task = await task_service.resolve_failed_node_task(
        session, principal=auth.principal, task_id=task_id, resolution=body.resolution, ctx=auth.ctx,
    )
    return success(_task_presenter(task))
