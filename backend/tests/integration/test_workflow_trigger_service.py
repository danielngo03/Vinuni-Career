from __future__ import annotations

import uuid

import pytest
from app.modules.workflow.application import activation_service, flow_service, trigger_service
from app.modules.workflow.domain.models import WorkflowExecution

from tests.auth_utils import CTX
from tests.org_utils import make_org_with_admin
from tests.workflow_utils import VALID_GRAPH


@pytest.mark.asyncio
async def test_dispatch_creates_execution_for_matching_active_flow(db_session) -> None:
    _user, org, admin = await make_org_with_admin(db_session, org_type="university")
    flow = await flow_service.create_draft_flow(
        db_session,
        principal=admin,
        name="Student verification",
        description=None,
        trigger_type="system.student_registered",
        graph=VALID_GRAPH,
        ctx=CTX,
    )
    await activation_service.activate_flow(db_session, principal=admin, flow_id=flow.id, ctx=CTX)

    execution_ids = await trigger_service.dispatch_trigger(
        db_session,
        trigger_type="system.student_registered",
        payload={"user_id": str(uuid.uuid4())},
        idempotency_key="student-registered-u1",
    )

    assert len(execution_ids) == 1
    execution = await db_session.get(WorkflowExecution, execution_ids[0])
    assert execution.flow_id == flow.id


@pytest.mark.asyncio
async def test_dispatch_ignores_draft_and_archived_flows(db_session) -> None:
    _user, org, admin = await make_org_with_admin(db_session, org_type="university")
    await flow_service.create_draft_flow(
        db_session,
        principal=admin,
        name="Draft only",
        description=None,
        trigger_type="system.student_registered",
        graph=VALID_GRAPH,
        ctx=CTX,
    )

    execution_ids = await trigger_service.dispatch_trigger(
        db_session,
        trigger_type="system.student_registered",
        payload={"user_id": str(uuid.uuid4())},
        idempotency_key="student-registered-u2",
    )

    assert execution_ids == []


@pytest.mark.asyncio
async def test_dispatch_is_idempotent_for_same_key(db_session) -> None:
    _user, org, admin = await make_org_with_admin(db_session, org_type="university")
    flow = await flow_service.create_draft_flow(
        db_session,
        principal=admin,
        name="Student verification",
        description=None,
        trigger_type="system.student_registered",
        graph=VALID_GRAPH,
        ctx=CTX,
    )
    await activation_service.activate_flow(db_session, principal=admin, flow_id=flow.id, ctx=CTX)

    first = await trigger_service.dispatch_trigger(
        db_session,
        trigger_type="system.student_registered",
        payload={"user_id": "u1"},
        idempotency_key="dup-key",
    )
    second = await trigger_service.dispatch_trigger(
        db_session,
        trigger_type="system.student_registered",
        payload={"user_id": "u1"},
        idempotency_key="dup-key",
    )

    assert first == second
