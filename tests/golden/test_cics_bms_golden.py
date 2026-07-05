"""Golden fixture — CICS BMS extract over examples/cics_bms/MENU01.bms."""
from __future__ import annotations

from pathlib import Path

from mainframe_brain.extractors.cics_bms.extractor import CICSBMSExtractor
from mainframe_brain.graph.schema import NodeType

_EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "cics_bms" / "MENU01.bms"


def test_golden_cics_bms_shape():
    assert _EXAMPLE.exists()
    res = CICSBMSExtractor().extract(_EXAMPLE, codebase_id="default")
    maps = [n for n in res.nodes if n.type == NodeType.CICS_MAP]
    assert len(maps) == 1
    m = maps[0]
    assert m.name == "MAP01S"
    assert m.properties["fields_seen"] >= 6
    assert m.properties["maps_seen"] == 2
    assert m.properties["final_seen"] is True
    assert len(m.content_hash) == 64
    assert all(c in "0123456789abcdef" for c in m.content_hash)
    assert len(res.units) > 0
    assert all(len(u.content_hash) == 64 for u in res.units)
    assert m.parse_confidence == 1.0