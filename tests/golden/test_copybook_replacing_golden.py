"""Golden fixture for gap #2 — COPY...REPLACING post-expansion hashing.

Phase 1 of the extractor does NOT inline copybook text into paragraph source
(COPY resolution is deferred). The post-expansion hashing contract is therefore
asserted at the unit level against ``expand_copybook`` / ``post_expansion_source``:
two programs importing the SAME copybook file with DIFFERENT REPLACING pairs must
produce different expanded text and different content hashes. Hashing the raw
copybook file would cache LLM narrations against the wrong field names.

The extractor-level half of the contract — that ``replacing_applied`` /
``post_expansion`` flags are set whenever COPY...REPLACING is captured — is also
asserted so the gap-#2 wiring is covered end-to-end at the extraction layer.
"""
from __future__ import annotations

from pathlib import Path

from mainframe_brain.extractors.base import content_hash
from mainframe_brain.extractors.cobol.extractor import CobolExtractor
from mainframe_brain.extractors.copybook.expansion import (
    expand_copybook,
    post_expansion_hash,
    post_expansion_source,
)
from mainframe_brain.graph.schema import EdgeType, NodeType

# Copybook text is plain COR text consumed directly by expand_copybook
# (Phase 1 does not inline copybooks into paragraph source). Indentation is
# cosmetic here — the placeholder tokens are what drive the substitution.
_COPYBOOK = """\
01 ACCT-RECORD.
   05 ==ACCT-ID== PIC 9(8).
   05 ACCT-NAME   PIC X(30).
"""

# Fixed-format COBOL: column 7 (index 6) is a space for a normal source line
# so _content_area treats the line as a normal area-A/B source line.
_PROGA = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. PROGA.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       COPY ACCTFLDS REPLACING ==ACCT-ID== BY ==CUST-ID==.
       PROCEDURE DIVISION.
       0000-MAIN.
           GOBACK.
"""

_PROGB = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. PROGB.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       COPY ACCTFLDS REPLACING ==ACCT-ID== BY ==CLIENT-NO==.
       PROCEDURE DIVISION.
       0000-MAIN.
           GOBACK.
"""


def _write(tmp_path: Path, name: str, text: str) -> Path:
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def test_post_expansion_hashing_contract_unit() -> None:
    """Same copybook, different REPLACING → different text + different hashes."""
    pairs_a: list[tuple[str, str]] = [("ACCT-ID", "CUST-ID")]
    pairs_b: list[tuple[str, str]] = [("ACCT-ID", "CLIENT-NO")]

    expanded_a = expand_copybook(_COPYBOOK, pairs_a)
    expanded_b = expand_copybook(_COPYBOOK, pairs_b)
    raw_expanded = expand_copybook(_COPYBOOK, [])

    assert expanded_a != expanded_b, "different REPLACING pairs must diverge"
    assert "CUST-ID" in expanded_a and "==ACCT-ID==" not in expanded_a
    assert "CLIENT-NO" in expanded_b and "==ACCT-ID==" not in expanded_b
    assert expanded_a != raw_expanded, "REPLACING must actually mutate text"
    assert expanded_b != raw_expanded

    hash_a = content_hash(expanded_a)
    hash_b = content_hash(expanded_b)
    hash_raw = content_hash(raw_expanded)

    assert hash_a != hash_b, (
        "gap #2: identical raw copybook file, different expanded text, "
        "different cache key — content_hash must differ"
    )
    assert hash_a != hash_raw
    assert hash_b != hash_raw
    assert len(hash_a) == 64 and len(hash_b) == 64


def test_post_expansion_source_and_hash_helpers() -> None:
    """post_expansion_source / post_expansion_hash honor REPLACING."""
    para_source = "0000-MAIN.\nMOVE ==ACCT-ID== TO WS-X."
    a = post_expansion_source(para_source, [("ACCT-ID", "CUST-ID")])
    b = post_expansion_source(para_source, [("ACCT-ID", "CLIENT-NO")])
    assert a != b
    assert post_expansion_hash(para_source, [("ACCT-ID", "CUST-ID")]) != (
        post_expansion_hash(para_source, [("ACCT-ID", "CLIENT-NO")])
    )
    # empty replacing is a no-op pass-through
    assert post_expansion_source(para_source, []) == para_source


def test_extractor_flags_replacing_applied_per_program(tmp_path: Path) -> None:
    """Gap #2 wiring: each program that uses COPY REPLACING marks its paragraphs.

    Phase 1 does not inline copybook text, so paragraph content_hashes are equal
    here (identical paragraph body). The contract that DIFFERENT REPLACING pairs
    produce DIFFERENT hashes is proven at the unit level above, against the
    actual copybook text where the placeholders live. This test locks the
    extractor's per-program flagging so a regression that drops ``replacing_all``
    is caught immediately.
    """
    pa = _write(tmp_path, "PROGA.cbl", _PROGA)
    pb = _write(tmp_path, "PROGB.cbl", _PROGB)
    _write(tmp_path, "ACCTFLDS.cpy", _COPYBOOK)

    res_a = CobolExtractor().extract(pa, codebase_id="default")
    res_b = CobolExtractor().extract(pb, codebase_id="default")

    inc_a = [e for e in res_a.edges if e.type == EdgeType.INCLUDES]
    inc_b = [e for e in res_b.edges if e.type == EdgeType.INCLUDES]
    assert len(inc_a) == 1 and len(inc_b) == 1
    assert inc_a[0].properties["replacing"] == [("ACCT-ID", "CUST-ID")]
    assert inc_b[0].properties["replacing"] == [("ACCT-ID", "CLIENT-NO")]

    paras_a = [n for n in res_a.nodes if n.type == NodeType.PARAGRAPH]
    paras_b = [n for n in res_b.nodes if n.type == NodeType.PARAGRAPH]
    assert paras_a and paras_b
    for p in paras_a:
        assert p.properties["replacing_applied"] is True
        assert p.properties["post_expansion"] is True
    for p in paras_b:
        assert p.properties["replacing_applied"] is True
        assert p.properties["post_expansion"] is True
    for u in res_a.units:
        assert u.post_expansion is True
    for u in res_b.units:
        assert u.post_expansion is True