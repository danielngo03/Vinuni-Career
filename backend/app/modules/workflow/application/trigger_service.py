"""Public entrypoint other modules call to notify the workflow engine that a
business event happened. This is the one function other modules are allowed
to import directly (mirrors how ``enqueue_notification`` is imported across
module boundaries elsewhere in this codebase) — no other workflow internals
should be reached into from outside this module.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.workflow.application.execution_service import execute_flow
from app.modules.workflow.domain.models import WorkflowExecution, WorkflowFlow


async def dispatch_trigger(
    session: AsyncSession,
    *,
    trigger_type: str,
    payload: dict,
    idempotency_key: str,
) -> list[uuid.UUID]:
    active_flows = (
        await session.execute(
            select(WorkflowFlow).where(
                WorkflowFlow.trigger_type == trigger_type,
                WorkflowFlow.status == "ACTIVE",
            )
        )
    ).scalars().all()

    execution_ids: list[uuid.UUID] = []
    for flow in active_flows:
        existing = (
            await session.execute(
                select(WorkflowExecution).where(
                    WorkflowExecution.flow_id == flow.id,
                    WorkflowExecution.idempotency_key == idempotency_key,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            execution_ids.append(existing.id)
            continue

        execution = WorkflowExecution(
            id=uuid.uuid4(),
            flow_id=flow.id,
            trigger_event=payload,
            idempotency_key=idempotency_key,
            status="RUNNING",
            started_at=datetime.now(tz=UTC),
            node_logs=[],
        )
        session.add(execution)
        await session.flush()
        execution_ids.append(execution.id)

    await session.commit()

    for execution_id in execution_ids:
        await execute_flow(session, execution_id=execution_id)

    return execution_ids
