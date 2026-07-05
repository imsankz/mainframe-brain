"""Golden fixture — DB2 DDL extract over examples/db2/schema.ddl."""
from __future__ import annotations

from pathlib import Path

from mainframe_brain.extractors.db2_ddl.extractor import DB2DDLExtractor
from mainframe_brain.graph.schema import NodeType

_EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "db2" / "schema.ddl"


def test_golden_db2_ddl_shape():
    assert _EXAMPLE.exists()
    res = DB2DDLExtractor().extract(_EXAMPLE, codebase_id="default")
    types = [n.type for n in res.nodes]
    assert NodeType.DB2_TABLE in types
    assert NodeType.VIEW in types or any(e.type.value == "ABSTRACTS" for e in res.edges)
    cascade = [e for e in res.edges if e.type.value == "CASCADES_TO"]
    assert cascade, "expected ON DELETE CASCADE edge"