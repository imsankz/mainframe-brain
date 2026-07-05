from mainframe_brain.graph.schema import Edge, EdgeType, Node, NodeType
from mainframe_brain.graph.sqlite_store import SQLiteGraphStore


def _make_program() -> Node:
    return Node(
        id="Program:default:PROG1",
        type=NodeType.PROGRAM,
        name="PROG1",
        codebase_id="default",
        content_hash="abc123",
        properties={"lines": 200, "language": "COBOL"},
    )


def _make_paragraph() -> Node:
    return Node(
        id="Paragraph:default:PROG1#INIT",
        type=NodeType.PARAGRAPH,
        name="INIT",
        codebase_id="default",
        content_hash="def456",
        properties={"section": "PROCEDURE"},
    )


def test_sqlite_store_roundtrip():
    store = SQLiteGraphStore(":memory:", codebase_id="default")

    prog = _make_program()
    para = _make_paragraph()
    store.add_node(prog)
    store.add_node(para)
    store.add_edge(
        Edge(src=prog.id, dst=para.id, type=EdgeType.PERFORMS, properties={"line": 10})
    )

    got = store.get_node(prog.id)
    assert got is not None
    assert got.type == NodeType.PROGRAM
    assert got.properties == {"lines": 200, "language": "COBOL"}
    assert got.content_hash == "abc123"

    nbrs = store.neighbors(prog.id, edge_type=EdgeType.PERFORMS.value)
    assert len(nbrs) == 1
    assert nbrs[0].id == para.id
    assert nbrs[0].properties == {"section": "PROCEDURE"}

    all_nbrs = store.neighbors(prog.id)
    assert len(all_nbrs) == 1

    assert len(store.all_nodes()) == 2
    assert len(store.all_edges()) == 1

    rows = store.query("SELECT id, type FROM nodes WHERE type = 'Program'")
    assert rows == [{"id": prog.id, "type": "Program"}]

    fresh = SQLiteGraphStore(":memory:", codebase_id="default")
    diff = store.diff_against(fresh)
    assert diff["added"] == sorted([prog.id, para.id])
    assert diff["removed"] == []
    assert diff["changed"] == []

    history = store.query("SELECT op FROM node_history ORDER BY ts")
    ops = [r["op"] for r in history]
    assert len(ops) == 2
    assert ops == ["add", "add"]

    store.add_node(prog)
    history2 = store.query("SELECT op FROM node_history ORDER BY ts")
    ops2 = [r["op"] for r in history2]
    assert ops2 == ["add", "add", "update"]

    store.close()
    fresh.close()