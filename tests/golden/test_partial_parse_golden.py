"""Golden fixture for gap #5.11 — partial-parse confidence reporting.

The extractor must NEVER silently drop a node on malformed input. A partial parse
emits a node with ``parse_confidence < 1.0`` and a non-empty ``anomalies`` list
instead of failing or swallowing the artifact. This fixture feeds an
unterminated ``EXEC SQL`` block (no ``END-EXEC``) and a malformed ``PIC`` clause
into the COBOL extractor and asserts:

* the extractor returns an ``ExtractionResult`` (no crash);
* the Program node still exists (not dropped) AND has ``parse_confidence < 1.0``;
* the Program node's ``properties["anomalies"]`` is non-empty and mentions the
  unterminated EXEC SQL block;
* a low-confidence Field node for the malformed PIC also survives.
"""
from __future__ import annotations

from pathlib import Path

from mainframe_brain.extractors.base import ExtractionResult
from mainframe_brain.extractors.cobol.extractor import CobolExtractor
from mainframe_brain.graph.schema import NodeType

# Fixed-format COBOL: column 7 (index 6) must be a space for a normal source
# line, otherwise _content_area treats the line as a continuation. Indents here
# keep the indicator column clean so the WS-field and EXEC SQL parsers engage.
_BROKEN = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. BROKEN.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-OK           PIC 9(4).
       01  WS-BAD          PIC @GARBAGE@.
       PROCEDURE DIVISION.
       0000-MAIN.
           EXEC SQL
               SELECT * FROM ACCOUNTS
           GOBACK.
"""


def _write(tmp_path: Path, name: str, text: str) -> Path:
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def test_partial_parse_does_not_crash(tmp_path: Path) -> None:
    path = _write(tmp_path, "BROKEN.cbl", _BROKEN)
    result = CobolExtractor().extract(path, codebase_id="default")
    assert isinstance(result, ExtractionResult)
    assert result.nodes, "extractor must return at least the Program node"


def test_partial_parse_program_node_low_confidence_with_anomalies(tmp_path: Path) -> None:
    path = _write(tmp_path, "BROKEN.cbl", _BROKEN)
    result = CobolExtractor().extract(path, codebase_id="default")

    programs = [n for n in result.nodes if n.type == NodeType.PROGRAM]
    assert len(programs) == 1, "Program node must exist (never silently dropped)"
    prog = programs[0]
    assert prog.name == "BROKEN"
    assert prog.parse_confidence < 1.0, "partial parse must lower parse_confidence"
    anomalies = prog.properties.get("anomalies")
    assert isinstance(anomalies, list) and anomalies, (
        "low-confidence Program must carry a non-empty anomalies list"
    )
    assert any("EXEC SQL" in a for a in anomalies), (
        "unterminated EXEC SQL block must be recorded as an anomaly"
    )


def test_partial_parse_malformed_field_survives_low_confidence(tmp_path: Path) -> None:
    path = _write(tmp_path, "BROKEN.cbl", _BROKEN)
    result = CobolExtractor().extract(path, codebase_id="default")

    fields = [n for n in result.nodes if n.type == NodeType.FIELD]
    bad = [f for f in fields if f.name == "WS-BAD"]
    assert bad, "malformed field node must exist (never silently dropped)"
    assert bad[0].parse_confidence < 1.0

    ok = [f for f in fields if f.name == "WS-OK"]
    assert ok and ok[0].parse_confidence == 1.0


def test_partial_parse_confidence_in_unit_range(tmp_path: Path) -> None:
    path = _write(tmp_path, "BROKEN.cbl", _BROKEN)
    result = CobolExtractor().extract(path, codebase_id="default")
    for n in result.nodes:
        assert 0.0 <= n.parse_confidence <= 1.0