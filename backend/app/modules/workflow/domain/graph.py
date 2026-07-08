"""Pure graph/context concepts for the workflow engine: no I/O, no ORM."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum

_VAR_PATTERN = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")


class TriggerType(StrEnum):
    STUDENT_REGISTERED = "system.student_registered"
    APPLICATION_SUBMITTED = "system.application_submitted"
    PAYMENT_RECEIVED = "system.payment_received"
    FILE_UPLOADED = "system.file_uploaded"
    PARTNER_REGISTERED = "system.partner_registered"
    SCHEDULER_CRON = "scheduler.cron"


class NodeType(StrEnum):
    """Explicit node-type catalog for the visual workflow builder
    (docs/PARTNER_RBAC_ANALYTICS_SPEC.md "Visual Recruiting Workflow Builder
    Contract"). ``ACTION``/``AI_PROCESS``/``HUMAN_REVIEW``/``DELAY`` are the
    original generic node types kept for backward compatibility with existing
    saved graphs and tests; the newer specific types below are additive so the
    builder can offer a precise palette without breaking prior flows.
    """

    TRIGGER = "trigger"
    CONDITION = "condition"
    # Generic/legacy node types (kept for backward compatibility).
    AI_PROCESS = "ai_process"
    HUMAN_REVIEW = "human_review"
    ACTION = "action"
    DELAY = "delay"
    END = "end"
    # Spec-named node types (contract catalog).
    WAIT = "wait"
    ASSIGN_OWNER = "assign_owner"
    SEND_NOTIFICATION = "send_notification"
    CREATE_TASK = "create_task"
    MOVE_CANDIDATE = "move_candidate"
    REQUEST_APPROVAL = "request_approval"
    AI_SUGGESTION = "ai_suggestion"
    WEBHOOK = "webhook"


# Node types whose real (non-simulated) execution performs, or is intended to
# eventually perform, a side effect outside the workflow module itself (send a
# message, mutate a pipeline stage, call an external system, etc). These are
# exactly the node types a dry-run must no-op instead of executing for real.
SIDE_EFFECTING_NODE_TYPES = frozenset(
    {
        NodeType.ACTION,
        NodeType.ASSIGN_OWNER,
        NodeType.SEND_NOTIFICATION,
        NodeType.CREATE_TASK,
        NodeType.MOVE_CANDIDATE,
        NodeType.REQUEST_APPROVAL,
        NodeType.HUMAN_REVIEW,
        NodeType.AI_SUGGESTION,
        NodeType.AI_PROCESS,
        NodeType.WEBHOOK,
    }
)

# Node types that require the activator to hold a specific RBAC capability
# (``resource_type:action``) before a flow containing them can be activated.
# ``data.capability`` on the node overrides the default for that node type so
# a flow author can be explicit (e.g. an ACTION node whose ``data.action`` is
# ``"offers:send"``). This is intentionally a conservative default map — a
# node with an unmapped/custom action falls back to ``workflow:activate``
# (already required for the flow overall) rather than blocking activation on
# a capability the platform cannot infer.
DEFAULT_NODE_CAPABILITY: dict[NodeType, tuple[str, str]] = {
    NodeType.ASSIGN_OWNER: ("jobs", "assign_owner"),
    NodeType.SEND_NOTIFICATION: ("notifications", "send"),
    NodeType.CREATE_TASK: ("workflow", "create_task"),
    NodeType.MOVE_CANDIDATE: ("pipeline", "move_candidate"),
    NodeType.REQUEST_APPROVAL: ("workflow", "request_approval"),
    NodeType.HUMAN_REVIEW: ("workflow", "request_approval"),
    NodeType.AI_SUGGESTION: ("ai_assistant", "suggest"),
    NodeType.AI_PROCESS: ("ai_assistant", "suggest"),
    NodeType.WEBHOOK: ("workflow", "webhook"),
}


def required_capability_for_node(node: dict) -> tuple[str, str] | None:
    """Resolve the ``(resource_type, action)`` capability a node requires to
    be activated, honoring an explicit ``data.capability: "resource:action"``
    override (e.g. an ``action`` node whose real effect is ``offers:send``).
    """

    data = node.get("data") or {}
    override = data.get("capability")
    if isinstance(override, str) and ":" in override:
        resource, action = override.split(":", 1)
        return resource, action

    node_type = node.get("type")
    try:
        return DEFAULT_NODE_CAPABILITY.get(NodeType(node_type))
    except ValueError:
        return None


class FlowStatus(StrEnum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    ARCHIVED = "ARCHIVED"


class ExecutionStatus(StrEnum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass(slots=True)
class FlowContext:
    """Variables available to node expressions, accumulated across a run.

    ``trigger`` is the original event payload (read-only in practice, never
    mutated); ``variables`` accumulates each node's declared outputs so later
    nodes can reference ``{{some_output}}`` per docs/BUSINESS_LOGIC.md §16.2.
    """

    trigger: dict
    variables: dict = field(default_factory=dict)

    def _lookup(self, key: str) -> str:
        if key in self.variables:
            return str(self.variables[key])
        if key in self.trigger:
            return str(self.trigger[key])
        raise KeyError(f"unknown flow variable: {key}")

    def interpolate(self, template: str) -> str:
        return _VAR_PATTERN.sub(lambda m: self._lookup(m.group(1)), template)

    def merge(self, output: dict) -> None:
        self.variables.update(output)
