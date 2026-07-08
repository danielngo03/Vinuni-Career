"""Structural validation for an AI routing graph before save/activation.

A routing graph represents one task family's fallback CHAIN: an ordered list
of provider nodes connected by "fallback" edges (p1 -> p2 -> p3 means "try p1
first, then p2, then p3"). This is deliberately simpler than the workflow
engine's general DAG validation — a fallback chain has no branching Condition
nodes in this first version, so cycle detection isn't needed in the same
sense; duplicate-provider and orphan-node checks are what actually matter
here.
"""

from __future__ import annotations

from app.modules.ai_settings.domain.aliases import ALIAS_FIELDS

TASK_FAMILIES: tuple[str, ...] = tuple(sorted(set(ALIAS_FIELDS.values())))


def validate_routing_graph(graph: dict) -> list[str]:
    errors: list[str] = []
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    provider_nodes = [n for n in nodes if n.get("type") == "provider"]

    if not provider_nodes:
        errors.append("graph must contain at least one provider node")
        return errors

    provider_ids = [n["data"]["provider_id"] for n in provider_nodes]
    seen: set[str] = set()
    for pid in provider_ids:
        if pid in seen:
            errors.append(f"duplicate provider in graph: {pid}")
        seen.add(pid)

    if len(provider_nodes) > 1:
        connected: set[str] = set()
        for edge in edges:
            if edge.get("kind") == "fallback":
                connected.add(edge["source"])
                connected.add(edge["target"])
        for node in provider_nodes:
            if node["id"] not in connected:
                errors.append(f"provider node {node['id']} is not connected to the fallback chain")

    return errors
