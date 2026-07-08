from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from app.modules.workflow.application import execution_service
from app.modules.workflow.domain.models import WorkflowExecution, WorkflowFlow

CONDITION_GRAPH = {
    "nodes": [
        {"id": "n1", "type": "trigger", "data": {"trigger_type": "system.partner_registered"}},
        {"id": "n2", "type": "condition", "data": {"expression": "{{fraud_score}} > 0.70"}},
        {
            "id": "n3",
            "type": "human_review",
            "data": {
                "assignee_mode": "queue",
                "assignee_department_id": "22222222-2222-2222-2222-222222222222",
                "sla_hours": 24,
            },
        },
        {"id": "n4", "type": "action", "data": {"action": "auto_approve"}},
        {"id": "n5", "type": "end", "data": {}},
    ],
    "edges": [
        {"source": "n1", "target": "n2"},
        {"source": "n2", "target": "n3", "condition": "true"},
        {"source": "n2", "target": "n4", "condition": "false"},
        {"source": "n3", "target": "n5"},
        {"source": "n4", "target": "n5"},
    ],
}


async def _make_flow_and_execution(db_session, *, trigger_event: dict) -> WorkflowExecution:
    flow = WorkflowFlow(
        id=uuid.uuid4(), name="Partner approval", description=None,
        trigger_type="system.partner_registered", graph=CONDITION_GRAPH,
        status="ACTIVE", version=1, created_by=uuid.uuid4(),
        created_at=datetime.now(tz=UTC),
    )
    db_session.add(flow)
    await db_session.flush()
    execution = WorkflowExecution(
        id=uuid.uuid4(), flow_id=flow.id, trigger_event=trigger_event,
        idempotency_key="evt-1", status="RUNNING",
        started_at=datetime.now(tz=UTC), node_logs=[],
    )
    db_session.add(execution)
    await db_session.flush()
    await db_session.commit()
    return execution


@pytest.mark.asyncio
async def test_low_fraud_score_auto_approves(db_session) -> None:
    execution = await _make_flow_and_execution(db_session, trigger_event={"fraud_score": 0.10})

    await execution_service.execute_flow(db_session, execution_id=execution.id)

    refreshed = await db_session.get(WorkflowExecution, execution.id)
    assert refreshed.status == "COMPLETED"
    node_types = [log["node_id"] for log in refreshed.node_logs]
    assert node_types == ["n1", "n2", "n4", "n5"]


@pytest.mark.asyncio
async def test_high_fraud_score_routes_to_human_review_and_pauses(db_session) -> None:
    execution = await _make_flow_and_execution(db_session, trigger_event={"fraud_score": 0.95})

    await execution_service.execute_flow(db_session, execution_id=execution.id)

    refreshed = await db_session.get(WorkflowExecution, execution.id)
    assert refreshed.status == "RUNNING"
    last_log = refreshed.node_logs[-1]
    assert last_log["node_id"] == "n3"
    assert last_log["decision"] == "awaiting_human_review"


@pytest.mark.asyncio
async def test_execution_is_idempotent_per_flow_and_event(db_session) -> None:
    execution = await _make_flow_and_execution(db_session, trigger_event={"fraud_score": 0.10})

    await execution_service.execute_flow(db_session, execution_id=execution.id)
    await execution_service.execute_flow(db_session, execution_id=execution.id)

    refreshed = await db_session.get(WorkflowExecution, execution.id)
    completed_end_logs = [log for log in refreshed.node_logs if log["node_id"] == "n5"]
    assert len(completed_end_logs) == 1
