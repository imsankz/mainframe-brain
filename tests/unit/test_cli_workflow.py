from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from mainframe_brain.cli import cli
from mainframe_brain.enrichment.cache import NarrationCache
from mainframe_brain.extractors.base import content_hash
from mainframe_brain.graph.schema import NodeType
from mainframe_brain.graph.sqlite_store import SQLiteGraphStore

_EXAMPLES = Path(__file__).resolve().parents[2] / "examples" / "cobol"


def _run(runner: CliRunner, store_path: str, *args) -> str:
    result = runner.invoke(
        cli, [*args, "--store-path", store_path] if "--store-path" not in args else list(args)
    )
    assert result.exit_code == 0, f"exit={result.exit_code} out={result.output}"
    return result.output


def _open(store_path: str) -> SQLiteGraphStore:
    return SQLiteGraphStore(store_path, codebase_id="default")


def _first_business_rule_id(store: SQLiteGraphStore, para_name: str | None = None) -> str:
    for n in store.all_nodes():
        if n.type == NodeType.BUSINESS_RULE and (para_name is None or para_name in n.name):
            return n.id
    raise AssertionError("no BusinessRule found")


def _paragraph_by_name(store: SQLiteGraphStore, name: str):
    for n in store.all_nodes():
        if n.type == NodeType.PARAGRAPH and n.name == name:
            return n
    raise AssertionError(f"no Paragraph named {name}")


def test_extract_then_triage_no_reenrichment_items(tmp_path):
    runner = CliRunner()
    db = str(tmp_path / "brain.db")

    out = runner.invoke(cli, ["extract", str(_EXAMPLES), "--out", db])
    assert out.exit_code == 0
    assert "Paragraph: 6" in out.output

    out = runner.invoke(cli, ["triage", "--store-path", db])
    assert out.exit_code == 0
    assert "work queue: 0 item(s)" in out.output


def test_enrich_then_triage_zero_cache_valid(tmp_path):
    runner = CliRunner()
    db = str(tmp_path / "brain.db")

    runner.invoke(cli, ["extract", str(_EXAMPLES), "--out", db])
    out = runner.invoke(cli, ["enrich", "--store-path", db, "--adapter", "mock", "--budget", "50000"])
    assert out.exit_code == 0
    assert "created: 6" in out.output

    out = runner.invoke(cli, ["triage", "--store-path", db])
    assert out.exit_code == 0
    assert "work queue: 0 item(s)" in out.output


def test_modify_paragraph_source_then_triage_one_changed(tmp_path):
    runner = CliRunner()
    db = str(tmp_path / "brain.db")

    runner.invoke(cli, ["extract", str(_EXAMPLES), "--out", db])
    runner.invoke(cli, ["enrich", "--store-path", db, "--adapter", "mock", "--budget", "50000"])

    store = _open(db)
    para = _paragraph_by_name(store, "2000-CALC-INTEREST")
    new_source = para.properties["source"] + "\n           DISPLAY \"CHANGED LINE\"."
    para.properties["source"] = new_source
    para.content_hash = content_hash(new_source)
    store.add_node(para)
    store.close()

    out = runner.invoke(cli, ["triage", "--store-path", db, "--threshold", "0.0"])
    assert out.exit_code == 0
    assert "work queue: 1 item(s)" in out.output
    assert "2000-CALC-INTEREST |" in out.output
    assert "| changed" in out.output

    out_json = runner.invoke(cli, ["triage", "--store-path", db, "--threshold", "0.0", "--json"])
    assert out_json.exit_code == 0
    payload = json.loads(out_json.output)
    assert payload["status"] == "ok"
    assert payload["command"] == "triage"
    assert payload["summary"]["skipped_count"] == 0
    assert len(payload["data"]) == 1
    assert payload["data"][0]["reason"] == "changed"
    assert payload["summary"]["budget_remaining"] == 50000 - payload["summary"]["total_tokens"]

    out = runner.invoke(cli, ["enrich", "--store-path", db, "--adapter", "mock", "--budget", "50000"])
    assert out.exit_code == 0
    assert "created: 1" in out.output

    out = runner.invoke(cli, ["triage", "--store-path", db, "--threshold", "0.0"])
    assert out.exit_code == 0
    assert "work queue: 0 item(s)" in out.output


def test_verify_marks_business_rule_and_cache(tmp_path):
    runner = CliRunner()
    db = str(tmp_path / "brain.db")

    runner.invoke(cli, ["extract", str(_EXAMPLES), "--out", db])
    runner.invoke(cli, ["enrich", "--store-path", db, "--adapter", "mock", "--budget", "50000"])

    store = _open(db)
    br_id = _first_business_rule_id(store)
    br = store.get_node(br_id)
    first_verified = br.last_verified
    store.close()

    out = runner.invoke(cli, ["verify", "--store-path", db, br_id])
    assert out.exit_code == 0
    assert f"verified: {br_id}" in out.output

    store = _open(db)
    br = store.get_node(br_id)
    assert br.properties["human_verified"] is True
    assert "flagged_reason" not in br.properties
    assert br.last_verified != first_verified
    cache = NarrationCache(store._conn)
    row = cache._conn.execute(
        "SELECT human_verified, stale FROM narration_cache WHERE content_hash = ?",
        (br.content_hash,),
    ).fetchone()
    assert row[0] == 1
    assert row[1] == 0
    store.close()


