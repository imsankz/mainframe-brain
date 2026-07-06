"""End-to-end integration test: extract → triage → enrich → query → verify → flag → edit."""
from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from mainframe_brain.cli import cli
from mainframe_brain.enrichment.cache import NarrationCache
from mainframe_brain.graph.schema import EdgeType, NodeType
from mainframe_brain.graph.sqlite_store import SQLiteGraphStore

_EXAMPLES_COBOL = Path(__file__).resolve().parents[2] / "examples" / "cobol"


def _run(runner: CliRunner, store_path: str, *args: str) -> str:
    result = runner.invoke(cli, [*args, "--store-path", store_path])
    assert result.exit_code == 0, f"exit={result.exit_code} out={result.output}"
    return result.output


def _open(store_path: str) -> SQLiteGraphStore:
    return SQLiteGraphStore(store_path, codebase_id="default")


# ---------------------------------------------------------------------------
# Stage 1 — extract
# ---------------------------------------------------------------------------


def test_full_pipeline_extract_creates_nodes_and_edges(tmp_path: Path) -> None:
    runner = CliRunner()
    db = str(tmp_path / "brain.db")

    out = runner.invoke(cli, ["extract", str(_EXAMPLES_COBOL), "--out", db])
    assert out.exit_code == 0, f"extract failed: {out.output}"
    assert "Paragraph:" in out.output

    store = _open(db)
    nodes = store.all_nodes()
    edges = store.all_edges()

    # Assert we have expected node types
    node_types = {n.type for n in nodes}
    assert NodeType.PROGRAM in node_types
    assert NodeType.PARAGRAPH in node_types
    assert NodeType.COPYBOOK in node_types
    assert NodeType.FIELD in node_types

    # Assert specific nodes exist
    node_ids = {n.id for n in nodes}
    assert "Program:default:INTCALC01" in node_ids
    assert "Paragraph:default:INTCALC01.2000-CALC-INTEREST" in node_ids
    assert "Paragraph:default:INTCALC01.9000-ERROR" in node_ids
    assert "Copybook:default:ACCTFLDS" in node_ids

    # Assert edges exist
    edge_types = {e.type for e in edges}
    assert EdgeType.PERFORMS in edge_types
    assert EdgeType.INCLUDES in edge_types
    assert EdgeType.READS in edge_types

    # Verify PERFORMS edges: MAIN calls INIT, CALC, WRITE
    performs_edges = [e for e in edges if e.type == EdgeType.PERFORMS]
    performs_dsts = {e.dst for e in performs_edges}
    assert "Paragraph:default:INTCALC01.1000-INIT" in performs_dsts
    assert "Paragraph:default:INTCALC01.2000-CALC-INTEREST" in performs_dsts
    assert "Paragraph:default:INTCALC01.3000-WRITE-RESULT" in performs_dsts

    store.close()


# ---------------------------------------------------------------------------
# Stage 2 — triage (fresh DB: all paragraphs are "new")
# ---------------------------------------------------------------------------


def test_full_pipeline_triage_before_enrich(tmp_path: Path) -> None:
    runner = CliRunner()
    db = str(tmp_path / "brain.db")

    runner.invoke(cli, ["extract", str(_EXAMPLES_COBOL), "--out", db])

    out = runner.invoke(cli, ["triage", "--store-path", db])
    assert out.exit_code == 0
    # Triage only shows re-enrichment items (not "new") so queue is empty
    assert "work queue: 0 item(s)" in out.output


# ---------------------------------------------------------------------------
# Stage 3 — enrich with mock adapter
# ---------------------------------------------------------------------------


def test_full_pipeline_enrich_creates_business_rules(tmp_path: Path) -> None:
    runner = CliRunner()
    db = str(tmp_path / "brain.db")

    runner.invoke(cli, ["extract", str(_EXAMPLES_COBOL), "--out", db])
    out = runner.invoke(
        cli, ["enrich", "--store-path", db, "--adapter", "mock", "--budget", "50000"]
    )
    assert out.exit_code == 0, f"enrich failed: {out.output}"
    assert "created: 6" in out.output

    store = _open(db)
    nodes = store.all_nodes()
    edges = store.all_edges()

    # Assert BusinessRule nodes were created
    business_rules = [n for n in nodes if n.type == NodeType.BUSINESS_RULE]
    assert len(business_rules) == 6

    for br in business_rules:
        assert br.properties.get("human_verified") is False
        assert "confidence" in br.properties
        assert "rule" in br.properties

    # Assert IMPLEMENTS_RULE edges exist
    implements_edges = [e for e in edges if e.type == EdgeType.IMPLEMENTS_RULE]
    assert len(implements_edges) == 6

    # Verify a BusinessRule for CALC-INTEREST exists
    calc_rules = [br for br in business_rules if "CALC-INTEREST" in br.name]
    assert len(calc_rules) >= 1
    calc_rule = calc_rules[0]
    assert calc_rule.properties["confidence"] == 0.5

    store.close()


# ---------------------------------------------------------------------------
# Stage 4 — query "what runs INTCALC01"
# ---------------------------------------------------------------------------


def test_full_pipeline_query_what_runs(tmp_path: Path) -> None:
    runner = CliRunner()
    db = str(tmp_path / "brain.db")

    runner.invoke(cli, ["extract", str(_EXAMPLES_COBOL), "--out", db])
    runner.invoke(cli, ["enrich", "--store-path", db, "--adapter", "mock", "--budget", "50000"])

    out = runner.invoke(cli, ["query", "--store-path", db, "what runs INTCALC01"])
    assert out.exit_code == 0
    assert "INTCALC01 is invoked by" in out.output


