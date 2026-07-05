from __future__ import annotations

from pathlib import Path

from mainframe_brain.extractors.cobol.extractor import CobolExtractor
from mainframe_brain.graph.schema import EdgeType, NodeType

COBOL_SAMPLE = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. DEMOPROG.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-AMOUNT      PIC 9(5).
       01  WS-RATE        PIC 9V99.
       PROCEDURE DIVISION.
       0000-MAIN.
           PERFORM 1000-SETUP
           PERFORM 2000-DO-WORK THRU 2999-DO-EXIT
           CALL "SUBPROG" USING WS-AMOUNT
           EXEC SQL
               SELECT AMOUNT INTO :WS-AMOUNT
               FROM ACCOUNTS
               WHERE ACCT_ID = :HV-ACCT
           END-EXEC
           GOBACK.
       1000-SETUP.
           MOVE 0 TO WS-AMOUNT.
       2000-DO-WORK.
           IF WS-AMOUNT > 0
               COMPUTE WS-AMOUNT = WS-AMOUNT * WS-RATE
           END-IF.
       2999-DO-EXIT.
           EXIT.
       9000-ERR.
           DISPLAY "ERR".
           GO TO 0000-MAIN.
"""


def _write(tmp_path: Path, name: str, text: str) -> Path:
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def test_cobol_smoke(tmp_path: Path) -> None:
    path = _write(tmp_path, "demoprog.cbl", COBOL_SAMPLE)
    result = CobolExtractor().extract(path, codebase_id="default")

    assert result.artifact_type == "cobol"
    programs = [n for n in result.nodes if n.type == NodeType.PROGRAM]
    assert len(programs) == 1
    assert programs[0].name == "DEMOPROG"
    assert programs[0].id == "Program:default:DEMOPROG"

    paragraphs = [n for n in result.nodes if n.type == NodeType.PARAGRAPH]
    para_names = {p.name for p in paragraphs}
    assert {"0000-MAIN", "1000-SETUP", "2000-DO-WORK", "2999-DO-EXIT", "9000-ERR"} <= para_names

    perf_edges = [e for e in result.edges if e.type == EdgeType.PERFORMS]
    assert len(perf_edges) >= 2
    assert any(e.dst.endswith(".1000-SETUP") for e in perf_edges)
    assert any(e.properties.get("thru") is True for e in perf_edges)

    call_edges = [e for e in result.edges if e.type == EdgeType.CALLS]
    assert len(call_edges) == 1
    assert call_edges[0].dst == "Program:default:SUBPROG"

    reads = [e for e in result.edges if e.type == EdgeType.READS]
    assert len(reads) == 1
    assert reads[0].dst == "DB2Table:default:ACCOUNTS"
    tables = [n for n in result.nodes if n.type == NodeType.DB2_TABLE]
    assert any(t.name == "ACCOUNTS" for t in tables)

    fields = [n for n in result.nodes if n.type == NodeType.FIELD]
    assert any(f.name == "WS-AMOUNT" for f in fields)
    assert any(f.name == "WS-RATE" for f in fields)

    assert len(result.units) >= 2
    for u in result.units:
        assert u.kind == "paragraph"
        assert len(u.content_hash) == 64
        assert all(c in "0123456789abcdef" for c in u.content_hash)


def test_cobol_goto_density_and_partial(tmp_path: Path) -> None:
    bad = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. BADPIC.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-X           PIC 9(2).
       01  WS-BAD         PIC @BAD@.
       PROCEDURE DIVISION.
       0000-MAIN.
           IF WS-X = 1
               GO TO 1000-ERR
           END-IF.
       1000-ERR.
           DISPLAY "E".
           GOBACK.
"""
    path = _write(tmp_path, "bad.cbl", bad)
    result = CobolExtractor().extract(path)

    fields = [n for n in result.nodes if n.type == NodeType.FIELD]
    bad_field = next(f for f in fields if f.name == "WS-BAD")
    assert bad_field.parse_confidence < 1.0


def test_cobol_includes_capture_replacing(tmp_path: Path) -> None:
    src = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. INCPROG.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       COPY ACCTFLDS REPLACING ==ACCT-ID== BY ==CUST-ID==.
       PROCEDURE DIVISION.
       0000-MAIN.
           GOBACK.
"""
    path = _write(tmp_path, "inc.cbl", src)
    result = CobolExtractor().extract(path)
    incs = [e for e in result.edges if e.type == EdgeType.INCLUDES]
    assert len(incs) == 1
    assert incs[0].dst == "Copybook:default:ACCTFLDS"
    assert incs[0].properties["replacing"] == [("ACCT-ID", "CUST-ID")]