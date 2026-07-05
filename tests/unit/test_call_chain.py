from __future__ import annotations

from pathlib import Path

from mainframe_brain.cli import get_extractors
from mainframe_brain.graph.schema import NodeType
from mainframe_brain.graph.sqlite_store import SQLiteGraphStore


def test_jcl_to_program_to_subprogram_chain(tmp_path):
    store = SQLiteGraphStore(":memory:")
    for family, fname in [("cobol", "INTCALC01.cbl"), ("jcl", "PAYRUN.jcl")]:
        f = Path(__file__).resolve().parents[2] / "examples" / family / fname
        for ext in get_extractors():
            if ext.can_handle(f):
                res = ext.extract(f, codebase_id="default")
                store.add_nodes(res.nodes)
                store.add_edges(res.edges)

    executes = [
        e for e in store.all_edges()
        if (e.type.value if hasattr(e.type, "value") else str(e.type)) == "EXECUTES"
    ]
    assert executes, "expected EXECUTES edges from JCLStep to Program"

    step_to_prog = {e.src: e.dst for e in executes}
    assert any("INTCALC01" in d for d in step_to_prog.values()), (
        "expected JCL to run INTCALC01"
    )

    calls = [
        e for e in store.all_edges()
        if (e.type.value if hasattr(e.type, "value") else str(e.type)) == "CALLS"
    ]
    assert any(
        "INTCALC01" in e.src and "SUBPROG" in e.dst for e in calls
    ), "expected INTCALC01 CALLS SUBPROG"

    src_step = next(sid for sid, dst in step_to_prog.items() if "INTCALC01" in dst)
    step = store.get_node(src_step)
    assert step is not None and step.type == NodeType.JCL_STEP
    assert step.properties.get("parent_job"), "JCLStep must record its parent_job"

    callee = store.get_node("Program:default:SUBPROG")
    assert callee is not None
    assert callee.properties.get("placeholder") is True
