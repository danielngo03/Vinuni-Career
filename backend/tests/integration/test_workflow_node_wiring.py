"""Real side-effect wiring for consequential workflow nodes.

The engine used to log ``move_candidate`` / ``send_notification`` / ``webhook``
as no-op "intent". These tests pin the now-real wiring AND its safety rails:

- ``move_candidate`` calls the approved ``recruitment`` stage seam with a
  tenant-scoped system principal + a stable per-node idempotency key; a dry-run
  performs NO write; a downstream failure produces a recoverable failed-node
  task (never a crash / leak).
- ``send_notification`` enqueues with a stable per-node ``dedupe_key`` so a
  retry can't double-send.
- ``webhook`` sends only a REDACTED payload through the SSRF-guarded dispatcher,
  and a dry-run sends nothing.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from app.modules.recruitment.application import stage_service
from app.modules.workflow.application import execution_service, webhook_dispatch
from app.modules.workflow.domain.models import WorkflowExecution, WorkflowFlow


def _linear_graph(node_id: str, node_type: str, data: dict) -> dict:
    return {
        "nodes": [
            {"id": "t", "type": "trigger", "data": {"trigger_type": "x"}},
            {"id": node_id, "type": node_type, "data": data},
            {"id": "e", "type": "end", "data": {}},
        ],
        "edges": [
            {"source": "t", "target": node_id},
            {"source": node_id, "target": "e"},
        ],
    }


async def _make(
    db_session,
    *,
    graph: dict,
    trigger_event: dict,
    owner_org_id: uuid.UUID | None,
) -> tuple[WorkflowFlow, WorkflowExecution]:
    flow = WorkflowFlow(
        id=uuid.uuid4(),
        name="wiring",
        description=None,
        trigger_type="x",
        graph=graph,
        status="ACTIVE",
        version=1,
        created_by=uuid.uuid4(),
        created_at=datetime.now(tz=UTC),
        owner_org_id=owner_org_id,
    )
    db_session.add(flow)
    await db_session.flush()
    execution = WorkflowExecution(
        id=uuid.uuid4(),
        flow_id=flow.id,
        trigger_event=trigger_event,
        idempotency_key=f"evt-{uuid.uuid4()}",
        status="RUNNING",
        started_at=datetime.now(tz=UTC),
        node_logs=[],
    )
    db_session.add(execution)
    await db_session.flush()
    await db_session.commit()
    return flow, execution


# --------------------------------------------------------------------------- #
# move_candidate                                                              #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_move_candidate_calls_stage_seam_with_scoped_principal(
    db_session, monkeypatch
) -> None:
    org_id = uuid.uuid4()
    app_id = uuid.uuid4()
    captured: dict = {}

    async def _fake_advance(session, *, principal, application_id, idempotency_key, ctx, locale):
        captured["principal"] = principal
        captured["application_id"] = application_id
        captured["idempotency_key"] = idempotency_key
        return {"ok": True}

    monkeypatch.setattr(stage_service, "advance_application_stage", _fake_advance)

    flow, execution = await _make(
        db_session,
        graph=_linear_graph("m", "move_candidate", {}),
        trigger_event={"application_id": str(app_id)},
        owner_org_id=org_id,
    )

    await execution_service.execute_flow(db_session, execution_id=execution.id)

    refreshed = await db_session.get(WorkflowExecution, execution.id)
    assert refreshed.status == "COMPLETED"
    # Real seam invoked with the resolved application + a stable per-node key.
    assert captured["application_id"] == app_id
    assert captured["idempotency_key"] == f"wf:{execution.id}:m"
    # Tenant-scoped SYSTEM principal — never superadmin, never a user.
    principal = captured["principal"]
    assert principal.org_id == org_id
    assert principal.is_superadmin is False
    assert principal.user_id is None


@pytest.mark.asyncio
async def test_move_candidate_dry_run_performs_no_write(db_session, monkeypatch) -> None:
    called = {"n": 0}

    async def _fake_advance(*args, **kwargs):
        called["n"] += 1
        return {"ok": True}

    monkeypatch.setattr(stage_service, "advance_application_stage", _fake_advance)

    flow, _execution = await _make(
        db_session,
        graph=_linear_graph("m", "move_candidate", {}),
        trigger_event={"application_id": str(uuid.uuid4())},
        owner_org_id=uuid.uuid4(),
    )

    out = await execution_service.dry_run_flow(
        db_session, flow=flow, sample_event={"application_id": str(uuid.uuid4())}
    )

    assert out["is_simulated"] is True
    assert called["n"] == 0  # no real stage move during a dry-run


@pytest.mark.asyncio
async def test_move_candidate_failure_creates_failed_node_task(db_session, monkeypatch) -> None:
    async def _boom(*args, **kwargs):
        raise RuntimeError("illegal transition / cross-org 404")

    monkeypatch.setattr(stage_service, "advance_application_stage", _boom)

    flow, execution = await _make(
        db_session,
        graph=_linear_graph("m", "move_candidate", {}),
        trigger_event={"application_id": str(uuid.uuid4())},
        owner_org_id=uuid.uuid4(),
    )

    await execution_service.execute_flow(db_session, execution_id=execution.id)

    refreshed = await db_session.get(WorkflowExecution, execution.id)
    assert refreshed.status == "FAILED"
    last = refreshed.node_logs[-1]
    assert last["node_id"] == "m"
    assert last["decision"] == "failed"
    # User-safe error only — no raw exception text / PII leaks.
    assert "illegal transition" not in last["error"]


@pytest.mark.asyncio
async def test_move_candidate_without_org_fails_safely(db_session, monkeypatch) -> None:
    async def _fake_advance(*args, **kwargs):
        raise AssertionError("must not be called when flow has no org")

    monkeypatch.setattr(stage_service, "advance_application_stage", _fake_advance)

    flow, execution = await _make(
        db_session,
        graph=_linear_graph("m", "move_candidate", {}),
        trigger_event={"application_id": str(uuid.uuid4())},
        owner_org_id=None,
    )

    await execution_service.execute_flow(db_session, execution_id=execution.id)

    refreshed = await db_session.get(WorkflowExecution, execution.id)
    assert refreshed.status == "FAILED"


# --------------------------------------------------------------------------- #
# send_notification dedupe                                                    #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_send_notification_uses_stable_dedupe_key(db_session, monkeypatch) -> None:
    captured: dict = {}

    async def _fake_enqueue(
        session, *, recipient_id, template_key, channel, locale, variables, dedupe_key
    ):
        captured["dedupe_key"] = dedupe_key
        captured["recipient_id"] = recipient_id

        class _Row:
            id = uuid.uuid4()

        return _Row()

    monkeypatch.setattr(execution_service, "enqueue_notification", _fake_enqueue)

    recipient = uuid.uuid4()
    flow, execution = await _make(
        db_session,
        graph=_linear_graph(
            "s",
            "send_notification",
            {"template_key": "welcome", "recipient_id": str(recipient)},
        ),
        trigger_event={},
        owner_org_id=uuid.uuid4(),
    )

    await execution_service.execute_flow(db_session, execution_id=execution.id)

    assert captured["dedupe_key"] == f"wf:{execution.id}:s"
    assert captured["recipient_id"] == recipient


# --------------------------------------------------------------------------- #
# webhook                                                                     #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_webhook_sends_redacted_payload(db_session, monkeypatch) -> None:
    captured: dict = {}

    async def _fake_post(url, payload, *, delivery_id, timeout=5.0, **kwargs):  # noqa: ASYNC109
        captured["url"] = url
        captured["payload"] = payload
        captured["delivery_id"] = delivery_id
        return 200

    monkeypatch.setattr(webhook_dispatch, "post_webhook", _fake_post)

    flow, execution = await _make(
        db_session,
        graph=_linear_graph(
            "w",
            "webhook",
            {"url": "https://hooks.partner.example/wf", "event_key": "partner.moved"},
        ),
        # PII in the trigger must NOT reach the external endpoint.
        trigger_event={"type": "t", "email": "secret@x.com"},
        owner_org_id=uuid.uuid4(),
    )

    await execution_service.execute_flow(db_session, execution_id=execution.id)

    refreshed = await db_session.get(WorkflowExecution, execution.id)
    assert refreshed.status == "COMPLETED"
    assert captured["delivery_id"] == f"wf:{execution.id}:w"
    # The whole outbound payload must not contain the raw PII value.
    assert "secret@x.com" not in str(captured["payload"])
    assert captured["payload"]["event"] == "partner.moved"


@pytest.mark.asyncio
async def test_webhook_dry_run_sends_nothing(db_session, monkeypatch) -> None:
    async def _fake_post(*args, **kwargs):
        raise AssertionError("dry-run must not call the network")

    monkeypatch.setattr(webhook_dispatch, "post_webhook", _fake_post)

    flow, _execution = await _make(
        db_session,
        graph=_linear_graph("w", "webhook", {"url": "https://hooks.partner.example/wf"}),
        trigger_event={"type": "t"},
        owner_org_id=uuid.uuid4(),
    )

    out = await execution_service.dry_run_flow(db_session, flow=flow, sample_event={"type": "t"})
    assert out["is_simulated"] is True
