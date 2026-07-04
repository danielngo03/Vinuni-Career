"""Recoverable failed-node task queue: surfaces workflow node failures on the
owning org's todos instead of silently dropping a candidate/application/
notification (docs/PARTNER_RBAC_ANALYTICS_SPEC.md "Failed nodes create
recoverable tasks").
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.application.context import RequestContext
from app.modules.workflow.application.flow_service import _audit_ctx
from app.modules.workflow.domain.models import WorkflowFailedNodeTask
from app.shared.audit import write_audit
from app.shared.exceptions import ResourceNotFoundError
from app.shared.permissions import Principal, permission_checker


async def list_failed_node_tasks(
    session: AsyncSession, *, principal: Principal, status: str | None = "open"
) -> list[WorkflowFailedNodeTask]:
    permission_checker.require(principal, "workflow", "read", resource_org_id=principal.org_id)
    stmt = select(WorkflowFailedNodeTask).order_by(WorkflowFailedNodeTask.created_at.desc())
    if not principal.is_superadmin:
        stmt = stmt.where(WorkflowFailedNodeTask.owner_org_id == principal.org_id)
    if status is not None:
        stmt = stmt.where(WorkflowFailedNodeTask.status == status)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def resolve_failed_node_task(
    session: AsyncSession,
    *,
    principal: Principal,
    task_id: uuid.UUID,
    resolution: str,
    ctx: RequestContext,
) -> WorkflowFailedNodeTask:
    """``resolution`` is ``"resolved"`` (manually handled/retried elsewhere)
    or ``"dismissed"`` (acknowledged, no action taken).
    """

    permission_checker.require(principal, "workflow", "activate", resource_org_id=principal.org_id)
    task = await session.get(WorkflowFailedNodeTask, task_id)
    if task is None:
        raise ResourceNotFoundError()
    if not principal.is_superadmin and task.owner_org_id != principal.org_id:
        raise ResourceNotFoundError()

    task.status = resolution
    task.resolved_at = datetime.now(tz=UTC)
    task.resolved_by = principal.user_id
    await session.flush()

    await write_audit(
        session,
        action="workflow.failed_node_task_resolved",
        resource_type="workflow_failed_node_task",
        resource_id=task.id,
        context=_audit_ctx(principal, ctx),
        after={"status": resolution},
    )
    await session.commit()
    return task
