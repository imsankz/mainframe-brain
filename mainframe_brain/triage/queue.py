"""Build the LLM work queue — ordered by risk, bounded by token budget."""
from __future__ import annotations

from dataclasses import dataclass, field

from mainframe_brain.extractors.base import LogicalUnit
from mainframe_brain.graph.schema import Node
from mainframe_brain.graph.store import GraphStore, make_node_id
from mainframe_brain.triage.risk import combined_risk, risk_score


@dataclass
class WorkItem:
    unit: LogicalUnit
    node_id: str
    risk_score: float
    tokens_estimate: int


@dataclass
class WorkQueue:
    items: list[WorkItem] = field(default_factory=list)
    estimated_tokens: int = 0
    budget_remaining: int = 0
    skipped_count: int = 0


def build_work_queue(
    store: GraphStore,
    units: list[LogicalUnit],
    node_lookup: dict[str, Node],
    budget_tokens: int,
    priority_threshold: float,
    codebase_id: str = "default",
) -> WorkQueue:
    items: list[WorkItem] = []
    skipped = 0
    for unit in units:
        node_id = make_node_id(unit.kind.capitalize(), codebase_id, unit.name)
        node = node_lookup.get(node_id)
        if node is None:
            continue
        base = risk_score(node)
        risk = combined_risk(store, node, base)
        items.append(
            WorkItem(
                unit=unit,
                node_id=node.id,
                risk_score=risk,
                tokens_estimate=max(1, len(unit.source) // 4),
            )
        )

    items.sort(key=lambda it: it.risk_score, reverse=True)

    chosen: list[WorkItem] = []
    used = 0
    for item in items:
        if item.risk_score < priority_threshold:
            skipped += 1
            continue
        if used + item.tokens_estimate > budget_tokens:
            skipped += 1
            continue
        chosen.append(item)
        used += item.tokens_estimate

    return WorkQueue(
        items=chosen,
        estimated_tokens=used,
        budget_remaining=budget_tokens - used,
        skipped_count=skipped,
    )