def test_flag_marks_business_rule_and_requeues_in_triage(tmp_path):
    runner = CliRunner()
    db = str(tmp_path / "brain.db")

    runner.invoke(cli, ["extract", str(_EXAMPLES), "--out", db])
    runner.invoke(cli, ["enrich", "--store-path", db, "--adapter", "mock", "--budget", "50000"])

    store = _open(db)
    br_id = _first_business_rule_id(store)
    br_hash = store.get_node(br_id).content_hash
    store.close()

    out = runner.invoke(cli, ["flag", "--store-path", db, "--rule", br_id, "--reason", "wrong edge case"])
    assert out.exit_code == 0
    assert "flagged:" in out.output

    store = _open(db)
    br = store.get_node(br_id)
    assert br.properties["human_verified"] is False
    assert br.properties["flagged_reason"] == "wrong edge case"
    assert "flagged_at" in br.properties
    assert NarrationCache(store._conn).is_stale(br_hash)
    store.close()

    out = runner.invoke(cli, ["triage", "--store-path", db, "--threshold", "0.0"])
    assert out.exit_code == 0
    assert "work queue: 1 item(s)" in out.output
    assert "| stale" in out.output


def test_edit_rule_replaces_text_and_marks_verified(tmp_path):
    runner = CliRunner()
    db = str(tmp_path / "brain.db")

    runner.invoke(cli, ["extract", str(_EXAMPLES), "--out", db])
    runner.invoke(cli, ["enrich", "--store-path", db, "--adapter", "mock", "--budget", "50000"])

    store = _open(db)
    br_id = _first_business_rule_id(store)
    br_hash = store.get_node(br_id).content_hash
    store.close()

    out = runner.invoke(
        cli,
        [
            "edit-rule",
            "--store-path",
            db,
            "--rule",
            br_id,
            "--rule-text",
            "Manual override: rate is annual.",
        ],
    )
    assert out.exit_code == 0
    assert f"edited: {br_id}" in out.output

    store = _open(db)
    br = store.get_node(br_id)
    assert br.properties["rule"] == "Manual override: rate is annual."
    assert br.properties["human_verified"] is True
    assert br.properties["edited_by_human"] is True
    cache = NarrationCache(store._conn)
    payload = cache.get(br_hash)
    assert payload is not None
    assert payload["rule"] == "Manual override: rate is annual."
    assert payload["human_verified"] is True
    assert not cache.is_stale(br_hash)
    store.close()

    out = runner.invoke(cli, ["triage", "--store-path", db, "--threshold", "0.0"])
    assert out.exit_code == 0
    assert "work queue: 0 item(s)" in out.output


def test_build_graph_counts(tmp_path):
    runner = CliRunner()
    db = str(tmp_path / "brain.db")

    runner.invoke(cli, ["extract", str(_EXAMPLES), "--out", db])

    out = runner.invoke(cli, ["build-graph", "--store-path", db])
    assert out.exit_code == 0
    assert "Paragraph: 6" in out.output
    assert "PERFORMS:" in out.output
    assert "logical units discoverable: 6" in out.output


def test_build_command_extracts_and_reports_accessible_summary(tmp_path):
    runner = CliRunner()
    db = str(tmp_path / "brain.db")

    out = runner.invoke(cli, ["build", str(_EXAMPLES), "--out", db, "--json"])
    assert out.exit_code == 0
    payload = json.loads(out.output)
    assert payload["status"] == "ok"
    assert payload["command"] == "build"
    assert payload["summary"]["logical_units"] > 0
    assert payload["summary"]["nodes_by_type"]["Paragraph"] > 0
    assert payload["summary"]["accessible_nodes"][0]["type"] in {"Program", "Paragraph", "BusinessRule"}


def test_list_nodes_json_includes_descriptive_fields(tmp_path):
    runner = CliRunner()
    db = str(tmp_path / "brain.db")

    runner.invoke(cli, ["build", str(_EXAMPLES), "--out", db])

    out = runner.invoke(cli, ["list-nodes", "--store-path", db, "--json"])
    assert out.exit_code == 0
    payload = json.loads(out.output)
    assert payload["status"] == "ok"
    assert payload["summary"]["count"] > 0
    assert payload["data"][0]["id"]
    assert payload["data"][0]["name"]
    assert payload["data"][0]["type"]


def test_build_graph_reports_risk_and_hub_summary(tmp_path):
    runner = CliRunner()
    db = str(tmp_path / "brain.db")

    runner.invoke(cli, ["extract", str(_EXAMPLES), "--out", db])

    out = runner.invoke(cli, ["build-graph", "--store-path", db, "--json"])
    assert out.exit_code == 0
    payload = json.loads(out.output)
    assert payload["status"] == "ok"
    assert payload["summary"]["top_risk_nodes"]
    assert payload["summary"]["hub_nodes"]


def test_impact_command_returns_blast_radius(tmp_path):
    runner = CliRunner()
    db = str(tmp_path / "brain.db")

    runner.invoke(cli, ["extract", str(_EXAMPLES), "--out", db])

    out = runner.invoke(cli, ["impact", "--store-path", db, "--node", "Program:default:INTCALC01", "--json"])
    assert out.exit_code == 0
    payload = json.loads(out.output)
    assert payload["status"] == "ok"
    assert payload["summary"]["target"] == "Program:default:INTCALC01"
    assert payload["summary"]["impact_count"] >= 1
    assert payload["data"][0]["node"]