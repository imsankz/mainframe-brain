import tempfile
from pathlib import Path

from mainframe_brain.extractors.cics_bms.extractor import CICSBMSExtractor
from mainframe_brain.graph.schema import NodeType

BMS = """\
         MAP01S  DFHMSD TYPE=&SYSPARM,LANG=COBOL,MODE=INOUT
         MAIN    DFHMDI SIZE=(24,80)
         TITLE   DFHMDF POS=(1,28),LENGTH=24,ATTRB=(NORM,PROT),             X
                        INITIAL='TITLE'
         FLD1    DFHMDF POS=(3,5),LENGTH=10
         MAP01S  DFHMSD TYPE=FINAL
"""

MALFORMED = """\
         MAP01S  DFHMSD TYPE=&SYSPARM,LANG=COBOL
         MAIN    DFHMDI SIZE=(24,80)
         BADFLD  DFHMDF LENGTH=10,ATTRB=(NORM,PROT)
         GOOD    DFHMDF POS=(3,5),LENGTH=4
         MAP01S  DFHMSD TYPE=FINAL
"""


def _write(d: Path, text: str, name: str = "menu.bms") -> Path:
    p = d / name
    p.write_text(text)
    return p


def test_can_handle_bms_extensions():
    ext = CICSBMSExtractor()
    assert ext.can_handle(Path("a.bms"))
    assert ext.can_handle(Path("a.MAP"))
    assert ext.can_handle(Path("a.CBS"))
    assert not ext.can_handle(Path("a.txt"))


def test_cics_map_node_and_fields():
    with tempfile.TemporaryDirectory() as d:
        p = _write(Path(d), BMS)
        res = CICSBMSExtractor().extract(p, codebase_id="default")
        maps = [n for n in res.nodes if n.type == NodeType.CICS_MAP]
        assert len(maps) == 1
        m = maps[0]
        assert m.name == "MAP01S"
        assert m.id == "CICSMap:default:MAP01S"
        fields = m.properties["fields"]
        assert len(fields) == 2
        assert fields[0]["name"] == "TITLE"
        assert fields[0]["length"] == 24
        assert fields[0]["pos"] == [1, 28]
        assert fields[0]["initial"] == "TITLE"
        assert fields[1]["name"] == "FLD1"
        assert fields[1]["attrb"] == ""


def test_logical_unit_one_with_64hex():
    with tempfile.TemporaryDirectory() as d:
        p = _write(Path(d), BMS)
        res = CICSBMSExtractor().extract(p, codebase_id="default")
        assert len(res.units) == 1
        u = res.units[0]
        assert u.kind == "bms_mapset"
        assert len(u.content_hash) == 64
        assert all(c in "0123456789abcdef" for c in u.content_hash)
        map_node = next(n for n in res.nodes if n.type == NodeType.CICS_MAP)
        assert len(map_node.content_hash) == 64


def test_partial_parse_malformed_field():
    with tempfile.TemporaryDirectory() as d:
        p = _write(Path(d), MALFORMED)
        res = CICSBMSExtractor().extract(p, codebase_id="default")
        maps = [n for n in res.nodes if n.type == NodeType.CICS_MAP]
        assert len(maps) == 1
        m = maps[0]
        assert m.parse_confidence < 1.0
        fields = m.properties["fields"]
        bad = next(f for f in fields if f["name"] == "BADFLD")
        assert bad["pos"] is None
        assert bad["length"] == 10
        assert "anomalies" in m.properties
        assert any("BADFLD" in a for a in m.properties["anomalies"])


def test_cbl_renders_on_edges():
    cbl = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. MENUAPP.
       PROCEDURE DIVISION.
           EXEC CICS SEND MAP('MAIN') END-EXEC.
           EXEC CICS RECEIVE MAP('MAIN') END-EXEC.
"""
    with tempfile.TemporaryDirectory() as d:
        p = _write(Path(d), cbl, name="menuapp.cbl")
        ext = CICSBMSExtractor()
        assert ext.can_handle(p)
        res = ext.extract(p, codebase_id="default")
        from mainframe_brain.graph.schema import EdgeType
        renders = [e for e in res.edges if e.type == EdgeType.RENDERS_ON]
        assert len(renders) == 1
        assert renders[0].dst == "CICSMap:default:MAIN"
        assert renders[0].src == "Program:default:MENUAPP"