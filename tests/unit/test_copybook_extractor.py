from __future__ import annotations

from pathlib import Path

from mainframe_brain.extractors.base import content_hash
from mainframe_brain.extractors.copybook.expansion import expand_copybook
from mainframe_brain.extractors.copybook.extractor import CopybookExtractor
from mainframe_brain.graph.schema import NodeType

CPY_SAMPLE = """\
       01  ACCT-RECORD.
           05  ACCT-ID            PIC 9(8).
           05  ACCT-BALANCE       PIC 9(11)V99.
           05  ACCT-FLAGS         PIC X(1)
                                   OCCURS 3 TIMES.
           05  ACCT-FLAG-REDEF    REDEFINES ACCT-FLAGS
                                   PIC 9(3).
           05  ACCT-STATUS        PIC X(1).
               88  ACTIVE-ACCT    VALUE "A".
               88  CLOSED-ACCT    VALUE "C".
"""


def _write(tmp_path: Path, name: str, text: str) -> Path:
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def test_copybook_basic(tmp_path: Path) -> None:
    path = _write(tmp_path, "ACCTFLDS.cpy", CPY_SAMPLE)
    result = CopybookExtractor().extract(path, codebase_id="default")

    assert result.artifact_type == "copybook"
    cbs = [n for n in result.nodes if n.type == NodeType.COPYBOOK]
    assert len(cbs) == 1
    assert cbs[0].name == "ACCTFLDS"
    assert cbs[0].id == "Copybook:default:ACCTFLDS"

    fields = [n for n in result.nodes if n.type == NodeType.FIELD]
    names = {f.name for f in fields}
    assert {"ACCT-ID", "ACCT-BALANCE", "ACCT-FLAGS", "ACCT-FLAG-REDEF", "ACCT-STATUS"} <= names

    redef = next(f for f in fields if f.name == "ACCT-FLAG-REDEF")
    assert redef.properties["redefines"] == "ACCT-FLAGS"

    occ = next(f for f in fields if f.name == "ACCT-FLAGS")
    assert occ.properties["occurs"] == 3

    status = next(f for f in fields if f.name == "ACCT-STATUS")
    assert "ACTIVE-ACCT" in status.properties.get("condition_names", [])
    assert "CLOSED-ACCT" in status.properties.get("condition_names", [])

    assert len(result.units) == 1
    assert result.units[0].kind == "copybook"
    assert len(result.units[0].content_hash) == 64


def test_expand_copybook_placeholder_substitution() -> None:
    raw = "             05  ==X==            PIC 9(2)."
    expanded = expand_copybook(raw, [("X", "YY")])
    assert "==X==" not in expanded
    assert "YY" in expanded


def test_expand_copybook_changes_hash() -> None:
    raw = "             05  FIELD-X PIC 9(2)."
    expanded = expand_copybook(raw, [("X", "YY")])
    h_raw = content_hash(raw)
    h_exp = content_hash(expanded)
    assert h_raw == content_hash(raw)
    assert h_exp == h_exp
    expanded2 = expand_copybook(raw, [("X", "ZZ")])
    assert content_hash(expanded2) != content_hash(raw) or raw == expanded2


def test_copybook_partial_pic_emits_low_confidence(tmp_path: Path) -> None:
    bad = """\
       01  BAD-FIELD      PIC @NOPE@.
"""
    path = _write(tmp_path, "BAD.cpy", bad)
    result = CopybookExtractor().extract(path)
    fields = [n for n in result.nodes if n.type == NodeType.FIELD]
    assert any(f.name == "BAD-FIELD" for f in fields)
    bad_field = next(f for f in fields if f.name == "BAD-FIELD")
    assert bad_field.parse_confidence < 1.0
    cbs = [n for n in result.nodes if n.type == NodeType.COPYBOOK]
    assert cbs[0].parse_confidence < 1.0