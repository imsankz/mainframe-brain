from pathlib import Path

from mainframe_brain.cli import get_extractors
from mainframe_brain.extractors.db2_ddl.extractor import DB2DDLExtractor
from mainframe_brain.extractors.sql_pl.extractor import SQLPLExtractor
from mainframe_brain.extractors.triggers.extractor import TriggerExtractor
from mainframe_brain.graph.schema import NodeType
from mainframe_brain.graph.sqlite_store import SQLiteGraphStore

_EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "db2" / "schema.ddl"


def _db2_family_from_registry() -> list:
    wanted = {DB2DDLExtractor, SQLPLExtractor, TriggerExtractor}
    found = [ext for ext in get_extractors() if type(ext) in wanted]
    assert len(found) == 3, f"expected 3 DB2-family extractors in registry, got {len(found)}"
    return found


def _run(store_path: Path) -> SQLiteGraphStore:
    store = SQLiteGraphStore(str(store_path), codebase_id="default")
    for ext in _db2_family_from_registry():
        if not ext.can_handle(_EXAMPLE):
            continue
        res = ext.extract(_EXAMPLE, codebase_id="default")
        store.add_nodes(res.nodes)
        store.add_edges(res.edges)
    return store


def test_trigger_count_is_two(tmp_path):
    store = _run(tmp_path / "mb.db")
    triggers = [n for n in store.all_nodes() if n.type == NodeType.TRIGGER]
    assert {t.name for t in triggers} == {"TR_TXNLOG_AI", "TR_AUDITLOG_AI"}
    assert len(triggers) == 2
    store.close()


def test_stored_procedure_count_is_two(tmp_path):
    store = _run(tmp_path / "mb.db")
    procs = [n for n in store.all_nodes() if n.type == NodeType.STORED_PROCEDURE]
    assert {p.name for p in procs} == {"CALC_INTEREST", "LOG_EVENT"}
    assert len(procs) == 2
    store.close()


def test_db2_table_count_is_three(tmp_path):
    store = _run(tmp_path / "mb.db")
    tables = [n for n in store.all_nodes() if n.type == NodeType.DB2_TABLE]
    assert {t.name for t in tables} == {"ACCOUNTS", "TXNLOG", "AUDITLOG"}
    assert len(tables) == 3
    store.close()


def test_triggers_come_from_trigger_extractor_only(tmp_path):
    store = _run(tmp_path / "mb.db")
    triggers = [n for n in store.all_nodes() if n.type == NodeType.TRIGGER]
    for t in triggers:
        assert t.properties.get("timing"), f"{t.name} missing timing"
        assert t.properties.get("event"), f"{t.name} missing event"
        assert isinstance(t.properties.get("referencing"), list), f"{t.name} missing referencing"
        assert "note" not in t.properties, (
            f"{t.name} carries DDL-marker note — TriggerExtractor is not the sole owner"
        )
        assert t.content_hash, f"{t.name} has empty content_hash — likely DDL marker stub"
    store.close()


def test_no_node_id_collisions(tmp_path):
    store = _run(tmp_path / "mb.db")
    nodes = store.all_nodes()
    ids = [n.id for n in nodes]
    assert len(ids) == len(set(ids)), "duplicate node ids in store"
    store.close()