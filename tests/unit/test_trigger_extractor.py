import tempfile
from pathlib import Path

from mainframe_brain.extractors.triggers.extractor import TriggerExtractor
from mainframe_brain.graph.schema import EdgeType, NodeType
from mainframe_brain.graph.store import make_node_id

TRIG = """
CREATE TRIGGER TR_TXNLOG_AI
    AFTER INSERT ON TXNLOG
    REFERENCING NEW AS N
    FOR EACH ROW MODE DB2SQL
BEGIN
    INSERT INTO AUDITLOG (AUDIT_ID, ACCT_ID, WHO, WHAT, WHEN_TS)
        VALUES (3, N.ACCT_ID, 'TXN', 'INSERT', CURRENT_TIMESTAMP);
END;

CREATE TRIGGER TR_AUDITLOG_AI
    AFTER INSERT ON AUDITLOG
    REFERENCING NEW AS N
    FOR EACH ROW MODE DB2SQL
BEGIN
    UPDATE SUMMARY SET LAST_EVENT = N.WHAT, LAST_TS = N.WHEN_TS;
END;
"""


def _write(d: Path) -> Path:
    p = d / "triggers.sql"
    p.write_text(TRIG)
    return p


def test_emits_two_trigger_nodes():
    with tempfile.TemporaryDirectory() as d:
        p = _write(Path(d))
        res = TriggerExtractor().extract(p, codebase_id="default")
        triggers = [n for n in res.nodes if n.type == NodeType.TRIGGER]
        assert {t.name for t in triggers} == {"TR_TXNLOG_AI", "TR_AUDITLOG_AI"}
        t1 = next(t for t in triggers if t.name == "TR_TXNLOG_AI")
        assert t1.properties["timing"] == "AFTER"
        assert t1.properties["base_event"] == "INSERT"
        assert t1.properties["table"] == "TXNLOG"
        assert t1.properties["referencing"] == [{"which": "NEW", "alias": "N"}]


def test_fires_on_edges():
    with tempfile.TemporaryDirectory() as d:
        p = _write(Path(d))
        res = TriggerExtractor().extract(p, codebase_id="default")
        fires = [e for e in res.edges if e.type == EdgeType.FIRES_ON]
        targets = {e.dst for e in fires}
        assert make_node_id("DB2Table", "default", "TXNLOG") in targets
        assert make_node_id("DB2Table", "default", "AUDITLOG") in targets


def test_trigger_trigger_chain_inferred():
    with tempfile.TemporaryDirectory() as d:
        p = _write(Path(d))
        res = TriggerExtractor().extract(p, codebase_id="default")
        t1_id = make_node_id("Trigger", "default", "TR_TXNLOG_AI")
        chain_edges = [e for e in res.edges
                       if e.type == EdgeType.TRIGGERS_TRIGGER and e.src == t1_id]
        assert len(chain_edges) == 1
        e = chain_edges[0]
        assert e.dst == "Trigger:default:ON:AUDITLOG:INSERT"
        assert e.properties["inferred"] is True
        assert e.properties["target_table"] == "AUDITLOG"
        assert e.properties["target_event"] == "INSERT"