"""Deterministic risk scoring — cheap priors before any LLM token is spent.

Heuristic rationale (see ARCHITECTURE 4.3 / 5):
- Cyclomatic complexity weights control-flow fanout, the strongest single proxy
  for "hard to narrate / easy to break."
- GOTO density captures spaghetti that complexity undercounts (unstructured jumps).
- External calls and undocumented literals surface hidden coupling and magic numbers.
- parse_confidence < 0.5 multiplies the score by 0.3 so partial-parse garbage
  does not crowd out real risk (5.11).
- Cascade depth (Table -> CASCADES_TO -> Table) and trigger-chain depth
  (Trigger -> TRIGGERS_TRIGGER -> Trigger) are *independent* multipliers: a
  three-deep FK cascade is risky to touch regardless of the paragraph above it.
"""
from __future__ import annotations

from collections import deque

from mainframe_brain.graph.schema import EdgeType, Node, NodeType
from mainframe_brain.graph.store import GraphStore


def _count(value) -> int:
    if isinstance(value, (list, tuple, set)):
        return len(value)
    return int(value or 0)


def risk_score(node: Node) -> float:
    p = node.properties
    complexity = float(p.get("cyclomatic_complexity", 0) or 0)
    goto = float(p.get("goto_density", 0) or 0)
    ext_calls = float(_count(p.get("external_calls", 0)))
    literals = float(_count(p.get("undocumented_literals", 0)))
    raw = complexity * 0.5 + goto * 0.2 + ext_calls * 0.15 + literals * 0.1
    capped = max(0.0, min(20.0, raw))
    pc = node.parse_confidence if node.parse_confidence is not None else 1.0
    factor = 0.3 if pc < 0.5 else 1.0
    return capped * factor


def _bfs_depth(store: GraphStore, start_id: str, edge_type: EdgeType) -> int:
    depth = 0
    seen: set[str] = {start_id}
    frontier: deque[str] = deque([start_id])
    while frontier:
        nxt: deque[str] = deque()
        for node_id in frontier:
            for nbr in store.neighbors(node_id, edge_type=edge_type.value):
                if nbr.id not in seen:
                    seen.add(nbr.id)
                    nxt.append(nbr.id)
        if nxt:
            depth += 1
            frontier = nxt
        else:
            break
    return depth


def cascade_depth(store: GraphStore, table_node_id: str) -> int:
    return _bfs_depth(store, table_node_id, EdgeType.CASCADES_TO)


def trigger_chain_depth(store: GraphStore, trigger_node_id: str) -> int:
    return _bfs_depth(store, trigger_node_id, EdgeType.TRIGGERS_TRIGGER)


def combined_risk(store: GraphStore, node: Node, base: float) -> float:
    score = base
    if node.type == NodeType.DB2_TABLE:
        score += cascade_depth(store, node.id) * 0.5
    elif node.type == NodeType.TRIGGER:
        score += trigger_chain_depth(store, node.id) * 0.8
    return score