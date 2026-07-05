import tempfile
from pathlib import Path

from mainframe_brain.extractors.sql_pl.extractor import SQLPLExtractor
from mainframe_brain.graph.schema import EdgeType, NodeType
from mainframe_brain.graph.store import make_node_id

PROC = """
CREATE PROCEDURE CALC_INTEREST
    (IN P_ACCT BIGINT, IN P_RATE DECIMAL(5,4), OUT P_INT DECIMAL(18,2))
    LANGUAGE SQL
    DYNAMIC RESULT SETS 0
BEGIN
    DECLARE V_BAL DECIMAL(18,2);
    SELECT BALANCE INTO V_BAL FROM ACCOUNTS WHERE ACCT_ID = P_ACCT;
    IF V_BAL > 0 THEN
        WHILE V_BAL < 1000000 DO
            SET V_BAL = V_BAL * (1 + P_RATE);
        END WHILE;
    END IF;
    SET P_INT = V_BAL * P_RATE;
    INSERT INTO TXNLOG (TXN_ID, ACCT_ID, TXN_AMT, TXN_TS)
        VALUES (1, P_ACCT, P_INT, CURRENT_TIMESTAMP);
    CALL LOG_EVENT ('INTEREST');
END PROCEDURE;

CREATE PROCEDURE LOG_EVENT (IN P_EVT VARCHAR(64))
    LANGUAGE SQL
BEGIN
    INSERT INTO AUDITLOG (AUDIT_ID, ACCT_ID, WHO, WHAT, WHEN_TS)
        VALUES (2, NULL, 'SYS', P_EVT, CURRENT_TIMESTAMP);
END PROCEDURE;
"""


def _write(d: Path) -> Path:
    p = d / "procs.sql"
    p.write_text(PROC)
    return p


def test_proc_node_params_complexity():
    with tempfile.TemporaryDirectory() as d:
        p = _write(Path(d))
        res = SQLPLExtractor().extract(p, codebase_id="default")
        procs = [n for n in res.nodes if n.type == NodeType.STORED_PROCEDURE]
        names = {n.name for n in procs}
        assert names == {"CALC_INTEREST", "LOG_EVENT"}

        calc = next(n for n in procs if n.name == "CALC_INTEREST")
        props = calc.properties
        assert props["language"] == "SQL PL"
        params = props["parameters"]
        assert len(params) == 3
        pmodes = {p["name"]: p["mode"] for p in params}
        assert pmodes["P_ACCT"] == "IN"
        assert pmodes["P_INT"] == "OUT"
        assert props["complexity_score"] >= 3


def test_proc_writes_and_invokes():
    with tempfile.TemporaryDirectory() as d:
        p = _write(Path(d))
        res = SQLPLExtractor().extract(p, codebase_id="default")
        calc_id = make_node_id("StoredProcedure", "default", "CALC_INTEREST")

        writes = [e for e in res.edges
                  if e.src == calc_id and e.type == EdgeType.WRITES]
        write_targets = {e.dst for e in writes}
        assert make_node_id("DB2Table", "default", "TXNLOG") in write_targets

        reads = [e for e in res.edges
                 if e.src == calc_id and e.type == EdgeType.READS]
        read_targets = {e.dst for e in reads}
        assert make_node_id("DB2Table", "default", "ACCOUNTS") in read_targets

        invokes = [e for e in res.edges
                   if e.src == calc_id and e.type == EdgeType.INVOKES_PROC]
        invoke_targets = {e.dst for e in invokes}
        assert make_node_id("StoredProcedure", "default", "LOG_EVENT") in invoke_targets


def test_can_handle_false_for_non_proc_sql(tmp_path):
    p = tmp_path / "x.sql"
    p.write_text("SELECT * FROM FOO;")
    assert not SQLPLExtractor().can_handle(p)


def test_can_handle_true_for_proc_sql(tmp_path):
    p = tmp_path / "y.Sql"
    p.write_text("CREATE PROCEDURE P() LANGUAGE SQL BEGIN END;")
    assert SQLPLExtractor().can_handle(p)