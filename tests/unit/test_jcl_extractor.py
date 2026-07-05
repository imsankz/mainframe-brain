from pathlib import Path

from mainframe_brain.extractors.jcl.extractor import JCLExtractor
from mainframe_brain.graph.schema import EdgeType, NodeType

_GOOD_JCL = """\
//PAYRUN JOB (ACCT),'PAY',CLASS=A,MSGCLASS=X
//STEP-COB EXEC PGM=PAYCALC0,COND=(4,LT)
//PAYMAST DD DSN=P.DATA.PAYMAST,DISP=SHR
//STEP-RPT EXEC PGM=IEBGENER,COND=(4,LT)
//SYSUT1  DD *
COPY THESE RECORDS
/*
//SYSUT2  DD DSN=P.DATA.PAYRUN.RPT,DISP=(NEW,CATLG,DELETE)
//SYSPRINT DD SYSOUT=X
"""

_BAD_JCL = """\
//PAYRUN JOB (ACCT),'PAY',CLASS=A
//STEP-COB EXEC PGM=PAYCALC0
//PAYMAST DD DSN=P.DATA.PAYMAST,DISP=SHR
// XYZ SOMEMALFORMEDLINE
//STEP-RPT EXEC PGM=IEBGENER
//SYSUT2 DD DSN=P.DATA.PAYRUN.RPT,DISP=(NEW,CATLG,DELETE)
"""


def _hex64(s: str) -> bool:
    return len(s) == 64 and all(c in "0123456789abcdef" for c in s)


def test_can_handle():
    ext = JCLExtractor()
    assert ext.can_handle(Path("foo.jcl"))
    assert ext.can_handle(Path("BAR.JCL"))
    assert not ext.can_handle(Path("bar.cbl"))
    assert not ext.can_handle(Path("foo.cob"))


def test_job_steps_datasets_edges_and_units(tmp_path):
    f = tmp_path / "payrun.jcl"
    f.write_text(_GOOD_JCL, encoding="utf-8")
    res = JCLExtractor().extract(f, codebase_id="cb1")

    jobs = [n for n in res.nodes if n.type == NodeType.JCL_JOB]
    steps = [n for n in res.nodes if n.type == NodeType.JCL_STEP]
    datasets = [n for n in res.nodes if n.type == NodeType.DATASET]
    assert len(jobs) == 1
    assert len(steps) == 2
    assert len(datasets) == 2

    assert _hex64(jobs[0].content_hash)
    for s in steps:
        assert _hex64(s.content_hash)
        assert s.properties["program"] in {"PAYCALC0", "IEBGENER"}
    assert steps[0].properties["cond"] == "4,LT"
    assert steps[1].properties["cond"] == "4,LT"
    assert steps[1].properties["sysouts"] == ["X"]

    reads = [e for e in res.edges if e.type == EdgeType.READS]
    writes = [e for e in res.edges if e.type == EdgeType.WRITES]
    assert len(reads) == 1
    assert len(writes) == 1
    assert reads[0].src == steps[0].id
    assert reads[0].dst == [d for d in datasets if d.name == "P.DATA.PAYMAST"][0].id
    assert writes[0].dst == [d for d in datasets if d.name == "P.DATA.PAYRUN.RPT"][0].id
    assert writes[0].properties["disp"] == "NEW"

    assert len(res.units) == 2
    for u in res.units:
        assert u.kind == "job_step"
        assert _hex64(u.content_hash)
        assert u.source  # non-empty
    assert {u.name for u in res.units} == {"STEP-COB", "STEP-RPT"}


def test_low_confidence_on_unknown_verb(tmp_path):
    f = tmp_path / "bad.jcl"
    f.write_text(_BAD_JCL, encoding="utf-8")
    res = JCLExtractor().extract(f, codebase_id="cb2")
    anomalies = [n for n in res.nodes if n.parse_confidence < 1.0]
    assert anomalies, "anomaly node must be emitted, not dropped"
    assert any(n.properties.get("anomaly") for n in anomalies)