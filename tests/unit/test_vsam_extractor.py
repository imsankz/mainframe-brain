from pathlib import Path

from mainframe_brain.extractors.vsam.extractor import VSAMExtractor
from mainframe_brain.graph.schema import EdgeType, NodeType

KSDS_COBOL = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. ACCTTEST.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT ACCOUNTS-FILE
               ASSIGN TO ACCTMAST
               ORGANIZATION IS INDEXED
               ACCESS MODE IS RANDOM
               RECORD KEY IS ACCT-KEY
               ALTERNATE RECORD KEY IS ACCT-NAME.
       DATA DIVISION.
       FILE SECTION.
       FD  ACCOUNTS-FILE.
       01  ACCOUNT-RECORD.
           05  ACCT-KEY        PIC X(8).
           05  ACCT-NAME       PIC X(24).
       WORKING-STORAGE SECTION.
       01  WS-EOF              PIC X VALUE 'N'.
       PROCEDURE DIVISION.
       MAIN-PARA.
           OPEN I-O ACCOUNTS-FILE.
       READ-LOOP.
           READ ACCOUNTS-FILE NEXT RECORD
               AT END MOVE 'Y' TO WS-EOF
           END-READ.
           CLOSE ACCOUNTS-FILE.
           STOP RUN.
"""

KSDS_AND_SEQ_COBOL = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. VSMAPP01.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT ACCOUNTS-FILE
               ASSIGN TO ACCTMAST
               ORGANIZATION IS INDEXED
               ACCESS MODE IS RANDOM
               RECORD KEY IS ACCT-KEY
               ALTERNATE RECORD KEY IS ACCT-NAME.
           SELECT PAY-FILE
               ASSIGN TO PAYDATA
               ORGANIZATION IS LINE SEQUENTIAL.
       DATA DIVISION.
       FILE SECTION.
       FD  ACCOUNTS-FILE.
       01  ACCOUNT-RECORD.
           05  ACCT-KEY        PIC X(8).
           05  ACCT-NAME       PIC X(24).
       FD  PAY-FILE.
       01  PAY-RECORD           PIC X(80).
       WORKING-STORAGE SECTION.
       01  WS-EOF              PIC X VALUE 'N'.
       PROCEDURE DIVISION.
       MAIN-PARA.
           OPEN I-O ACCOUNTS-FILE
           OPEN OUTPUT PAY-FILE.
       READ-LOOP.
           READ ACCOUNTS-FILE NEXT RECORD
               AT END MOVE 'Y' TO WS-EOF
           END-READ.
           MOVE ACCOUNT-RECORD TO PAY-RECORD.
           WRITE PAY-RECORD.
           CLOSE ACCOUNTS-FILE PAY-FILE.
           STOP RUN.
"""


def test_can_handle():
    ext = VSAMExtractor()
    assert ext.can_handle(Path("foo.CBL"))
    assert ext.can_handle(Path("bar.cob"))
    assert not ext.can_handle(Path("odd.jcl"))


def test_ksds_vsam_node_and_reads_edge(tmp_path):
    f = tmp_path / "acct.cbl"
    f.write_text(KSDS_COBOL, encoding="utf-8")
    res = VSAMExtractor().extract(f, codebase_id="cb1")

    vsam_nodes = [n for n in res.nodes if n.type == NodeType.VSAM_DATASET]
    assert len(vsam_nodes) == 1
    vsam = vsam_nodes[0]
    assert vsam.properties["organization"] == "KSDS"
    assert vsam.properties["record_key"] == "ACCT-KEY"
    assert vsam.properties["alternate_keys"] == ["ACCT-NAME"]
    assert vsam.properties["access_mode"] == "RANDOM"
    assert vsam.properties["external_dataset"] == "ACCTMAST"
    assert vsam.parse_confidence == 1.0

    assert len(res.units) == 1
    unit = res.units[0]
    assert unit.kind == "file_descriptor"
    assert len(unit.content_hash) == 64
    assert all(c in "0123456789abcdef" for c in unit.content_hash)

    reads_edges = [e for e in res.edges if e.type == EdgeType.READS]
    assert len(reads_edges) == 1
    assert reads_edges[0].dst == vsam.id
    assert reads_edges[0].src.endswith("Program:cb1:ACCTTEST")
    assert reads_edges[0].properties["verb"] == "READ"


def test_sequential_dataset_and_write_edge(tmp_path):
    f = tmp_path / "vsmapp01.cbl"
    f.write_text(KSDS_AND_SEQ_COBOL, encoding="utf-8")
    res = VSAMExtractor().extract(f, codebase_id="cb2")

    vsam_nodes = [n for n in res.nodes if n.type == NodeType.VSAM_DATASET]
    seq_nodes = [n for n in res.nodes if n.type == NodeType.DATASET]
    assert len(vsam_nodes) == 1
    assert len(seq_nodes) == 1
    seq = seq_nodes[0]
    assert seq.properties["DSORG"] == "PS"
    assert seq.properties["external_dataset"] == "PAYDATA"
    assert seq.name == "PAY-FILE"

    writes_edges = [e for e in res.edges if e.type == EdgeType.WRITES]
    assert len(writes_edges) == 1
    assert writes_edges[0].dst == seq.id
    assert writes_edges[0].properties["verb"] == "WRITE"

    reads_edges = [e for e in res.edges if e.type == EdgeType.READS]
    assert len(reads_edges) == 1
    assert reads_edges[0].dst == vsam_nodes[0].id

    assert len(res.units) == 2
    for u in res.units:
        assert u.kind == "file_descriptor"
        assert len(u.content_hash) == 64


def test_low_confidence_when_organization_missing(tmp_path):
    bad = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. BADAPP.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT ORPHAN-FILE ASSIGN TO ORPHANDATA.
       DATA DIVISION.
       FILE SECTION.
       FD  ORPHAN-FILE.
       01  ORPHAN-RECORD     PIC X(10).
       PROCEDURE DIVISION.
           OPEN INPUT ORPHAN-FILE.
           STOP RUN.
"""
    f = tmp_path / "orphan.cbl"
    f.write_text(bad, encoding="utf-8")
    res = VSAMExtractor().extract(f, codebase_id="cb3")
    seq_nodes = [n for n in res.nodes if n.type == NodeType.DATASET]
    assert len(seq_nodes) == 1
    assert seq_nodes[0].parse_confidence < 1.0
    assert seq_nodes[0].properties["DSORG"] == "PS"


def test_example_file_parses():
    f = Path("examples/vsam/VSMAPP01.cbl")
    res = VSAMExtractor().extract(f, codebase_id="cb4")
    vsam_nodes = [n for n in res.nodes if n.type == NodeType.VSAM_DATASET]
    seq_nodes = [n for n in res.nodes if n.type == NodeType.DATASET]
    assert len(vsam_nodes) == 1
    assert len(seq_nodes) == 1
    assert any(e.type == EdgeType.READS for e in res.edges)
    assert any(e.type == EdgeType.WRITES for e in res.edges)