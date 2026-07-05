"""Hash-based deduplication — analyze each unique piece of logic once."""
from __future__ import annotations

from collections import defaultdict

from mainframe_brain.extractors.base import LogicalUnit


def dedup_by_hash(units: list[LogicalUnit]) -> dict[str, list[LogicalUnit]]:
    groups: dict[str, list[LogicalUnit]] = defaultdict(list)
    for unit in units:
        groups[unit.content_hash].append(unit)
    return dict(groups)