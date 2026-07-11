"""Structural validation for a workflow graph before it can be saved as DRAFT
or promoted to ACTIVE. Pure function, no I/O.
"""

from __future__ import annotations

from app.modules.workflow.domain.graph import NodeType

_VALID_TYPES = {t.value for t in NodeType}
_VALID_ASSIGNEE_MODES = {"person", "queue"}


def validate_graph(graph: dict) -> list[str]:
    errors: list[str] = []
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    node_ids = {n["id"] for n in nodes}

    trigger_nodes = [n for n in nodes if n.get("type") == NodeType.TRIGGER.value]
    if len(trigger_nodes) != 1:
        errors.append("graph must contain exactly one trigger node")

    for node in nodes:
        node_type = node.get("type")
        if node_type not in _VALID_TYPES:
            errors.append(f"node {node.get('id')} has unknown type {node_type!r}")
            continue
        if node_type in (NodeType.HUMAN_REVIEW.value, NodeType.REQUEST_APPROVAL.value):
            errors.extend(_validate_human_review(node))
        if node_type == NodeType.SEND_NOTIFICATION.value:
            errors.extend(_validate_send_notification(node))
        if node_type == NodeType.WEBHOOK.value:
            errors.extend(_validate_webhook(node))
        if node_type == NodeType.AI_SCREEN_APPLICATION.value:
            errors.extend(_validate_ai_screen(node))
        if node_type == NodeType.NOTIFY.value:
            errors.extend(_validate_notify(node))

    for edge in edges:
        if edge.get("source") not in node_ids or edge.get("target") not in node_ids:
            errors.append(f"edge references unknown node: {edge}")

    reachable = _reachable_from_trigger(nodes, edges)
    for node in nodes:
        if node["id"] not in reachable:
            errors.append(f"orphan node not reachable from trigger: {node['id']}")

    if _has_cycle(node_ids, edges):
        errors.append("graph contains a cycle; workflow graphs must be a DAG")

    return errors


def _validate_human_review(node: dict) -> list[str]:
    errors: list[str] = []
    data = node.get("data", {})
    mode = data.get("assignee_mode")
    if mode not in _VALID_ASSIGNEE_MODES:
        errors.append(f"node {node['id']}: assignee_mode must be one of {_VALID_ASSIGNEE_MODES}")
        return errors
    if mode == "person" and not data.get("assignee_user_id"):
        errors.append(f"node {node['id']}: assignee_mode=person requires assignee_user_id")
    if mode == "queue" and not data.get("assignee_department_id"):
        errors.append(f"node {node['id']}: assignee_mode=queue requires assignee_department_id")
    return errors


def _validate_send_notification(node: dict) -> list[str]:
    data = node.get("data", {})
    if not data.get("template_key"):
        return [f"node {node['id']}: send_notification requires data.template_key"]
    return []


def _validate_webhook(node: dict) -> list[str]:
    data = node.get("data", {})
    if not data.get("url"):
        return [f"node {node['id']}: webhook requires data.url"]
    return []


_VALID_SCREEN_MODES = {"deterministic", "llm"}


def _validate_ai_screen(node: dict) -> list[str]:
    """``ai_screen_application`` config: an optional ``mode`` (deterministic|llm) and
    optional numeric thresholds. Thresholds must be within 0..100 and ordered
    (strong >= consider) so a flow author cannot build a nonsensical branch."""

    errors: list[str] = []
    data = node.get("data", {})
    mode = data.get("mode", "deterministic")
    if mode not in _VALID_SCREEN_MODES:
        errors.append(
            f"node {node['id']}: ai_screen_application mode must be one of {_VALID_SCREEN_MODES}"
        )
    strong = data.get("strong_threshold", 80)
    consider = data.get("consider_threshold", 50)
    for label, value in (("strong_threshold", strong), ("consider_threshold", consider)):
        if not isinstance(value, int | float) or not 0 <= float(value) <= 100:
            errors.append(f"node {node['id']}: {label} must be a number in 0..100")
    if (
        isinstance(strong, int | float)
        and isinstance(consider, int | float)
        and float(strong) < float(consider)
    ):
        errors.append(f"node {node['id']}: strong_threshold must be >= consider_threshold")
    return errors


_VALID_NOTIFY_RECIPIENT_MODES = {"assignee", "user", "trigger_var"}


def _validate_notify(node: dict) -> list[str]:
    """``notify`` config: a ``template_key`` plus a ``recipient_mode``. Modes
    ``user``/``trigger_var`` require the referenced key so a flow cannot activate a
    notify node that can never resolve a recipient."""

    errors: list[str] = []
    data = node.get("data", {})
    if not data.get("template_key"):
        errors.append(f"node {node['id']}: notify requires data.template_key")
    mode = data.get("recipient_mode", "assignee")
    if mode not in _VALID_NOTIFY_RECIPIENT_MODES:
        errors.append(
            f"node {node['id']}: notify recipient_mode must be one of "
            f"{_VALID_NOTIFY_RECIPIENT_MODES}"
        )
        return errors
    if mode == "user" and not data.get("recipient_user_id"):
        errors.append(f"node {node['id']}: notify recipient_mode=user requires recipient_user_id")
    if mode == "trigger_var" and not data.get("recipient_variable"):
        errors.append(
            f"node {node['id']}: notify recipient_mode=trigger_var requires recipient_variable"
        )
    return errors


def _reachable_from_trigger(nodes: list[dict], edges: list[dict]) -> set[str]:
    trigger = next((n["id"] for n in nodes if n.get("type") == NodeType.TRIGGER.value), None)
    if trigger is None:
        return set()
    adjacency: dict[str, list[str]] = {}
    for edge in edges:
        adjacency.setdefault(edge["source"], []).append(edge["target"])
    seen: set[str] = set()
    stack = [trigger]
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        stack.extend(adjacency.get(current, []))
    return seen


def _has_cycle(node_ids: set[str], edges: list[dict]) -> bool:
    adjacency: dict[str, list[str]] = {n: [] for n in node_ids}
    for edge in edges:
        target = edge.get("target")
        if edge.get("source") in adjacency and target is not None:
            adjacency[edge["source"]].append(target)

    WHITE, GRAY, BLACK = 0, 1, 2
    color = dict.fromkeys(node_ids, WHITE)

    def dfs(node: str) -> bool:
        color[node] = GRAY
        for neighbor in adjacency.get(node, []):
            if neighbor not in color:
                continue
            if color[neighbor] == GRAY:
                return True
            if color[neighbor] == WHITE and dfs(neighbor):
                return True
        color[node] = BLACK
        return False

    return any(color[n] == WHITE and dfs(n) for n in node_ids)


class GraphValidationError(Exception):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))
