from __future__ import annotations

from app.modules.ai_settings.domain.routing_validation import validate_routing_graph

VALID_GRAPH = {
    "nodes": [
        {"id": "p1", "type": "provider", "data": {"provider_id": "11111111-1111-1111-1111-111111111111", "order": 0}},
        {"id": "p2", "type": "provider", "data": {"provider_id": "22222222-2222-2222-2222-222222222222", "order": 1}},
    ],
    "edges": [{"source": "p1", "target": "p2", "kind": "fallback"}],
}


def test_valid_routing_graph_has_no_errors() -> None:
    assert validate_routing_graph(VALID_GRAPH) == []


def test_duplicate_provider_in_graph_is_rejected() -> None:
    graph = {
        "nodes": [
            {"id": "p1", "type": "provider", "data": {"provider_id": "11111111-1111-1111-1111-111111111111", "order": 0}},
            {"id": "p2", "type": "provider", "data": {"provider_id": "11111111-1111-1111-1111-111111111111", "order": 1}},
        ],
        "edges": [{"source": "p1", "target": "p2", "kind": "fallback"}],
    }
    errors = validate_routing_graph(graph)
    assert any("duplicate provider" in e for e in errors)


def test_no_primary_provider_is_rejected() -> None:
    errors = validate_routing_graph({"nodes": [], "edges": []})
    assert any("at least one provider node" in e for e in errors)


def test_orphan_provider_node_is_rejected() -> None:
    graph = {
        "nodes": VALID_GRAPH["nodes"] + [{"id": "p3", "type": "provider", "data": {"provider_id": "33333333-3333-3333-3333-333333333333", "order": 2}}],
        "edges": VALID_GRAPH["edges"],
    }
    errors = validate_routing_graph(graph)
    assert any("not connected to the fallback chain" in e for e in errors)
