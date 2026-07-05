"""Extractors — one plugin per artifact type. Extractors never call LLMs."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from mainframe_brain.graph.schema import Edge, Node


@dataclass
class LogicalUnit:
    """A chunk of an artifact, hashed for incremental re-analysis.

    CRITICAL: `source` and `content_hash` are computed POST-expansion for any
    unit affected by COPY...REPLACING. Hashing the raw copybook file would
    cache narrations against the wrong field names (gap #2 fix).
    """
    kind: str            # e.g. "paragraph", "copybook", "job_step"
    name: str
    source: str          # normalized, EXPANDED source text of this unit
    content_hash: str
    properties: dict = field(default_factory=dict)
    post_expansion: bool = False   # True if REPLACING was applied before hashing


def content_hash(text: str) -> str:
    """SHA-256 of normalized text (collapse whitespace, strip trailing ws).

    Use POST-expansion text for any unit touched by COPY...REPLACING so the
    cache is keyed to what the LLM actually sees, not the unexpanded copybook.
    """
    normalized = "\n".join(line.rstrip() for line in text.splitlines())
    return hashlib.sha256(normalized.encode("utf-8", errors="replace")).hexdigest()


@dataclass
class ExtractionResult:
    """Output of an extractor — nodes + edges + logical units queued for triage."""
    artifact_type: str
    source_file: str
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    units: list[LogicalUnit] = field(default_factory=list)


class Extractor(Protocol):
    artifact_type: str

    def can_handle(self, file_path: Path) -> bool: ...

    def extract(self, file_path: Path, codebase_id: str = "default") -> ExtractionResult: ...


__all__ = ["Extractor", "ExtractionResult", "LogicalUnit", "content_hash"]