"""Golden fixture — COBOL extract run over examples/cobol/INTCALC01.cbl.

Locks the parser output shape across regressions. Update only when extractor
behavior intentionally changes.
"""
from __future__ import annotations

from pathlib import Path

from mainframe_brain.extractors.cobol.extractor import CobolExtractor
from mainframe_brain.graph.schema import NodeType

_EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "cobol" / "INTCALC01.cbl"


def test_golden_cobol_extract_shape():
    assert _EXAMPLE.exists(), f"missing example {_EXAMPLE}"
    res = CobolExtractor().extract(_EXAMPLE, codebase_id="default")

    types = [n.type for n in res.nodes]
    assert NodeType.PROGRAM in types
    assert types.count(NodeType.PARAGRAPH) >= 5
    assert NodeType.FIELD in types

    program_nodes = [n for n in res.nodes if n.type == NodeType.PROGRAM]
    assert program_nodes[0].name == "INTCALC01"

    db2_edges = [e for e in res.edges if e.type.value in {"READS", "WRITES"}]
    assert db2_edges, "expected embedded SQL READS/WRITES edge"

    for n in res.nodes:
        assert n.id
        assert 0.0 <= n.parse_confidence <= 1.0
        if n.type == NodeType.PARAGRAPH:
            assert n.content_hash and len(n.content_hash) == 64
            assert "source" in n.properties


def test_golden_cobol_call_edges():
    res = CobolExtractor().extract(_EXAMPLE)
    calls = [e for e in res.edges if e.type.value == "CALLS"]
    assert calls, "expected at least one CALL edge"
    for e in calls:
        assert e.dst.startswith("Program:default:")