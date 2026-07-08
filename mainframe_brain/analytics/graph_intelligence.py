from __future__ import annotations

from collections import Counter
from typing import Any

from mainframe_brain.graph.schema import Node
from mainframe_brain.graph.store import GraphStore
from mainframe_brain.triage.risk import combined_risk, risk_score


def _serialize_node(node: Node) -> dict[str, Any]:
    return {
        "id": node.id,
        "name": node.name,
        "type": node.type.value,
        "codebase_id": node.codebase_id,
        "parse_confidence": node.parse_confidence,
        "properties": node.properties or {},
    }


def _top_risk_nodes(store: GraphStore, limit: int = 5) -> list[dict[str, Any]]:
    nodes = store.all_nodes()
    scored = []
    for node in nodes:
        risk = combined_risk(store, node, risk_score(node))
        scored.append((risk, node))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [
        {
            "node": _serialize_node(node),
            "risk_score": round(risk, 2),
        }
        for risk, node in scored[:limit]
    ]


def _hub_nodes(store: GraphStore, limit: int = 5) -> list[dict[str, Any]]:
    degree = Counter()
    for edge in store.all_edges():
        degree[edge.src] += 1
        degree[edge.dst] += 1
    ranked = sorted(degree.items(), key=lambda item: item[1], reverse=True)
    nodes = {node.id: node for node in store.all_nodes()}
    result = []
    for node_id, count in ranked[:limit]:
        node = nodes.get(node_id)
        if node is None:
            continue
        result.append({
            "node": _serialize_node(node),
            "degree": count,
        })
    return result


def build_graph_summary(store: GraphStore) -> dict[str, Any]:
    nodes = list(store.all_nodes())
    edges = list(store.all_edges())
    by_type = Counter(node.type.value for node in nodes)
    edge_types = Counter(edge.type.value for edge in edges)
    logical_units = sum(1 for node in nodes if node.type.value == "Paragraph")
    return {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes_by_type": dict(by_type),
        "edges_by_type": dict(edge_types),
        "logical_units_discoverable": logical_units,
        "top_risk_nodes": _top_risk_nodes(store),
        "hub_nodes": _hub_nodes(store),
        "graph_health": "stable" if edges else "empty",
    }


def analyze_impact(store: GraphStore, node_id: str, max_depth: int = 3) -> dict[str, Any]:
    target = store.get_node(node_id)
    if target is None:
        raise KeyError(node_id)

    seen: set[str] = set()
    queue: list[tuple[str, int]] = [(node_id, 0)]
    impact_nodes: list[dict[str, Any]] = []

    while queue:
        current_id, depth = queue.pop()
        if current_id in seen or depth > max_depth:
            continue
        seen.add(current_id)
        current = store.get_node(current_id)
        if current is None:
            continue
        for edge in store.all_edges():
            if edge.src == current_id:
                neighbor_id = edge.dst
            elif edge.dst == current_id:
                neighbor_id = edge.src
            else:
                continue
            if neighbor_id == node_id:
                continue
            if neighbor_id not in seen:
                queue.append((neighbor_id, depth + 1))
        if current_id != node_id:
            impact_nodes.append({
                "node": _serialize_node(current),
                "distance": depth,
                "relation": "downstream",
            })

    impact_nodes.sort(key=lambda item: (item["distance"], item["node"]["name"]))
    return {
        "target": node_id,
        "impact_count": len(impact_nodes),
        "max_depth": max_depth,
        "data": impact_nodes,
    }
