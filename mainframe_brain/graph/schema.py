"""Versioned node and edge type definitions for the Mainframe Brain knowledge graph.

The schema is a public contract: community extractors and enrichers depend on it.
Breaking changes require a migration path. Bump `SCHEMA_VERSION` on any breaking change.
"""
from __future__ import annotations

import enum
from dataclasses import asdict, dataclass, field
from typing import Any

SCHEMA_VERSION = "1.2.0"


class NodeType(str, enum.Enum):
    # Source-code / structural
    PROGRAM = "Program"
    PARAGRAPH = "Paragraph"
    COPYBOOK = "Copybook"
    FIELD = "Field"
    # JCL / jobs
    JCL_JOB = "JCLJob"
    JCL_STEP = "JCLStep"
    # Data sources (multiple first-class)
    DATASET = "Dataset"            # generic: file, GDG, VSAM, sequential
    DB2_TABLE = "DB2Table"
    DB2_COLUMN = "DB2Column"
    VSAM_DATASET = "VSAMDataset"   # KSDS/ESDS/RRDS
    # CICS
    CICS_MAP = "CICSMap"
    # DB2 procedural
    STORED_PROCEDURE = "StoredProcedure"
    TRIGGER = "Trigger"
    VIEW = "View"
    CONSTRAINT = "Constraint"
    # Reports / business output
    REPORT = "Report"
    # External boundaries
    EXTERNAL_SYSTEM = "ExternalSystem"
    # LLM-derived
    BUSINESS_RULE = "BusinessRule"


class EdgeType(str, enum.Enum):
    CALLS = "CALLS"
    PERFORMS = "PERFORMS"
    INCLUDES = "INCLUDES"
    READS = "READS"
    WRITES = "WRITES"
    DERIVED_FROM = "DERIVED_FROM"
    IMPLEMENTS_RULE = "IMPLEMENTS_RULE"
    RENDERS_ON = "RENDERS_ON"          # program → CICS map
    INVOKES_PROC = "INVOKES_PROC"
    FIRES_ON = "FIRES_ON"              # Trigger → Table
    TRIGGERS_TRIGGER = "TRIGGERS_TRIGGER"
    ABSTRACTS = "ABSTRACTS"            # View → Table
    CASCADES_TO = "CASCADES_TO"       # Table → Table via FK
    PRODUCES_REPORT = "PRODUCES_REPORT"  # JCLJob/Step → Report
    CALLS_EXTERNAL = "CALLS_EXTERNAL"  # Program → ExternalSystem
    XCTLS = "XCTLS"                     # CICS pseudo-conversational handoff (deferred)
    EXECUTES = "EXECUTES"               # JCLStep → Program (job runs which program)


@dataclass
class Node:
    """A graph node. `id` is globally unique within a brain.

    Convention: id = "{type}:{codebase_id}:{name}".
    `content_hash` is load-bearing for incremental re-analysis.
    `parse_confidence` (0..1) flags partial-parse nodes instead of dropping them.
    """
    id: str
    type: NodeType
    name: str
    codebase_id: str = "default"
    content_hash: str = ""
    last_verified: str = ""  # ISO8601; "" = never
    parse_confidence: float = 1.0  # <1.0 = partial/low-confidence parse
    properties: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["type"] = self.type.value
        return d


@dataclass
class Edge:
    """A directed graph edge."""
    src: str
    dst: str
    type: EdgeType
    properties: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["type"] = self.type.value
        return d


__all__ = [
    "SCHEMA_VERSION",
    "NodeType",
    "EdgeType",
    "Node",
    "Edge",
]