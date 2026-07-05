"""Golden fixture — JCL extract over examples/jcl/PAYRUN.jcl (synthetic)."""
from __future__ import annotations

from pathlib import Path

from mainframe_brain.extractors.jcl.extractor import JCLExtractor
from mainframe_brain.graph.schema import EdgeType, NodeType

_EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "jcl" / "PAYRUN.jcl"


def test_golden_jcl_shape():
    assert _EXAMPLE.exists(), f"missing example {_EXAMPLE}"
    res = JCLExtractor().extract(_EXAMPLE, codebase_id="default")

    types = [n.type for n in res.nodes]
    assert types.count(NodeType.JCL_JOB) >= 1
    assert types.count(NodeType.JCL_STEP) >= 3
    assert types.count(NodeType.DATASET) >= 4

    job_nodes = [n for n in res.nodes if n.type == NodeType.JCL_JOB]
    job = job_nodes[0]
    assert job.name == "PAYRUN"
    assert job.properties["msgclass"] == "X"
    assert job.properties["restart"] == "STEP-CALC"
    assert job.properties["class"] == "A"

    reads = [e for e in res.edges if e.type == EdgeType.READS]
    writes = [e for e in res.edges if e.type == EdgeType.WRITES]
    assert reads, "expected READS edges from steps to datasets"
    assert writes, "expected WRITES edges from steps to datasets"

    for e in reads + writes:
        assert e.src.startswith("JCLStep:default:")
        assert e.dst.startswith("Dataset:default:")

    assert len(res.units) >= 3
    for n in res.nodes:
        assert 0.0 <= n.parse_confidence <= 1.0
        if n.type == NodeType.JCL_STEP and n.parse_confidence == 1.0:
            assert n.content_hash and len(n.content_hash) == 64
    for u in res.units:
        assert u.kind == "job_step"
        assert len(u.content_hash) == 64