"""list-nodes --low-confidence filter (gap #5.11 surfacing).

Verifies the CLI flag composes with --type and prints ONLY partial-parse
survivors (parse_confidence < 1.0). Uses the real CliRunner against a
SQLiteGraphStore so the contract is proven end-to-end.
"""
from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from mainframe_brain.cli import cli
from mainframe_brain.graph.schema import Node, NodeType
from mainframe_brain.graph.sqlite_store import SQLiteGraphStore

_EXAMPLES = Path(__file__).resolve().parents[2] / "examples" / "cobol"


def _run(store_path: str, *args: str) -> str:
    runner = CliRunner()
    res = runner.invoke(cli, ["list-nodes", "--store-path", store_path, *args])
    assert res.exit_code == 0, res.output
    return res.output


def test_low_confidence_prints_nothing_for_clean_examples(tmp_path: Path) -> None:
    store_path = str(tmp_path / "clean.db")
    runner = CliRunner()
    res = runner.invoke(
        cli, ["extract", str(_EXAMPLES), "--out", store_path]
    )
    assert res.exit_code == 0, res.output

    paragraphs_only = _run(store_path, "--low-confidence", "--type", "Paragraph")
    assert paragraphs_only.strip() == "", "clean paragraphs must not be low-confidence"


def test_low_confidence_prints_injected_partial_node(tmp_path: Path) -> None:
    store_path = str(tmp_path / "injected.db")
    store = SQLiteGraphStore(store_path)
    clean = Node(
        id="Paragraph:default:CLEAN",
        type=NodeType.PARAGRAPH,
        name="CLEAN",
        codebase_id="default",
        content_hash="a" * 64,
        parse_confidence=1.0,
        properties={"source": "CLEAN."},
    )
    partial = Node(
        id="Paragraph:default:BROKEN",
        type=NodeType.PARAGRAPH,
        name="BROKEN",
        codebase_id="default",
        content_hash="b" * 64,
        parse_confidence=0.5,
        properties={"source": "BROKEN.", "anomalies": ["unterminated EXEC SQL"]},
    )
    store.add_node(clean)
    store.add_node(partial)
    store.close()

    out = _run(store_path, "--low-confidence")
    assert "Paragraph:default:BROKEN" in out
    assert "Paragraph:default:CLEAN" not in out
    assert "conf=0.50" in out
    assert "conf=1.00" not in out


def test_low_confidence_composes_with_type(tmp_path: Path) -> None:
    store_path = str(tmp_path / "mixed.db")
    store = SQLiteGraphStore(store_path)
    store.add_node(
        Node(
            id="Program:default:LOWP",
            type=NodeType.PROGRAM,
            name="LOWP",
            codebase_id="default",
            parse_confidence=0.5,
            properties={},
        )
    )
    store.add_node(
        Node(
            id="Paragraph:default:LOWPS",
            type=NodeType.PARAGRAPH,
            name="LOWPS",
            codebase_id="default",
            parse_confidence=0.5,
            properties={},
        )
    )
    store.close()

    out = _run(store_path, "--low-confidence", "--type", "Paragraph")
    assert "Paragraph:default:LOWPS" in out
    assert "Program:default:LOWP" not in out