# ---------------------------------------------------------------------------
# Stage 5 — verify a BusinessRule
# ---------------------------------------------------------------------------


def test_full_pipeline_verify_business_rule(tmp_path: Path) -> None:
    runner = CliRunner()
    db = str(tmp_path / "brain.db")

    runner.invoke(cli, ["extract", str(_EXAMPLES_COBOL), "--out", db])
    runner.invoke(cli, ["enrich", "--store-path", db, "--adapter", "mock", "--budget", "50000"])

    store = _open(db)
    brs = [n for n in store.all_nodes() if n.type == NodeType.BUSINESS_RULE]
    assert brs, "expected at least one BusinessRule"
    br_id = brs[0].id
    store.close()

    out = runner.invoke(cli, ["verify", "--store-path", db, br_id])
    assert out.exit_code == 0
    assert f"verified: {br_id}" in out.output

    store = _open(db)
    br = store.get_node(br_id)
    assert br is not None
    assert br.properties.get("human_verified") is True
    assert "flagged_reason" not in br.properties

    cache = NarrationCache(store._conn)
    assert not cache.is_stale(br.content_hash)
    store.close()


# ---------------------------------------------------------------------------
# Stage 6 — flag a BusinessRule
# ---------------------------------------------------------------------------


def test_full_pipeline_flag_business_rule(tmp_path: Path) -> None:
    runner = CliRunner()
    db = str(tmp_path / "brain.db")

    runner.invoke(cli, ["extract", str(_EXAMPLES_COBOL), "--out", db])
    runner.invoke(cli, ["enrich", "--store-path", db, "--adapter", "mock", "--budget", "50000"])

    store = _open(db)
    brs = [n for n in store.all_nodes() if n.type == NodeType.BUSINESS_RULE]
    br = brs[0]  # Pick first rule
    br_id = br.id
    br_hash = br.content_hash
    store.close()

    out = runner.invoke(
        cli,
        ["flag", "--store-path", db, "--rule", br_id, "--reason", "needs SME review"],
    )
    assert out.exit_code == 0
    assert "flagged:" in out.output

    store = _open(db)
    br = store.get_node(br_id)
    assert br is not None
    assert br.properties.get("human_verified") is False
    assert br.properties.get("flagged_reason") == "needs SME review"
    assert "flagged_at" in br.properties
    assert NarrationCache(store._conn).is_stale(br_hash)
    store.close()

    # Triage should now show the rule as "stale"
    out = runner.invoke(cli, ["triage", "--store-path", db, "--threshold", "0.0"])
    assert out.exit_code == 0
    assert "work queue: 1 item(s)" in out.output
    assert "| stale" in out.output


# ---------------------------------------------------------------------------
# Stage 7 — edit a BusinessRule
# ---------------------------------------------------------------------------


def test_full_pipeline_edit_business_rule(tmp_path: Path) -> None:
    runner = CliRunner()
    db = str(tmp_path / "brain.db")

    runner.invoke(cli, ["extract", str(_EXAMPLES_COBOL), "--out", db])
    runner.invoke(cli, ["enrich", "--store-path", db, "--adapter", "mock", "--budget", "50000"])

    store = _open(db)
    brs = [n for n in store.all_nodes() if n.type == NodeType.BUSINESS_RULE]
    br = brs[0]
    br_id = br.id
    br_hash = br.content_hash
    store.close()

    new_text = "Manual override: interest is calculated quarterly."
    out = runner.invoke(
        cli,
        [
            "edit-rule",
            "--store-path", db,
            "--rule", br_id,
            "--rule-text", new_text,
        ],
    )
    assert out.exit_code == 0
    assert f"edited: {br_id}" in out.output

    store = _open(db)
    br = store.get_node(br_id)
    assert br is not None
    assert br.properties.get("rule") == new_text
    assert br.properties.get("human_verified") is True
    assert br.properties.get("edited_by_human") is True

    cache = NarrationCache(store._conn)
    payload = cache.get(br_hash)
    assert payload is not None
    assert payload.get("rule") == new_text
    assert not cache.is_stale(br_hash)
    store.close()

    # After edit, triage should show zero items (rule is verified, not stale)
    out = runner.invoke(cli, ["triage", "--store-path", db])
    assert out.exit_code == 0
    assert "work queue: 0 item(s)" in out.output


# ---------------------------------------------------------------------------
# Stage 8 — enrichment queue state is persisted and resumable
# ---------------------------------------------------------------------------


def test_full_pipeline_enrichment_queue_persistence(tmp_path: Path) -> None:
    """Verify the enrichment_queue table is populated and has correct state after enrich."""
    runner = CliRunner()
    db = str(tmp_path / "brain.db")

    runner.invoke(cli, ["extract", str(_EXAMPLES_COBOL), "--out", db])
    runner.invoke(cli, ["enrich", "--store-path", db, "--adapter", "mock", "--budget", "50000"])

    store = _open(db)

    # Check enrichment_queue table exists and all items are 'done'
    rows = store._conn.execute("SELECT status, COUNT(*) as cnt FROM enrichment_queue GROUP BY status").fetchall()
    statuses = {r["status"]: r["cnt"] for r in rows}
    assert statuses.get("done", 0) == 6, f"expected 6 done items, got {statuses}"
    assert statuses.get("pending", 0) == 0
    assert statuses.get("in_progress", 0) == 0

    store.close()
