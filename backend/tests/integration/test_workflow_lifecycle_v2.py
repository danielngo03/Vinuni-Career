"""Coverage for the extended workflow contract:
docs/PARTNER_RBAC_ANALYTICS_SPEC.md "Visual Recruiting Workflow Builder
Contract" — flow ownership, pause/archive/clone lifecycle, dry-run
simulation, activation RBAC capability gating, per-node execution logs, and
failed-node recovery tasks.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.modules.workflow.application import (
    activation_service,
    execution_service,
    flow_service,
    task_service,
)
from app.modules.workflow.application.errors import (
    FlowNotActivatableError,
    MissingActivationCapabilitiesError,
)
from app.modules.workflow.domain.models import (
    WorkflowExecution,
    WorkflowFailedNodeTask,
    WorkflowFlow,
    WorkflowNodeExecutionLog,
)
from app.shared.exceptions import ResourceNotFoundError
from tests.auth_utils import CTX
from tests.org_utils import add_member, make_org_with_admin
from tests.workflow_utils import VALID_GRAPH

SEND_NOTIFICATION_GRAPH = {
    "nodes": [
        {"id": "n1", "type": "trigger", "data": {"trigger_type": "system.partner_registered"}},
        {
            "id": "n2",
            "type": "send_notification",
            "data": {"template_key": "workflow.test_notify", "channel": "email"},
        },
        {"id": "n3", "type": "end", "data": {}},
    ],
    "edges": [{"source": "n1", "target": "n2"}, {"source": "n2", "target": "n3"}],
}


# --- Ownership + tenant isolation -----------------------------------------


@pytest.mark.asyncio
async def test_create_draft_flow_records_owner_type_and_org(db_session) -> None:
    _user, org, admin = await make_org_with_admin(db_session, org_type="partner")

    flow = await flow_service.create_draft_flow(
        db_session, principal=admin, name="Screening flow", description=None,
        trigger_type="system.application_submitted", graph=VALID_GRAPH, ctx=CTX,
    )

    assert flow.owner_type == "partner"
    assert flow.owner_org_id == org.id


@pytest.mark.asyncio
async def test_flow_from_other_org_is_not_visible(db_session) -> None:
    _u1, _org1, admin1 = await make_org_with_admin(db_session, org_type="partner", display_name="Org A")
    _u2, _org2, admin2 = await make_org_with_admin(db_session, org_type="partner", display_name="Org B")

    flow = await flow_service.create_draft_flow(
        db_session, principal=admin1, name="Org A flow", description=None,
        trigger_type="system.application_submitted", graph=VALID_GRAPH, ctx=CTX,
    )

    with pytest.raises(ResourceNotFoundError):
        await flow_service.get_flow(db_session, principal=admin2, flow_id=flow.id)

    others_flows = await flow_service.list_flows(db_session, principal=admin2)
    assert flow.id not in {f.id for f in others_flows}


# --- Lifecycle: pause / resume / archive / clone --------------------------


@pytest.mark.asyncio
async def test_pause_then_resume_active_flow(db_session) -> None:
    _user, org, admin = await make_org_with_admin(db_session, org_type="university")
    flow = await flow_service.create_draft_flow(
        db_session, principal=admin, name="Moderation flow", description=None,
        trigger_type="system.partner_registered", graph=VALID_GRAPH, ctx=CTX,
    )
    await activation_service.activate_flow(db_session, principal=admin, flow_id=flow.id, ctx=CTX)

    paused = await activation_service.pause_flow(db_session, principal=admin, flow_id=flow.id, ctx=CTX)
    assert paused.status == "PAUSED"

    resumed = await activation_service.activate_flow(db_session, principal=admin, flow_id=flow.id, ctx=CTX)
    assert resumed.status == "ACTIVE"
    assert resumed.id == flow.id  # same flow identity, not a new version


@pytest.mark.asyncio
async def test_archive_flow_cannot_be_reactivated(db_session) -> None:
    _user, org, admin = await make_org_with_admin(db_session, org_type="university")
    flow = await flow_service.create_draft_flow(
        db_session, principal=admin, name="Moderation flow", description=None,
        trigger_type="system.partner_registered", graph=VALID_GRAPH, ctx=CTX,
    )
    await activation_service.activate_flow(db_session, principal=admin, flow_id=flow.id, ctx=CTX)
    archived = await activation_service.archive_flow(db_session, principal=admin, flow_id=flow.id, ctx=CTX)
    assert archived.status == "ARCHIVED"

    with pytest.raises(FlowNotActivatableError):
        await activation_service.activate_flow(db_session, principal=admin, flow_id=flow.id, ctx=CTX)


@pytest.mark.asyncio
async def test_clone_flow_creates_new_draft_copy(db_session) -> None:
    _user, org, admin = await make_org_with_admin(db_session, org_type="university")
    flow = await flow_service.create_draft_flow(
        db_session, principal=admin, name="Moderation flow", description=None,
        trigger_type="system.partner_registered", graph=VALID_GRAPH, ctx=CTX,
    )
    await activation_service.activate_flow(db_session, principal=admin, flow_id=flow.id, ctx=CTX)

    clone = await flow_service.clone_flow(db_session, principal=admin, flow_id=flow.id, ctx=CTX)

    assert clone.id != flow.id
    assert clone.status == "DRAFT"
    assert clone.version == 1
    assert clone.cloned_from_id == flow.id
    # Cloning an ACTIVE flow does not disturb the original.
    original = await flow_service.get_flow(db_session, principal=admin, flow_id=flow.id)
    assert original.status == "ACTIVE"


# --- Activation RBAC: node-level capability gating ------------------------


@pytest.mark.asyncio
async def test_activation_blocked_without_node_capability(db_session) -> None:
    _admin_user, org, _admin = await make_org_with_admin(db_session, org_type="partner")
    _member_user, _membership, member = await add_member(
        db_session,
        org=org,
        permissions=[("workflow", "create"), ("workflow", "read"), ("workflow", "activate")],
    )

    flow = await flow_service.create_draft_flow(
        db_session, principal=member, name="Notify flow", description=None,
        trigger_type="system.partner_registered", graph=SEND_NOTIFICATION_GRAPH, ctx=CTX,
    )

    with pytest.raises(MissingActivationCapabilitiesError) as exc_info:
        await activation_service.activate_flow(db_session, principal=member, flow_id=flow.id, ctx=CTX)

    assert "notifications:send" in exc_info.value.details["missing_capabilities"]


@pytest.mark.asyncio
async def test_activation_succeeds_with_matching_capability(db_session) -> None:
    _admin_user, org, _admin = await make_org_with_admin(db_session, org_type="partner")
    _member_user, _membership, member = await add_member(
        db_session,
        org=org,
        permissions=[
            ("workflow", "create"), ("workflow", "read"), ("workflow", "activate"),
            ("notifications", "send"),
        ],
    )

    flow = await flow_service.create_draft_flow(
        db_session, principal=member, name="Notify flow", description=None,
        trigger_type="system.partner_registered", graph=SEND_NOTIFICATION_GRAPH, ctx=CTX,
    )

    activated = await activation_service.activate_flow(db_session, principal=member, flow_id=flow.id, ctx=CTX)
    assert activated.status == "ACTIVE"


# --- Dry-run: no real side effects, redacted, node-by-node outcome --------


@pytest.mark.asyncio
async def test_dry_run_flow_never_activated_and_no_real_side_effects(db_session) -> None:
    _user, org, admin = await make_org_with_admin(db_session, org_type="partner")
    flow = await flow_service.create_draft_flow(
        db_session, principal=admin, name="Notify flow", description=None,
        trigger_type="system.partner_registered", graph=SEND_NOTIFICATION_GRAPH, ctx=CTX,
    )

    result = await execution_service.dry_run_flow(
        db_session, flow=flow, sample_event={"email": "candidate@example.com", "fraud_score": 0.1},
    )

    assert result["is_simulated"] is True
    # PII-looking field is redacted in the recorded sample event.
    assert result["sample_event"]["email"] == "[redacted]"
    step_types = [s["node_type"] for s in result["steps"]]
    assert step_types == ["trigger", "send_notification", "end"]
    assert all(s["status"] == "success" for s in result["steps"])

    # Dry-run must not change the flow's own lifecycle status.
    refreshed = await flow_service.get_flow(db_session, principal=admin, flow_id=flow.id)
    assert refreshed.status == "DRAFT"

    # A simulated execution row/log trail was written for auditability, but
    # marked simulated so it is distinguishable from a real run.
    execution = await db_session.get(WorkflowExecution, uuid.UUID(result["execution_id"]))
    assert execution.is_simulated is True
    logs = (
        await db_session.execute(
            select(WorkflowNodeExecutionLog).where(
                WorkflowNodeExecutionLog.execution_id == execution.id
            )
        )
    ).scalars().all()
    assert all(log.is_simulated for log in logs)
    assert len(logs) == 3


# --- Per-node execution logs + failed-node recovery tasks -----------------


async def _make_active_flow(session, *, org, graph: dict) -> WorkflowFlow:
    flow = WorkflowFlow(
        id=uuid.uuid4(), name="Notify flow", description=None,
        trigger_type="system.partner_registered", graph=graph,
        status="ACTIVE", version=1, created_by=uuid.uuid4(),
        created_at=datetime.now(tz=UTC), owner_type="partner", owner_org_id=org.id,
    )
    session.add(flow)
    await session.flush()
    return flow


@pytest.mark.asyncio
async def test_real_execution_persists_per_node_logs(db_session) -> None:
    _user, org, admin = await make_org_with_admin(db_session, org_type="partner")
    flow = await _make_active_flow(db_session, org=org, graph=VALID_GRAPH)
    execution = WorkflowExecution(
        id=uuid.uuid4(), flow_id=flow.id, trigger_event={"user_id": "u1"},
        idempotency_key="evt-log-1", status="RUNNING",
        started_at=datetime.now(tz=UTC), node_logs=[],
    )
    db_session.add(execution)
    await db_session.flush()
    await db_session.commit()

    await execution_service.execute_flow(db_session, execution_id=execution.id)

    logs = (
        await db_session.execute(
            select(WorkflowNodeExecutionLog).where(
                WorkflowNodeExecutionLog.execution_id == execution.id
            )
        )
    ).scalars().all()
    assert {log.node_id for log in logs} == {"n1", "n2"}
    assert all(log.is_simulated is False for log in logs)


@pytest.mark.asyncio
async def test_failed_node_creates_recoverable_task_and_execution_fails(db_session) -> None:
    _user, org, admin = await make_org_with_admin(db_session, org_type="partner")
    flow = await _make_active_flow(db_session, org=org, graph=SEND_NOTIFICATION_GRAPH)
    execution = WorkflowExecution(
        id=uuid.uuid4(), flow_id=flow.id, trigger_event={},  # no recipient available
        idempotency_key="evt-fail-1", status="RUNNING",
        started_at=datetime.now(tz=UTC), node_logs=[],
    )
    db_session.add(execution)
    await db_session.flush()
    await db_session.commit()

    await execution_service.execute_flow(db_session, execution_id=execution.id)

    refreshed = await db_session.get(WorkflowExecution, execution.id)
    assert refreshed.status == "FAILED"
    assert refreshed.node_logs[-1]["decision"] == "failed"
    assert refreshed.node_logs[-1]["error"]

    tasks = await task_service.list_failed_node_tasks(db_session, principal=admin, status="open")
    assert len(tasks) == 1
    assert tasks[0].execution_id == execution.id
    assert tasks[0].node_id == "n2"
    assert tasks[0].owner_org_id == org.id

    resolved = await task_service.resolve_failed_node_task(
        db_session, principal=admin, task_id=tasks[0].id, resolution="resolved", ctx=CTX,
    )
    assert resolved.status == "resolved"
    assert resolved.resolved_at is not None

    remaining_open = await task_service.list_failed_node_tasks(db_session, principal=admin, status="open")
    assert remaining_open == []


@pytest.mark.asyncio
async def test_dry_run_does_not_create_failed_node_task_on_failure(db_session) -> None:
    """A dry-run node failure (e.g. a deliberately broken sample event) must
    never create a real recoverable task — that would be a false-positive
    ops alert for a test run.
    """

    _user, org, admin = await make_org_with_admin(db_session, org_type="partner")
    flow = await flow_service.create_draft_flow(
        db_session, principal=admin, name="Notify flow", description=None,
        trigger_type="system.partner_registered", graph=SEND_NOTIFICATION_GRAPH, ctx=CTX,
    )

    # Force a failure path is not actually reachable for send_notification in
    # simulate mode (it never fails by design), so assert no task exists
    # after a dry run regardless — this documents/guards the invariant.
    await execution_service.dry_run_flow(db_session, flow=flow, sample_event={})

    tasks = (
        await db_session.execute(select(WorkflowFailedNodeTask))
    ).scalars().all()
    assert tasks == []


@pytest.mark.asyncio
async def test_list_flow_executions_excludes_dry_runs_and_includes_node_logs(
    db_session,
) -> None:
    _user, org, admin = await make_org_with_admin(db_session, org_type="partner")
    flow = await _make_active_flow(db_session, org=org, graph=VALID_GRAPH)

    execution = WorkflowExecution(
        id=uuid.uuid4(), flow_id=flow.id, trigger_event={"user_id": "u1"},
        idempotency_key="evt-history-1", status="RUNNING",
        started_at=datetime.now(tz=UTC), node_logs=[],
    )
    db_session.add(execution)
    await db_session.flush()
    await db_session.commit()
    await execution_service.execute_flow(db_session, execution_id=execution.id)

    await execution_service.dry_run_flow(db_session, flow=flow, sample_event={"user_id": "u2"})

    history = await execution_service.list_flow_executions(db_session, flow=flow)

    assert len(history) == 1
    assert history[0]["id"] == str(execution.id)
    assert history[0]["is_simulated"] is False
    # VALID_GRAPH's n2 is a `human_review` node, which pauses execution
    # (status stays RUNNING) rather than completing — mirrors
    # test_real_execution_persists_per_node_logs's same fixture.
    assert history[0]["status"] == "RUNNING"
    assert {node["node_id"] for node in history[0]["nodes"]} == {"n1", "n2"}
