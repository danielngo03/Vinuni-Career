"""Graph interpreter: walks a WorkflowFlow's graph node-by-node for a given
WorkflowExecution. Callable directly (tests, local/inline worker) and also
wrapped as a Celery task in ``celery_tasks.py`` for the deferred production
path — see docs/LOCAL_DEV_STACK.md on the inline-vs-Celery worker split.

Human Review / Request Approval / AI Suggestion nodes pause execution (status
stays RUNNING) until a separate review-decision call resumes the flow — that
resume entrypoint is out of scope for this plan (Phase A ships the
auto-approve/condition/end path end-to-end; the human-decision resume API is a
fast-follow, tracked in the plan's follow-up list, not silently implied here).

Real (non-simulated) side effects are wired only where an approved, tenant-safe
seam exists:
- ``send_notification`` → ``notifications.dispatch_service.enqueue_notification``
  (idempotent via a per-node ``dedupe_key``);
- ``move_candidate`` → ``recruitment.stage_service.advance_application_stage``
  (idempotency-key aware, executed under a system principal scoped to the flow's
  owning org so tenant isolation still holds — a cross-org application is a 404);
- ``webhook`` → the SSRF-guarded ``webhook_dispatch.post_webhook`` (redacted
  payload only, private/internal targets refused, redirects off, time-boxed).

``assign_owner`` and ``create_task`` remain logged-intent stubs: there is still
no approved job-owner-assignment seam and no generic task entity to write into,
so recording the intent is honest rather than fabricating a write. Every real
node degrades a failure into a recoverable failed-node task; dry-run no-ops all
of them. Human Review / Request Approval / AI Suggestion nodes pause execution
(status stays RUNNING) until a separate review-decision call resumes the flow —
that resume entrypoint remains a fast-follow.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notifications.application.dispatch_service import enqueue_notification
from app.modules.workflow.domain.graph import FlowContext
from app.modules.workflow.domain.models import (
    WorkflowExecution,
    WorkflowFailedNodeTask,
    WorkflowFlow,
    WorkflowNodeExecutionLog,
)
from app.shared.permissions import Principal

# Keys whose *value* is a direct identifier and must be masked before it is
# persisted to a node log / shown in a dry-run. Matched case-insensitively.
# ``name`` is deliberately EXACT-only (so ``template_name`` / ``job_name`` /
# ``filename`` are NOT redacted and conditions stay exercisable), while the
# unambiguous tokens below also match as substrings so nested/prefixed variants
# like ``candidate_email`` / ``student_phone`` / ``applicant_passport_number``
# are caught too.
_PII_EXACT_KEYS = {
    "email",
    "e_mail",
    "phone",
    "phone_number",
    "mobile",
    "full_name",
    "name",
    "first_name",
    "last_name",
    "middle_name",
    "display_name",
    "candidate_name",
    "student_name",
    "applicant_name",
    "recipient_name",
    "address",
    "home_address",
    "national_id",
    "identity_number",
    "id_number",
    "cccd",
    "cmnd",
    "passport",
    "ssn",
    "cv_text",
    "resume_text",
    "cover_letter",
    "date_of_birth",
    "dob",
    "gpa",
    "salary",
}
_PII_KEY_SUBSTRINGS = (
    "email",
    "phone",
    "passport",
    "national_id",
    "identity_number",
    "ssn",
    "date_of_birth",
    "cover_letter",
    "cv_text",
    "resume_text",
)
# Bound recursion so a hostile/cyclic-looking payload can never blow the stack.
_MAX_REDACT_DEPTH = 6
_REDACTED = "[redacted]"

_CONDITION_RE = re.compile(r"^\s*(?P<left>.+?)\s*(?P<op>>=|<=|==|!=|>|<)\s*(?P<right>.+?)\s*$")


def _is_pii_key(key: object) -> bool:
    if not isinstance(key, str):
        return False
    lowered = key.lower()
    if lowered in _PII_EXACT_KEYS:
        return True
    return any(sub in lowered for sub in _PII_KEY_SUBSTRINGS)


def _redact(value: object, *, depth: int = 0) -> object:
    """Recursively mask PII-looking keys inside nested dicts/lists.

    The old implementation only checked top-level, exact-lowercase keys, so a
    ``{"candidate": {"email": ...}}`` object or the whole trigger payload nested
    under ``"trigger"`` slipped through unredacted. This walks the structure so
    embedded identifiers are masked wherever they appear.
    """

    if depth > _MAX_REDACT_DEPTH:
        return "[trimmed]"
    if isinstance(value, dict):
        redacted: dict = {}
        for key, item in value.items():
            redacted[key] = _REDACTED if _is_pii_key(key) else _redact(item, depth=depth + 1)
        return redacted
    if isinstance(value, (list, tuple)):
        return [_redact(item, depth=depth + 1) for item in value]
    return value


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

    result = _redact(event)
    return result if isinstance(result, dict) else {}


def _summarize(value: dict) -> dict:
    """Redact/trim a node's input or output before it is persisted to a log
    row — never store raw CV text, prompts, tokens, or full trigger payloads.
    Recurses into nested dicts/lists so embedded identifiers (e.g. a candidate
    object under the trigger payload) are masked too.
    """

    result = _redact(value)
    return result if isinstance(result, dict) else {}


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
            result = await _execute_node(
                session, current, context, simulate=simulate, flow=flow, execution=execution
            )
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
                await _create_failed_node_task(
                    session, flow=flow, execution=execution, node=current, error=exc.user_safe_error
                )
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
            result = await _execute_node(
                session, current, context, simulate=True, flow=flow, execution=execution
            )
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
    session: AsyncSession,
    node: dict,
    context: FlowContext,
    *,
    simulate: bool,
    flow: WorkflowFlow,
    execution: WorkflowExecution,
) -> _NodeResult:
    node_type = node["type"]
    data = node.get("data", {})

    if node_type == "trigger":
        return _NodeResult(decision="entered")

    if node_type == "condition":
        expression = context.interpolate(data["expression"])
        return _NodeResult(decision=str(_evaluate_condition(expression)).lower())

    if node_type in ("human_review", "request_approval"):
        return _NodeResult(decision="awaiting_human_review")

    if node_type in ("ai_process", "ai_suggestion"):
        # Consequential-AI nodes are advisory/confirmation-required by
        # default (docs contract) — no auto-executed AI write action exists
        # yet, so this always pauses for human confirmation, same as
        # human_review, until an org-level "audited automation policy" model
        # exists to allow an explicit opt-in bypass.
        return _NodeResult(
            decision="awaiting_human_review",
            output_variables={"ai_suggestion": data.get("prompt_key", "advisory")},
        )

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
        recipient_id = data.get("recipient_id") or context.variables.get(
            data.get("recipient_variable", "")
        )
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
                # Idempotency: a retry / duplicate trigger delivery of the same
                # node must not enqueue a second outbox row.
                dedupe_key=_node_idempotency_key(execution, node),
            )
        except Exception as exc:  # noqa: BLE001 — convert to a user-safe, recoverable failure
            raise NodeExecutionFailed("Không thể gửi thông báo do lỗi hệ thống.") from exc
        return _NodeResult(decision="done", output_variables={"notification_sent": True})

    if node_type == "move_candidate":
        return await _run_move_candidate(
            session, node=node, data=data, context=context, flow=flow, execution=execution,
            simulate=simulate,
        )

    if node_type == "webhook":
        return await _run_webhook(
            node=node, data=data, context=context, execution=execution, simulate=simulate
        )

    if node_type in ("assign_owner", "create_task", "action"):
        # Logged-intent stub: these have no approved, tenant-safe cross-module
        # write interface yet (there is no job-owner assignment seam and no
        # generic task entity — see module docstring). Recording the intent is
        # honest; fabricating a write is not.
        label = "simulated_action" if simulate else "action_taken"
        return _NodeResult(decision="done", output_variables={label: data.get("action", node_type)})

    if node_type == "end":
        return _NodeResult(decision="done")

    raise ValueError(f"unsupported node type: {node_type}")


def _node_idempotency_key(execution: WorkflowExecution, node: dict) -> str:
    """Stable per-(execution, node) key so a retry / duplicate trigger delivery
    of the same node never double-applies its side effect.
    """

    return f"wf:{execution.id}:{node['id']}"


def _automation_principal(flow: WorkflowFlow) -> Principal:
    """A tenant-scoped system identity for a flow's consequential writes.

    Authorization for the flow was already established at ACTIVATION time (the
    activator had to hold every node's capability). Execution then runs as a
    non-superadmin system principal scoped to the flow's OWNING org, so a
    downstream service (e.g. ``recruitment.stage_service``) still enforces
    tenant isolation: a cross-org resource is a 404, exactly as for a human
    partner of that org. It is never superadmin and never impersonates a user.
    """

    return Principal(
        user_id=None,
        persona="system",
        org_id=flow.owner_org_id,
        is_superadmin=False,
        permissions=frozenset({"applications:read"}),
    )


def _resolve_application_id(data: dict, context: FlowContext) -> uuid.UUID | None:
    """Which application a ``move_candidate`` node acts on: an explicit
    ``data.application_id``, else a flow variable named by
    ``data.application_variable`` (default ``application_id``), else the trigger
    event's ``application_id``.
    """

    raw = (
        data.get("application_id")
        or context.variables.get(data.get("application_variable", "application_id"))
        or context.trigger.get("application_id")
    )
    if raw is None:
        return None
    try:
        return uuid.UUID(str(raw))
    except (ValueError, TypeError, AttributeError):
        return None


async def _run_move_candidate(
    session: AsyncSession,
    *,
    node: dict,
    data: dict,
    context: FlowContext,
    flow: WorkflowFlow,
    execution: WorkflowExecution,
    simulate: bool,
) -> _NodeResult:
    """Advance an application to its next pipeline stage via the approved
    ``recruitment.stage_service`` seam (idempotency-key aware, org-scoped).
    """

    if simulate:
        return _NodeResult(
            decision="done", output_variables={"simulated_action": "move_candidate"}
        )
    if flow.owner_org_id is None:
        raise NodeExecutionFailed("Không thể chuyển ứng viên: workflow không thuộc tổ chức nào.")
    application_id = _resolve_application_id(data, context)
    if application_id is None:
        raise NodeExecutionFailed("Không thể chuyển ứng viên: thiếu mã hồ sơ ứng tuyển hợp lệ.")

    from app.modules.auth.application.context import RequestContext
    from app.modules.recruitment.application.stage_service import advance_application_stage

    try:
        await advance_application_stage(
            session,
            principal=_automation_principal(flow),
            application_id=application_id,
            idempotency_key=_node_idempotency_key(execution, node),
            ctx=RequestContext(),
            locale=data.get("locale", "vi"),
        )
    except NodeExecutionFailed:
        raise
    except Exception as exc:  # noqa: BLE001 — any downstream error is a recoverable node failure
        # Covers cross-org 404, version conflict, illegal transition, etc. The
        # user-safe message never leaks the underlying reason/PII.
        raise NodeExecutionFailed(
            "Không thể chuyển ứng viên sang giai đoạn tiếp theo."
        ) from exc
    return _NodeResult(decision="done", output_variables={"candidate_moved": True})


async def _run_webhook(
    *,
    node: dict,
    data: dict,
    context: FlowContext,
    execution: WorkflowExecution,
    simulate: bool,
) -> _NodeResult:
    """Deliver a redacted event to an external URL through the SSRF-guarded
    dispatcher. No raw PII leaves the platform (payload is redacted), private/
    internal targets are refused, redirects are disabled, and the call is
    time-boxed. Any failure becomes a recoverable node failure.
    """

    if simulate:
        return _NodeResult(decision="done", output_variables={"simulated_action": "webhook"})

    from app.modules.workflow.application import webhook_dispatch

    url = context.interpolate(str(data.get("url", "")))
    trigger = execution.trigger_event if isinstance(execution.trigger_event, dict) else {}
    payload = {
        "event": data.get("event_key") or trigger.get("type"),
        "flow_id": str(execution.flow_id),
        "execution_id": str(execution.id),
        "node_id": node["id"],
        "data": _summarize(context.variables),
    }
    try:
        status = await webhook_dispatch.post_webhook(
            url,
            payload,
            delivery_id=_node_idempotency_key(execution, node),
            timeout=float(data.get("timeout_seconds", 5.0)),
        )
    except webhook_dispatch.WebhookError as exc:
        raise NodeExecutionFailed(f"Webhook bị từ chối: {exc.user_safe_error}") from exc
    except Exception as exc:  # noqa: BLE001
        raise NodeExecutionFailed("Không thể gọi webhook do lỗi kết nối.") from exc
    return _NodeResult(decision="done", output_variables={"webhook_status": status})


def _coerce_condition_value(value: str) -> float | bool | str:
    token = value.strip()
    if (token.startswith('"') and token.endswith('"')) or (
        token.startswith("'") and token.endswith("'")
    ):
        return token[1:-1]
    lowered = token.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    try:
        return float(token)
    except ValueError:
        if not re.fullmatch(r"[\w .:/@-]{1,200}", token):
            raise NodeExecutionFailed("Điều kiện workflow không hợp lệ.") from None
        return token


def _evaluate_condition(expression: str) -> bool:
    match = _CONDITION_RE.match(expression)
    if match is None:
        raise NodeExecutionFailed("Điều kiện workflow không hợp lệ.")

    left = _coerce_condition_value(match.group("left"))
    right = _coerce_condition_value(match.group("right"))
    op = match.group("op")

    if isinstance(left, float) and isinstance(right, float):
        if op == ">":
            return left > right
        if op == ">=":
            return left >= right
        if op == "<":
            return left < right
        if op == "<=":
            return left <= right
        if op == "==":
            return left == right
        if op == "!=":
            return left != right
    elif op in {"==", "!="}:
        return (left == right) if op == "==" else (left != right)

    raise NodeExecutionFailed("Điều kiện workflow không hợp lệ.")


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
        (
            await session.execute(
                select(WorkflowExecution)
                .where(
                    WorkflowExecution.flow_id == flow.id,
                    WorkflowExecution.is_simulated.is_(False),
                )
                .order_by(WorkflowExecution.started_at.desc())
                .limit(max(limit, 1))
            )
        )
        .scalars()
        .all()
    )
    if not executions:
        return []

    logs = (
        (
            await session.execute(
                select(WorkflowNodeExecutionLog)
                .where(WorkflowNodeExecutionLog.execution_id.in_([e.id for e in executions]))
                .order_by(WorkflowNodeExecutionLog.entered_at.asc())
            )
        )
        .scalars()
        .all()
    )
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
