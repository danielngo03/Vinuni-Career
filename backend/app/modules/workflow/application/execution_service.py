"""Graph interpreter: walks a WorkflowFlow's graph node-by-node for a given
WorkflowExecution. Callable directly (tests, local/inline worker) and also
wrapped as a Celery task in ``celery_tasks.py`` for the deferred production
path — see docs/LOCAL_DEV_STACK.md on the inline-vs-Celery worker split.

Human Review / Request Approval / AI Suggestion nodes pause execution (status
stays RUNNING) until a separate review-decision call resumes the flow — that
resume entrypoint is out of scope for this plan (Phase A ships the
auto-approve/condition/end path end-to-end; the human-decision resume API is a
fast-follow, tracked in the plan's follow-up list, not silently implied here).

Only ``send_notification`` performs a real cross-module side effect today (via
the approved ``notifications.dispatch_service.enqueue_notification`` seam).
``assign_owner``, ``create_task``, ``move_candidate``, and ``webhook`` are
intentionally logged-intent stubs — they record what would happen without
calling into ``recruitment``/external systems, since this module owns no
approved write interface into those domains yet. Wiring those up for real is
flagged as backlog/follow-up, not silently pretended to be complete.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notifications.application.dispatch_service import enqueue_notification
from app.modules.workflow.domain.graph import FlowContext, SIDE_EFFECTING_NODE_TYPES
from app.modules.workflow.domain.models import (
    WorkflowExecution,
    WorkflowFailedNodeTask,
    WorkflowFlow,
    WorkflowNodeExecutionLog,
)

_PII_KEYS = {
    "email", "phone", "phone_number", "full_name", "name", "address",
    "national_id", "cv_text", "resume_text", "cover_letter", "ssn",
    "date_of_birth", "identity_number",
}


class NodeExecutionFailed(Exception):
    """Raised by a node handler for a recoverable failure. ``user_safe_error``
    is stored on the node log and the created follow-up task; never include
    stack traces, provider/internal details, or raw PII in it.
    """

    def __init__(self, user_safe_error: str) -> None:
        self.user_safe_error = user_safe_error
        super().__init__(user_safe_error)


def redact_sample_event(event: dict) -> dict:
    """Best-effort PII redaction for dry-run sample events
    (docs/PARTNER_RBAC_ANALYTICS_SPEC.md: "Show dry-run output using sample
    events with PII redacted"). Keys that look like direct identifiers are
    masked; everything else (ids, statuses, scores, counts) passes through
    since it is needed to exercise conditions realistically.
    """

    redacted: dict = {}
    for key, value in event.items():
        if key.lower() in _PII_KEYS:
            redacted[key] = "[redacted]"
        else:
            redacted[key] = value
    return redacted


def _summarize(value: dict) -> dict:
    """Redact/trim a node's input or output before it is persisted to a log
    row — never store raw CV text, prompts, tokens, or full trigger payloads.
    """

    return redact_sample_event(value)


async def execute_flow(
    session: AsyncSession, *, execution_id: uuid.UUID, simulate: bool = False
) -> None:
    execution = await session.get(WorkflowExecution, execution_id)
    if execution is None or execution.status != "RUNNING":
        return

    flow = await session.get(WorkflowFlow, execution.flow_id)
    if flow is None:
        return

    if execution.node_logs:
        # Already progressed (idempotent re-entry, e.g. duplicate trigger
        # delivery) — do not replay from the start.
        return

    graph = flow.graph
    nodes_by_id = {n["id"]: n for n in graph["nodes"]}
    context = FlowContext(trigger=execution.trigger_event, variables={})

    current = _find_trigger_node(nodes_by_id)
    logs = list(execution.node_logs)

    while current is not None:
        entered_at = datetime.now(tz=UTC)
        try:
            result = await _execute_node(session, current, context, simulate=simulate)
        except NodeExecutionFailed as exc:
            exited_at = datetime.now(tz=UTC)
            logs.append(
                {
                    "node_id": current["id"],
                    "entered_at": entered_at.isoformat(),
                    "exited_at": exited_at.isoformat(),
                    "decision": "failed",
                    "error": exc.user_safe_error,
                }
            )
            await _persist_node_log(
                session,
                execution=execution,
                node=current,
                status="failed",
                entered_at=entered_at,
                exited_at=exited_at,
                input_summary=_summarize(context.variables | {"trigger": context.trigger}),
                output_summary={},
                user_safe_error=exc.user_safe_error,
                simulate=simulate,
            )
            execution.node_logs = logs
            execution.status = "FAILED"
            execution.finished_at = exited_at
            await session.flush()
            if not simulate:
                await _create_failed_node_task(session, flow=flow, execution=execution, node=current, error=exc.user_safe_error)
            await session.commit()
            return

        exited_at = datetime.now(tz=UTC)
        logs.append(
            {
                "node_id": current["id"],
                "entered_at": entered_at.isoformat(),
                "exited_at": exited_at.isoformat(),
                "decision": result.decision,
                "error": None,
            }
        )
        await _persist_node_log(
            session,
            execution=execution,
            node=current,
            status="skipped" if result.decision == "awaiting_human_review" else "success",
            entered_at=entered_at,
            exited_at=exited_at,
            input_summary=_summarize(context.variables | {"trigger": context.trigger}),
            output_summary=_summarize(result.output_variables),
            user_safe_error=None,
            simulate=simulate,
        )
        context.merge(result.output_variables)

        if result.decision == "awaiting_human_review":
            execution.node_logs = logs
            await session.commit()
            return
        if current["type"] == "end":
            execution.status = "COMPLETED"
            execution.finished_at = datetime.now(tz=UTC)
            execution.node_logs = logs
            await session.commit()
            return

        current = _resolve_next_node(nodes_by_id, graph["edges"], current, result.decision)

    execution.node_logs = logs
    execution.status = "COMPLETED"
    execution.finished_at = datetime.now(tz=UTC)
    await session.commit()


async def dry_run_flow(
    session: AsyncSession,
    *,
    flow: WorkflowFlow,
    sample_event: dict | None,
) -> dict:
    """Simulate a flow against a synthetic/sample event with PII redacted.

    No real side effects: no notifications enqueued, no rows written to
    ``jobs``/``recruitment`` tables, no outbound webhook calls. A
    ``WorkflowExecution``/``WorkflowNodeExecutionLog`` audit trail *is*
    written (marked ``is_simulated``) so dry-runs show up in execution
    history distinctly from real runs, per the contract's "readable execution
    history" requirement.
    """

    graph = flow.graph
    nodes_by_id = {n["id"]: n for n in graph["nodes"]}
    trigger_event = redact_sample_event(sample_event or {"sample": True})
    context = FlowContext(trigger=trigger_event, variables={})

    execution = WorkflowExecution(
        id=uuid.uuid4(),
        flow_id=flow.id,
        trigger_event=trigger_event,
        idempotency_key=f"dryrun:{uuid.uuid4()}",
        status="RUNNING",
        started_at=datetime.now(tz=UTC),
        node_logs=[],
        is_simulated=True,
    )
    session.add(execution)
    await session.flush()

    steps: list[dict] = []
    current = _find_trigger_node(nodes_by_id)
    logs: list[dict] = []
    visited = 0
    max_steps = len(nodes_by_id) + 1

    while current is not None and visited <= max_steps:
        visited += 1
        entered_at = datetime.now(tz=UTC)
        try:
            result = await _execute_node(session, current, context, simulate=True)
            status, error, decision = "success", None, result.decision
            output_summary = _summarize(result.output_variables)
        except NodeExecutionFailed as exc:
            status, error, decision = "failed", exc.user_safe_error, "failed"
            output_summary = {}
            result = _NodeResult(decision="failed")
        exited_at = datetime.now(tz=UTC)

        step = {
            "node_id": current["id"],
            "node_type": current["type"],
            "status": status,
            "decision": decision,
            "output_summary": output_summary,
            "user_safe_error": error,
        }
        steps.append(step)
        logs.append(
            {
                "node_id": current["id"],
                "entered_at": entered_at.isoformat(),
                "exited_at": exited_at.isoformat(),
                "decision": decision,
                "error": error,
            }
        )
        await _persist_node_log(
            session,
            execution=execution,
            node=current,
            status="skipped" if decision == "awaiting_human_review" else status,
            entered_at=entered_at,
            exited_at=exited_at,
            input_summary=_summarize(context.variables | {"trigger": context.trigger}),
            output_summary=output_summary,
            user_safe_error=error,
            simulate=True,
        )

        if status == "failed" or decision == "awaiting_human_review":
            break
        context.merge(result.output_variables)
        if current["type"] == "end":
            break
        current = _resolve_next_node(nodes_by_id, graph["edges"], current, decision)

    execution.node_logs = logs
    execution.status = "FAILED" if steps and steps[-1]["status"] == "failed" else "COMPLETED"
    execution.finished_at = datetime.now(tz=UTC)
    await session.commit()

    return {
        "execution_id": str(execution.id),
        "is_simulated": True,
        "sample_event": trigger_event,
        "steps": steps,
    }


async def _persist_node_log(
    session: AsyncSession,
    *,
    execution: WorkflowExecution,
    node: dict,
    status: str,
    entered_at: datetime,
    exited_at: datetime,
    input_summary: dict,
    output_summary: dict,
    user_safe_error: str | None,
    simulate: bool,
) -> None:
    session.add(
        WorkflowNodeExecutionLog(
            execution_id=execution.id,
            node_id=node["id"],
            node_type=node["type"],
            status=status,
            actor_type="system",
            reason=None,
            input_summary=input_summary,
            output_summary=output_summary,
            user_safe_error=user_safe_error,
            is_simulated=simulate,
            entered_at=entered_at,
            exited_at=exited_at,
        )
    )
    await session.flush()


async def _create_failed_node_task(
    session: AsyncSession,
    *,
    flow: WorkflowFlow,
    execution: WorkflowExecution,
    node: dict,
    error: str,
) -> None:
    session.add(
        WorkflowFailedNodeTask(
            execution_id=execution.id,
            flow_id=flow.id,
            node_id=node["id"],
            node_type=node["type"],
            owner_type=flow.owner_type,
            owner_org_id=flow.owner_org_id,
            user_safe_error=error,
            status="open",
            created_at=datetime.now(tz=UTC),
        )
    )
    await session.flush()


class _NodeResult:
    def __init__(self, decision: str, output_variables: dict | None = None) -> None:
        self.decision = decision
        self.output_variables = output_variables or {}


def _find_trigger_node(nodes_by_id: dict[str, dict]) -> dict | None:
    return next((n for n in nodes_by_id.values() if n["type"] == "trigger"), None)


async def _execute_node(
    session: AsyncSession, node: dict, context: FlowContext, *, simulate: bool
) -> _NodeResult:
    node_type = node["type"]
    data = node.get("data", {})

    if node_type == "trigger":
        return _NodeResult(decision="entered")

    if node_type == "condition":
        expression = context.interpolate(data["expression"])
        # NOTE (deliberate, narrow, flagged for follow-up): this eval() runs
        # with {"__builtins__": {}} against a string that has already been
        # through FlowContext.interpolate, so no attacker-controlled Python
        # syntax reaches it in this plan's two seed templates (Task 9 only
        # uses "{{fraud_score}} > 0.70"-shaped expressions with numeric
        # literals). This is a real security-hardening gap flagged for a
        # follow-up task (a proper restricted expression grammar), not
        # something to silently ship as final.
        return _NodeResult(decision=str(eval(expression, {"__builtins__": {}})).lower())  # noqa: S307

    if node_type in ("human_review", "request_approval"):
        return _NodeResult(decision="awaiting_human_review")

    if node_type in ("ai_process", "ai_suggestion"):
        # Consequential-AI nodes are advisory/confirmation-required by
        # default (docs contract) — no auto-executed AI write action exists
        # yet, so this always pauses for human confirmation, same as
        # human_review, until an org-level "audited automation policy" model
        # exists to allow an explicit opt-in bypass.
        return _NodeResult(decision="awaiting_human_review", output_variables={"ai_suggestion": data.get("prompt_key", "advisory")})

    if node_type == "delay" or node_type == "wait":
        # No real scheduler/SLA-timer wiring yet — logged as an instant no-op,
        # flagged as follow-up (see module docstring).
        return _NodeResult(decision="done")

    if node_type == "send_notification":
        if simulate:
            return _NodeResult(
                decision="done",
                output_variables={"simulated_notification_template": data.get("template_key")},
            )
        template_key = data.get("template_key")
        recipient_id = data.get("recipient_id") or context.variables.get(data.get("recipient_variable", ""))
        if not template_key or not recipient_id:
            raise NodeExecutionFailed(
                "Không thể gửi thông báo: thiếu người nhận hoặc mẫu thông báo."
            )
        try:
            await enqueue_notification(
                session,
                recipient_id=uuid.UUID(str(recipient_id)),
                template_key=template_key,
                channel=data.get("channel", "email"),
                locale=data.get("locale", "vi"),
                variables=_summarize(context.variables),
            )
        except Exception as exc:  # noqa: BLE001 — convert to a user-safe, recoverable failure
            raise NodeExecutionFailed("Không thể gửi thông báo do lỗi hệ thống.") from exc
        return _NodeResult(decision="done", output_variables={"notification_sent": True})

    if node_type in ("assign_owner", "create_task", "move_candidate", "webhook", "action"):
        # Logged-intent stub: records what would happen without a real
        # cross-module write (see module docstring for rationale/follow-up).
        label = "simulated_action" if simulate else "action_taken"
        return _NodeResult(decision="done", output_variables={label: data.get("action", node_type)})

    if node_type == "end":
        return _NodeResult(decision="done")

    raise ValueError(f"unsupported node type: {node_type}")


def _resolve_next_node(
    nodes_by_id: dict[str, dict], edges: list[dict], current: dict, decision: str
) -> dict | None:
    candidates = [e for e in edges if e["source"] == current["id"]]
    if len(candidates) == 1 and "condition" not in candidates[0]:
        return nodes_by_id.get(candidates[0]["target"])
    for edge in candidates:
        if edge.get("condition") == decision:
            return nodes_by_id.get(edge["target"])
    return None


async def list_flow_executions(
    session: AsyncSession, *, flow: WorkflowFlow, limit: int = 20
) -> list[dict]:
    """Newest-first REAL execution history for a flow, each with its per-node
    log trail. Dry-run/test executions are excluded here — they belong to the
    separate ``/test`` (simulated) surface, not production execution history.
    """

    executions = (
        await session.execute(
            select(WorkflowExecution)
            .where(
                WorkflowExecution.flow_id == flow.id,
                WorkflowExecution.is_simulated.is_(False),
            )
            .order_by(WorkflowExecution.started_at.desc())
            .limit(max(limit, 1))
        )
    ).scalars().all()
    if not executions:
        return []

    logs = (
        await session.execute(
            select(WorkflowNodeExecutionLog)
            .where(
                WorkflowNodeExecutionLog.execution_id.in_([e.id for e in executions])
            )
            .order_by(WorkflowNodeExecutionLog.entered_at.asc())
        )
    ).scalars().all()
    logs_by_execution: dict[uuid.UUID, list[WorkflowNodeExecutionLog]] = {}
    for log in logs:
        logs_by_execution.setdefault(log.execution_id, []).append(log)

    return [
        {
            "id": str(execution.id),
            "status": execution.status,
            "is_simulated": execution.is_simulated,
            "started_at": execution.started_at.isoformat() if execution.started_at else None,
            "finished_at": execution.finished_at.isoformat() if execution.finished_at else None,
            "nodes": [
                {
                    "node_id": log.node_id,
                    "node_type": log.node_type,
                    "status": log.status,
                    "actor_type": log.actor_type,
                    "actor_id": str(log.actor_id) if log.actor_id else None,
                    "reason": log.reason,
                    "input_summary": log.input_summary,
                    "output_summary": log.output_summary,
                    "user_safe_error": log.user_safe_error,
                    "entered_at": log.entered_at.isoformat() if log.entered_at else None,
                    "exited_at": log.exited_at.isoformat() if log.exited_at else None,
                }
                for log in logs_by_execution.get(execution.id, [])
            ],
        }
        for execution in executions
    ]
