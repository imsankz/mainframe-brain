from pathlib import Path

from mainframe_brain.extractors.db2_ddl.extractor import DB2DDLExtractor
from mainframe_brain.graph.schema import EdgeType, NodeType
from mainframe_brain.graph.store import make_node_id

DDL = """
CREATE TABLE ACCOUNTS (
    ACCT_ID  BIGINT       NOT NULL PRIMARY KEY,
    CUST_ID  BIGINT       NOT NULL,
    BALANCE  DECIMAL(18,2)
);

CREATE TABLE AUDITLOG (
    AUDIT_ID BIGINT NOT NULL PRIMARY KEY,
    ACCT_ID  BIGINT,
    WHO      VARCHAR(64),
    CONSTRAINT ACCOUNTS_AK FOREIGN KEY (ACCT_ID)
        REFERENCES ACCOUNTS (ACCT_ID) ON DELETE CASCADE
);

CREATE VIEW V_ACCTS AS
    SELECT ACCT_ID, CUST_ID, BALANCE
    FROM ACCOUNTS
    WHERE BALANCE > 0;
"""


def _write(tmp_path: Path) -> Path:
    p = tmp_path / "schema.ddl"
    p.write_text(DDL)
    return p


def test_ddl_emits_tables_columns():
    p = _write(Path("/tmp/mb_test_ddl")) if False else None  # placeholder
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = _write(Path(d))
        ex = DB2DDLExtractor()
        res = ex.extract(p, codebase_id="default")

        tables = [n for n in res.nodes if n.type == NodeType.DB2_TABLE]
        assert {t.name for t in tables} == {"ACCOUNTS", "AUDITLOG"}

        cols = [n for n in res.nodes if n.type == NodeType.DB2_COLUMN]
        col_names = {c.name for c in cols}
        assert col_names == {"ACCT_ID", "CUST_ID", "BALANCE", "AUDIT_ID", "WHO"}

        acct_cols = [c for c in cols if c.properties["parent_table"] == "ACCOUNTS"]
        assert len(acct_cols) == 3


def test_ddl_emits_cascade_edge():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = _write(Path(d))
        res = DB2DDLExtractor().extract(p, codebase_id="default")
        cascade_edges = [e for e in res.edges if e.type == EdgeType.CASCADES_TO]
        assert len(cascade_edges) == 1
        e = cascade_edges[0]
        assert e.src == make_node_id("DB2Table", "default", "AUDITLOG")
        assert e.dst == make_node_id("DB2Table", "default", "ACCOUNTS")
        assert e.properties["rule"] == "ON DELETE CASCADE"

        fks = [n for n in res.nodes
               if n.type == NodeType.CONSTRAINT and n.properties.get("kind") == "FK"]
        assert len(fks) == 1
        fk = fks[0]
        assert fk.properties["references"] == "ACCOUNTS"
        assert "ON DELETE CASCADE" in fk.properties["cascade_rule"]


def test_ddl_emits_view_and_abstracts_edge():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = _write(Path(d))
        res = DB2DDLExtractor().extract(p, codebase_id="default")
        views = [n for n in res.nodes if n.type == NodeType.VIEW]
        assert len(views) == 1
        assert views[0].name == "V_ACCTS"

        abs_edges = [e for e in res.edges if e.type == EdgeType.ABSTRACTS]
        assert len(abs_edges) == 1
        assert abs_edges[0].dst == make_node_id("DB2Table", "default", "ACCOUNTS")