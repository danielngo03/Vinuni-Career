from __future__ import annotations

from app.modules.workflow.domain.validation import validate_graph

VALID_GRAPH = {
    "nodes": [
        {"id": "n1", "type": "trigger", "data": {"trigger_type": "system.student_registered"}},
        {
            "id": "n2",
            "type": "human_review",
            "data": {
                "assignee_mode": "person",
                "assignee_user_id": "11111111-1111-1111-1111-111111111111",
                "sla_hours": 24,
            },
        },
        {"id": "n3", "type": "end", "data": {}},
    ],
    "edges": [
        {"source": "n1", "target": "n2"},
        {"source": "n2", "target": "n3"},
    ],
}


def test_valid_graph_has_no_errors() -> None:
    assert validate_graph(VALID_GRAPH) == []


def test_cycle_is_rejected() -> None:
    graph = {
        "nodes": VALID_GRAPH["nodes"],
        "edges": [
            {"source": "n1", "target": "n2"},
            {"source": "n2", "target": "n1"},
        ],
    }
    errors = validate_graph(graph)
    assert any("cycle" in e for e in errors)


def test_missing_trigger_node_is_rejected() -> None:
    graph = {"nodes": [{"id": "n1", "type": "end", "data": {}}], "edges": []}
    errors = validate_graph(graph)
    assert any("exactly one trigger node" in e for e in errors)


def test_human_review_requires_assignee_fields() -> None:
    graph = {
        "nodes": [
            {"id": "n1", "type": "trigger", "data": {"trigger_type": "system.student_registered"}},
            {"id": "n2", "type": "human_review", "data": {"assignee_mode": "person"}},
        ],
        "edges": [{"source": "n1", "target": "n2"}],
    }
    errors = validate_graph(graph)
    assert any("assignee_user_id" in e for e in errors)


def test_human_review_queue_mode_requires_department() -> None:
    graph = {
        "nodes": [
            {"id": "n1", "type": "trigger", "data": {"trigger_type": "system.student_registered"}},
            {"id": "n2", "type": "human_review", "data": {"assignee_mode": "queue"}},
        ],
        "edges": [{"source": "n1", "target": "n2"}],
    }
    errors = validate_graph(graph)
    assert any("assignee_department_id" in e for e in errors)


def test_orphan_node_is_rejected() -> None:
    graph = {
        "nodes": VALID_GRAPH["nodes"] + [{"id": "n4", "type": "end", "data": {}}],
        "edges": VALID_GRAPH["edges"],
    }
    errors = validate_graph(graph)
    assert any("orphan" in e for e in errors)
