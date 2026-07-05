"""Layer 3 — change & risk triage. Decides what's worth spending tokens on."""
from __future__ import annotations

from mainframe_brain.triage.dedup import dedup_by_hash
from mainframe_brain.triage.diff import DiffResult, compute_diff
from mainframe_brain.triage.queue import WorkItem, WorkQueue, build_work_queue
from mainframe_brain.triage.risk import (
    cascade_depth,
    combined_risk,
    risk_score,
    trigger_chain_depth,
)

__all__ = [
    "DiffResult",
    "compute_diff",
    "dedup_by_hash",
    "risk_score",
    "cascade_depth",
    "trigger_chain_depth",
    "combined_risk",
    "WorkItem",
    "WorkQueue",
    "build_work_queue",
]