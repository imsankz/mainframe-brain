"""query — natural-language-ish graph queries (zero LLM)."""
from __future__ import annotations

import json

import click

from mainframe_brain.cli._common import (
    _find_node,
    _neighbors_with_edge,
    _open,
)
from mainframe_brain.graph.schema import NodeType


@click.command()
@click.option("--store-path", "store_path", required=True)
@click.argument("question")
@click.option("--json", "as_json", is_flag=True, help="Output JSON to stdout.")
def query(store_path: str, question: str, as_json: bool) -> None:
    """Natural-language-ish graph queries (zero LLM)."""
    store = _open(store_path)
    q = question.lower().strip()

    if q.startswith("what touches") or q.startswith("touching "):
        name = q.replace("what touches ", "").replace("touching ", "").strip()
        target = _find_node(store, name)
        if not target:
            _query_output(store, as_json, question, False, {"reason": f"no node named '{name}'"}, None)
        else:
            neighbors = []
            for nb, edge in _neighbors_with_edge(store, target.id):
                et = edge.type.value if hasattr(edge.type, "value") else str(edge.type)
                neighbors.append({"node": nb.id, "type": nb.type.value, "edge_type": et})

            if as_json:
                summary = {
                    "target": target.id,
                    "target_type": target.type.value,
                    "count": len(neighbors),
                }
                _query_output(store, as_json, question, True, summary, neighbors)
            else:
                click.echo(f"{target.id} ({target.type.value})")
                for nb, edge in _neighbors_with_edge(store, target.id):
                    et = edge.type.value if hasattr(edge.type, "value") else str(edge.type)
                    click.echo(f"  --[{et}]--> {nb.id} ({nb.type.value})")

    elif q.startswith("what runs ") or q.startswith("what job runs "):
        name = q.replace("what job runs ", "").replace("what runs ", "").strip()
        target = _find_node(store, name, NodeType.PROGRAM)
        if not target:
            _query_output(store, as_json, question, False, {"reason": f"no Program named '{name}'"}, None)
        else:
            callers: list[tuple] = []
            for e in store.all_edges():
                if e.type.value == "EXECUTES" and e.dst == target.id:
                    step = store.get_node(e.src)
                    if step:
                        callers.append(("EXEC", step))
                elif e.type.value == "CALLS" and e.dst == target.id:
                    caller_prog = store.get_node(e.src)
                    if caller_prog:
                        callers.append(("CALL", caller_prog))

            if as_json:
                caller_data = [
                    {
                        "kind": kind,
                        "node": c.id,
                        "parent_job": c.properties.get("parent_job", "") if kind == "EXEC" else None,
                    }
                    for kind, c in callers
                ]
                _query_output(store, as_json, question, True,
                              {"target": target.id, "invoker_count": len(callers)}, caller_data)
            else:
                click.echo(f"{target.id} is invoked by:")
                if not callers:
                    click.echo("  (nothing found)")
                for kind, c in callers:
                    if kind == "EXEC":
                        parent = c.properties.get("parent_job", "")
                        suffix = f" [{parent}]" if parent else ""
                        click.echo(f"  --{kind} from--> {c.id}{suffix}")
                    else:
                        click.echo(f"  --{kind} from--> {c.id}")

    elif q.startswith("show triggers on "):
        table_name = q.replace("show triggers on ", "").strip()
        table = _find_node(store, table_name, NodeType.DB2_TABLE)
        if not table:
            _query_output(store, as_json, question, False,
                          {"reason": f"no DB2Table named '{table_name}'"}, None)
        else:
            triggers = [
                store.get_node(e.src)
                for e in store.all_edges()
                if e.type.value == "FIRES_ON" and e.dst == table.id
            ]
            triggers = [t for t in triggers if t]

            if as_json:
                triggers_data = [
                    {
                        "id": t.id,
                        "timing": t.properties.get("timing"),
                        "event": t.properties.get("event"),
                        "chain": [c.id for c in store.neighbors(t.id, "TRIGGERS_TRIGGER")],
                    }
                    for t in triggers
                ]
                _query_output(store, as_json, question, True,
                              {"table": table.id, "trigger_count": len(triggers)}, triggers_data)
            else:
                click.echo(f"triggers on {table.id}: {len(triggers)}")
                for t in triggers:
                    click.echo(
                        f"  {t.id} timing={t.properties.get('timing')} "
                        f"event={t.properties.get('event')}"
                    )
                    for chain in store.neighbors(t.id, "TRIGGERS_TRIGGER"):
                        click.echo(f"    -> fires {chain.id}")

    elif q.startswith("impact of "):
        name = q.replace("impact of ", "").strip()
        target = _find_node(store, name)
        if not target:
            _query_output(store, as_json, question, False, {"reason": f"no node named '{name}'"}, None)
        else:
            visited: dict[str, int] = {target.id: 0}
            frontier: list[tuple[str, int]] = [(target.id, 0)]
            while frontier:
                cur, depth = frontier.pop(0)
                if depth >= 2:
                    continue
                nexts: set[str] = set()
                for e in store.all_edges():
                    if e.src == cur and e.dst != cur:
                        nexts.add(e.dst)
                    elif e.dst == cur and e.src != cur:
                        nexts.add(e.src)
                for nid in nexts:
                    if nid not in visited:
                        visited[nid] = depth + 1
                        frontier.append((nid, depth + 1))
            impact = [
                {"node": nid, "hop": d}
                for nid, d in sorted(visited.items(), key=lambda x: (x[1], x[0]))
                if nid != target.id
            ]
            if as_json:
                _query_output(store, as_json, question, True,
                              {"target": target.id, "impact_radius": len(impact)}, impact)
            else:
                click.echo(f"impact radius of {target.id}:")
                for nid, d in sorted(visited.items(), key=lambda x: (x[1], x[0])):
                    if nid == target.id:
                        continue
                    click.echo(f"  hop {d}: {nid}")
    else:
        msg = (
            "unrecognized query. try: 'what touches <name>', 'impact of <name>', "
            "'show triggers on <table>'"
        )
        if as_json:
            _query_output(store, as_json, question, False, {"reason": msg}, None)
        else:
            click.echo(msg)

    store.close()


def _query_output(store, as_json: bool, question: str, matched: bool, summary_extra: dict, data) -> None:
    if as_json:
        click.echo(json.dumps({
            "status": "ok",
            "command": "query",
            "summary": {"query": question, "matched": matched, **summary_extra},
            "data": data,
            "errors": [],
        }, indent=2, default=str))
    # For non-json mode, the caller handles it inline
