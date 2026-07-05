"""Change diff — which logical units are new/changed/unchanged vs the stored graph."""
from __future__ import annotations

from dataclasses import dataclass

from mainframe_brain.extractors.base import LogicalUnit
from mainframe_brain.graph.store import GraphStore, make_node_id


@dataclass
class DiffResult:
    added: list[str]
    changed: list[str]
    unchanged: list[str]


def _unit_node_id(unit: LogicalUnit, codebase_id: str) -> str:
    return make_node_id(unit.kind.capitalize(), codebase_id, unit.name)


def compute_diff(store: GraphStore, current_units: list[LogicalUnit], codebase_id: str) -> DiffResult:
    stored = {n.id: n.content_hash for n in store.all_nodes() if n.codebase_id == codebase_id}
    added: list[str] = []
    changed: list[str] = []
    unchanged: list[str] = []
    for unit in current_units:
        nid = _unit_node_id(unit, codebase_id)
        if nid not in stored:
            added.append(nid)
        elif stored[nid] != unit.content_hash:
            changed.append(nid)
        else:
            unchanged.append(nid)
    return DiffResult(added=added, changed=changed, unchanged=unchanged)