"""Recruiting-automation workflow node tests (Wave 2B).

Covers the four new node types (``ai_screen_application`` / ``auto_advance_on_gate``
/ ``notify`` / ``jd_pdf_to_draft``) end-to-end through the real execution engine:

- happy path + branch routing, dry-run no-op, and per-node audit log;
- gate-respecting auto-advance (never bypasses ``gate_met``);
- trigger idempotency (a re-fired trigger never double-acts);
- human confirmation required for the consequential JD->draft node;
- RBAC on activation (a flow with an AI screen node needs the screen grant);
- metering for the AI node (LLM path invoked on real runs, skipped on dry-run).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from app.modules.documents.application import application_fit_service, snapshot_service
from app.modules.notifications.domain.models import NotificationOutbox
from app.modules.recruitment.application import (
    access,
    apply_service,
    automation_facade,
    cv_evaluation_service,
    decision_service,
)
from app.modules.recruitment.domain import pipeline
from app.modules.recruitment.domain.models import CandidateStage
from app.modules.workflow.application import (
    activation_service,
    execution_service,
    flow_service,
    trigger_service,
)
from app.modules.workflow.application.errors import MissingActivationCapabilitiesError
from app.modules.workflow.domain.models import (
    WorkflowExecution,
    WorkflowFlow,
    WorkflowNodeExecutionLog,
)
from sqlalchemy import func, select

from tests.auth_utils import CTX
from tests.documents_utils import make_student
from tests.org_utils import add_member, make_org_with_admin
from tests.recruitment_utils import apply_payload, make_builder_cv, publish_job


@pytest.fixture(autouse=True)
def _authorizer():
    access.install_authorizer()
    yield
    snapshot_service.set_snapshot_access_authorizer(None)


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #


async def _make_active_flow(db, *, org, admin, graph, trigger_type="system.application_submitted"):
    flow = WorkflowFlow(
        id=uuid.uuid4(),
        name="Recruiting automation",
        description=None,
        trigger_type=trigger_type,
        graph=graph,
        status="ACTIVE",
        version=1,
        created_by=admin.user_id,
        created_at=datetime.now(tz=UTC),
        owner_type="partner",
        owner_org_id=org.id,
    )
    db.add(flow)
    await db.flush()
    await db.commit()
    return flow


async def _run(db, *, flow, trigger_event, key="evt-1"):
    execution = WorkflowExecution(
        id=uuid.uuid4(),
        flow_id=flow.id,
        trigger_event=trigger_event,
        idempotency_key=key,
        status="RUNNING",
        started_at=datetime.now(tz=UTC),
        node_logs=[],
    )
    db.add(execution)
    await db.flush()
    await db.commit()
    await execution_service.execute_flow(db, execution_id=execution.id)
    return await db.get(WorkflowExecution, execution.id)


async def _node_logs(db, execution_id) -> list[WorkflowNodeExecutionLog]:
    return list(
        (
            await db.execute(
                select(WorkflowNodeExecutionLog)
                .where(WorkflowNodeExecutionLog.execution_id == execution_id)
                .order_by(WorkflowNodeExecutionLog.entered_at)
            )
        )
        .scalars()
        .all()
    )


def _screen_graph(*, mode="deterministic", hm_user_id):
    return {
        "nodes": [
            {
                "id": "t",
                "type": "trigger",
                "data": {"trigger_type": "system.application_submitted"},
            },
            {
                "id": "s",
                "type": "ai_screen_application",
                "data": {"mode": mode, "strong_threshold": 80, "consider_threshold": 50},
            },
            {
                "id": "n",
                "type": "notify",
                "data": {
                    "template_key": "partner.strong_candidate",
                    "recipient_mode": "user",
                    "recipient_user_id": str(hm_user_id),
                },
            },
            {"id": "e", "type": "end", "data": {}},
        ],
        "edges": [
            {"source": "t", "target": "s"},
            {"source": "s", "target": "n", "condition": "strong"},
            {"source": "n", "target": "e"},
        ],
    }


def _patch_screen(monkeypatch, *, org_id, score):
    async def _ref(session, *, application_id):
        return {
            "snapshot_id": uuid.uuid4(),
            "job_id": uuid.uuid4(),
            "org_id": org_id,
            "status": "submitted",
        }

    async def _signals(session, *, snapshot_id, job_id, locale="vi"):
        return {
            "score": score,
            "band": "Strong" if score >= 80 else "Weak",
            "band_key": "strong" if score >= 80 else "weak",
            "matched_skills": ["python", "fastapi"],
            "gaps": [] if score >= 80 else ["kubernetes"],
            "signal": "ok",
        }

    monkeypatch.setattr(automation_facade, "application_screening_ref", _ref)
    monkeypatch.setattr(application_fit_service, "application_snapshot_fit_signals", _signals)


# --------------------------------------------------------------------------- #
# ai_screen_application + notify (deterministic)                               #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_strong_screen_routes_to_notify_and_enqueues_outbox(db_session, monkeypatch) -> None:
    _u, org, admin = await make_org_with_admin(db_session)
    _patch_screen(monkeypatch, org_id=org.id, score=88)
    flow = await _make_active_flow(
        db_session, org=org, admin=admin, graph=_screen_graph(hm_user_id=admin.user_id)
    )

    execution = await _run(
        db_session, flow=flow, trigger_event={"application_id": str(uuid.uuid4())}
    )

    assert execution.status == "COMPLETED"
    visited = [log["node_id"] for log in execution.node_logs]
    assert visited == ["t", "s", "n", "e"]  # strong -> notify -> end

    # Node audit trail persisted for each node.
    logs = await _node_logs(db_session, execution.id)
    screen_log = next(log for log in logs if log.node_type == "ai_screen_application")
    assert screen_log.output_summary.get("screen_recommendation") == "strong"

    # notify really enqueued one outbox row (no synchronous SMTP).
    outbox = (
        (
            await db_session.execute(
                select(NotificationOutbox).where(
                    NotificationOutbox.template_key == "partner.strong_candidate"
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(outbox) == 1
    assert outbox[0].recipient_id == admin.user_id
    # Leak-safe payload only.
    assert "cv_text" not in outbox[0].variables


@pytest.mark.asyncio
async def test_weak_screen_holds_without_notifying(db_session, monkeypatch) -> None:
    _u, org, admin = await make_org_with_admin(db_session)
    _patch_screen(monkeypatch, org_id=org.id, score=42)
    flow = await _make_active_flow(
        db_session, org=org, admin=admin, graph=_screen_graph(hm_user_id=admin.user_id)
    )

    execution = await _run(
        db_session, flow=flow, trigger_event={"application_id": str(uuid.uuid4())}
    )

    assert execution.status == "COMPLETED"
    # No "strong" edge matched -> flow ends after screen (held), notify never runs.
    assert [log["node_id"] for log in execution.node_logs] == ["t", "s"]
    outbox_count = (
        await db_session.execute(
            select(func.count())
            .select_from(NotificationOutbox)
            .where(NotificationOutbox.template_key == "partner.strong_candidate")
        )
    ).scalar_one()
    assert outbox_count == 0


@pytest.mark.asyncio
async def test_screen_dry_run_is_no_op(db_session, monkeypatch) -> None:
    _u, org, admin = await make_org_with_admin(db_session)
    _patch_screen(monkeypatch, org_id=org.id, score=88)
    flow = await _make_active_flow(
        db_session, org=org, admin=admin, graph=_screen_graph(hm_user_id=admin.user_id)
    )

    result = await execution_service.dry_run_flow(
        db_session, flow=flow, sample_event={"application_id": str(uuid.uuid4())}
    )

    assert result["is_simulated"] is True
    steps = {s["node_id"]: s for s in result["steps"]}
    assert steps["s"]["decision"] == "strong"
    # notify simulated: NO real outbox row.
    outbox_count = (
        await db_session.execute(
            select(func.count())
            .select_from(NotificationOutbox)
            .where(NotificationOutbox.template_key == "partner.strong_candidate")
        )
    ).scalar_one()
    assert outbox_count == 0
    # Dry-run node logs are marked simulated (audit distinct from real runs).
    logs = await _node_logs(db_session, uuid.UUID(result["execution_id"]))
    assert logs and all(log.is_simulated for log in logs)


# --------------------------------------------------------------------------- #
# Metering: LLM mode invokes the metered evaluator, dry-run does not spend      #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_llm_screen_invokes_metered_evaluator(db_session, monkeypatch) -> None:
    _u, org, admin = await make_org_with_admin(db_session)
    _patch_screen(monkeypatch, org_id=org.id, score=70)
    calls: list[uuid.UUID] = []

    async def _fake_eval(session, *, principal, application_id, ctx, refresh=False, locale="vi"):
        calls.append(application_id)
        return {"recommendation": "strong", "match_score": 91, "is_fallback": False}

    monkeypatch.setattr(cv_evaluation_service, "evaluate_candidate_cv", _fake_eval)
    flow = await _make_active_flow(
        db_session,
        org=org,
        admin=admin,
        graph=_screen_graph(mode="llm", hm_user_id=admin.user_id),
    )

    execution = await _run(
        db_session, flow=flow, trigger_event={"application_id": str(uuid.uuid4())}
    )

    assert execution.status == "COMPLETED"
    assert len(calls) == 1  # metered path taken once
    assert [log["node_id"] for log in execution.node_logs] == ["t", "s", "n", "e"]


@pytest.mark.asyncio
async def test_llm_screen_dry_run_does_not_spend(db_session, monkeypatch) -> None:
    _u, org, admin = await make_org_with_admin(db_session)
    _patch_screen(monkeypatch, org_id=org.id, score=88)
    calls: list[uuid.UUID] = []

    async def _fake_eval(session, *, principal, application_id, ctx, refresh=False, locale="vi"):
        calls.append(application_id)
        return {"recommendation": "strong", "match_score": 91, "is_fallback": False}

    monkeypatch.setattr(cv_evaluation_service, "evaluate_candidate_cv", _fake_eval)
    flow = await _make_active_flow(
        db_session,
        org=org,
        admin=admin,
        graph=_screen_graph(mode="llm", hm_user_id=admin.user_id),
    )

    await execution_service.dry_run_flow(
        db_session, flow=flow, sample_event={"application_id": str(uuid.uuid4())}
    )

    assert calls == []  # dry-run never calls the metered model


# --------------------------------------------------------------------------- #
# auto_advance_on_gate: respects the gate (real path)                          #
# --------------------------------------------------------------------------- #


async def _apply_and_review(db, *, partner, uni, job_id):
    su, student = await make_student(db, prefix="cand")
    sel = await make_builder_cv(db, student=student)
    app = await apply_service.apply_to_job(
        db, principal=student, payload=apply_payload(job_id=job_id, cv_selection=sel), ctx=CTX
    )
    app_id = uuid.UUID(app["id"])
    await decision_service.review_application(db, principal=partner, application_id=app_id, ctx=CTX)
    return app_id


async def _active_stage(db, app_id) -> CandidateStage | None:
    return (
        (
            await db.execute(
                select(CandidateStage).where(
                    CandidateStage.application_id == app_id,
                    CandidateStage.status == pipeline.STAGE_ACTIVE,
                )
            )
        )
        .scalars()
        .first()
    )


@pytest.mark.asyncio
async def test_auto_advance_facade_advances_when_gate_met(db_session) -> None:
    _pu, porg, partner = await make_org_with_admin(db_session, display_name="Partner Co")
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await publish_job(db_session, partner_principal=partner, uni_principal=uni)
    app_id = await _apply_and_review(db_session, partner=partner, uni=uni, job_id=job_id)

    before = await _active_stage(db_session, app_id)
    assert before is not None  # stage-1 (manual gate, trivially met)

    result = await automation_facade.auto_advance_if_gate_met(
        db_session, principal=partner, application_id=app_id, ctx=CTX, idempotency_key="wf-adv-1"
    )

    assert result["advanced"] is True
    after = await _active_stage(db_session, app_id)
    assert after is not None and after.stage_id != before.stage_id  # moved to next stage


@pytest.mark.asyncio
async def test_auto_advance_facade_holds_when_not_applicable(db_session) -> None:
    """A submitted (not under_review) application is never force-advanced."""

    _pu, porg, partner = await make_org_with_admin(db_session, display_name="Partner Co")
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await publish_job(db_session, partner_principal=partner, uni_principal=uni)
    su, student = await make_student(db_session, prefix="cand2")
    sel = await make_builder_cv(db_session, student=student)
    app = await apply_service.apply_to_job(
        db_session,
        principal=student,
        payload=apply_payload(job_id=job_id, cv_selection=sel),
        ctx=CTX,
    )
    app_id = uuid.UUID(app["id"])  # status = submitted, NOT reviewed

    result = await automation_facade.auto_advance_if_gate_met(
        db_session, principal=partner, application_id=app_id, ctx=CTX, idempotency_key="wf-adv-2"
    )

    assert result == {"advanced": False, "reason": "not_applicable"}
    # No stage rows materialized by a refused auto-advance.
    count = (
        await db_session.execute(
            select(func.count())
            .select_from(CandidateStage)
            .where(CandidateStage.application_id == app_id)
        )
    ).scalar_one()
    assert count == 0


@pytest.mark.asyncio
async def test_auto_advance_node_holds_on_gate_not_met(db_session, monkeypatch) -> None:
    _u, org, admin = await make_org_with_admin(db_session)

    async def _held(session, *, principal, application_id, ctx, idempotency_key, locale="vi"):
        return {"advanced": False, "reason": "gate_not_met"}

    monkeypatch.setattr(automation_facade, "auto_advance_if_gate_met", _held)
    graph = {
        "nodes": [
            {"id": "t", "type": "trigger", "data": {"trigger_type": "system.stage_changed"}},
            {"id": "a", "type": "auto_advance_on_gate", "data": {}},
            {
                "id": "n",
                "type": "notify",
                "data": {
                    "template_key": "x",
                    "recipient_mode": "user",
                    "recipient_user_id": str(admin.user_id),
                },
            },
            {"id": "e", "type": "end", "data": {}},
        ],
        "edges": [
            {"source": "t", "target": "a"},
            {"source": "a", "target": "n", "condition": "advanced"},
            {"source": "n", "target": "e"},
        ],
    }
    flow = await _make_active_flow(
        db_session, org=org, admin=admin, graph=graph, trigger_type="system.stage_changed"
    )

    execution = await _run(
        db_session, flow=flow, trigger_event={"application_id": str(uuid.uuid4())}
    )

    assert execution.status == "COMPLETED"
    # gate_not_met -> no "advanced" edge match -> flow ends, notify never runs.
    assert [log["node_id"] for log in execution.node_logs] == ["t", "a"]


# --------------------------------------------------------------------------- #
# jd_pdf_to_draft: human confirm required (never auto-creates a job)           #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_jd_pdf_to_draft_pauses_for_human_confirm(db_session) -> None:
    _u, org, admin = await make_org_with_admin(db_session)
    graph = {
        "nodes": [
            {"id": "t", "type": "trigger", "data": {"trigger_type": "system.file_uploaded"}},
            {"id": "d", "type": "jd_pdf_to_draft", "data": {}},
            {"id": "e", "type": "end", "data": {}},
        ],
        "edges": [{"source": "t", "target": "d"}, {"source": "d", "target": "e"}],
    }
    flow = await _make_active_flow(
        db_session, org=org, admin=admin, graph=graph, trigger_type="system.file_uploaded"
    )

    execution = await _run(
        db_session,
        flow=flow,
        trigger_event={"jd_fields": {"title": "Backend Engineer", "required_skills": ["python"]}},
    )

    # Paused for human confirm-create: never auto-published, never reached end.
    assert execution.status == "RUNNING"
    assert execution.node_logs[-1]["node_id"] == "d"
    assert execution.node_logs[-1]["decision"] == "awaiting_human_review"
    logs = await _node_logs(db_session, execution.id)
    draft_log = next(log for log in logs if log.node_type == "jd_pdf_to_draft")
    assert draft_log.status == "skipped"
    assert draft_log.output_summary.get("job_draft_proposal", {}).get("title") == "Backend Engineer"


# --------------------------------------------------------------------------- #
# RBAC on activation                                                           #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_activation_requires_screen_capability(db_session) -> None:
    _u, org, admin = await make_org_with_admin(db_session)
    graph = _screen_graph(hm_user_id=admin.user_id)
    draft = await flow_service.create_draft_flow(
        db_session,
        principal=admin,
        name="Screen flow",
        description=None,
        trigger_type="system.application_submitted",
        graph=graph,
        ctx=CTX,
    )

    # A member WITHOUT ai_recruiting:screen_candidate cannot activate the flow.
    _mu, _mem, limited = await add_member(
        db_session,
        org=org,
        permissions=[("workflow", "activate"), ("workflow", "read"), ("notifications", "send")],
    )
    with pytest.raises(MissingActivationCapabilitiesError) as exc:
        await activation_service.activate_flow(
            db_session, principal=limited, flow_id=draft.id, ctx=CTX
        )
    assert "ai_recruiting:screen_candidate" in exc.value.details["missing_capabilities"]

    # The admin (wildcard grants) can.
    activated = await activation_service.activate_flow(
        db_session, principal=admin, flow_id=draft.id, ctx=CTX
    )
    assert activated.status == "ACTIVE"


# --------------------------------------------------------------------------- #
# Trigger wiring + idempotency                                                 #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_application_submitted_trigger_fires_scoped_flow(db_session) -> None:
    _pu, porg, partner = await make_org_with_admin(db_session, display_name="Partner Co")
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    # Another partner with its OWN flow that must NOT fire for the first partner's app.
    _ou, oorg, other = await make_org_with_admin(db_session, display_name="Other Co")

    graph = {
        "nodes": [
            {
                "id": "t",
                "type": "trigger",
                "data": {"trigger_type": "system.application_submitted"},
            },
            {"id": "e", "type": "end", "data": {}},
        ],
        "edges": [{"source": "t", "target": "e"}],
    }
    my_flow = await _make_active_flow(db_session, org=porg, admin=partner, graph=graph)
    other_flow = await _make_active_flow(db_session, org=oorg, admin=other, graph=graph)

    job_id = await publish_job(db_session, partner_principal=partner, uni_principal=uni)
    su, student = await make_student(db_session, prefix="cand3")
    sel = await make_builder_cv(db_session, student=student)
    await apply_service.apply_to_job(
        db_session,
        principal=student,
        payload=apply_payload(job_id=job_id, cv_selection=sel),
        ctx=CTX,
    )

    my_execs = (
        await db_session.execute(
            select(func.count())
            .select_from(WorkflowExecution)
            .where(WorkflowExecution.flow_id == my_flow.id)
        )
    ).scalar_one()
    other_execs = (
        await db_session.execute(
            select(func.count())
            .select_from(WorkflowExecution)
            .where(WorkflowExecution.flow_id == other_flow.id)
        )
    ).scalar_one()
    assert my_execs == 1  # the owning org's flow fired
    assert other_execs == 0  # tenant scoping: the other org's flow did not


@pytest.mark.asyncio
async def test_trigger_is_idempotent_no_double_action(db_session) -> None:
    _u, org, admin = await make_org_with_admin(db_session)
    graph = {
        "nodes": [
            {
                "id": "t",
                "type": "trigger",
                "data": {"trigger_type": "system.application_submitted"},
            },
            {
                "id": "n",
                "type": "notify",
                "data": {
                    "template_key": "dup.check",
                    "recipient_mode": "user",
                    "recipient_user_id": str(admin.user_id),
                },
            },
            {"id": "e", "type": "end", "data": {}},
        ],
        "edges": [{"source": "t", "target": "n"}, {"source": "n", "target": "e"}],
    }
    flow = await _make_active_flow(db_session, org=org, admin=admin, graph=graph)

    payload = {"application_id": str(uuid.uuid4())}
    key = f"application_submitted:{uuid.uuid4()}"
    await trigger_service.dispatch_trigger(
        db_session,
        trigger_type="system.application_submitted",
        payload=payload,
        idempotency_key=key,
        scope_org_id=org.id,
    )
    await trigger_service.dispatch_trigger(
        db_session,
        trigger_type="system.application_submitted",
        payload=payload,
        idempotency_key=key,
        scope_org_id=org.id,
    )

    exec_count = (
        await db_session.execute(
            select(func.count())
            .select_from(WorkflowExecution)
            .where(WorkflowExecution.flow_id == flow.id)
        )
    ).scalar_one()
    outbox_count = (
        await db_session.execute(
            select(func.count())
            .select_from(NotificationOutbox)
            .where(NotificationOutbox.template_key == "dup.check")
        )
    ).scalar_one()
    assert exec_count == 1  # duplicate trigger reused the same execution
    assert outbox_count == 1  # notify acted exactly once
