"""build — extract source content into a graph store and summarize it for access."""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import click

from mainframe_brain.cli._common import _open, get_extractors
from mainframe_brain.graph.schema import NodeType


@click.command(name="build")
@click.argument("path", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--codebase-id", default="default")
@click.option("--out", default="brain.db")
@click.option("--json", "as_json", is_flag=True, help="Output JSON to stdout.")
def build(path: Path, codebase_id: str, out: str, as_json: bool) -> None:
    """Extract a source tree into a graph store and surface a useful summary."""
    store = _open(out, codebase_id)
    extractors = get_extractors()
    files = [p for p in path.rglob("*") if p.is_file()]
    node_counts: dict[str, int] = defaultdict(int)
    edge_count = 0
    unit_count = 0
    handled = 0
    errors: list[str] = []

    if as_json:
        iterable = files
        for f in iterable:
            file_handled = False
            for ext in extractors:
                try:
                    if not ext.can_handle(f):
                        continue
                    res = ext.extract(f, codebase_id=codebase_id)
                    store.add_nodes(res.nodes)
                    store.add_edges(res.edges)
                    for n in res.nodes:
                        node_counts[n.type.value] = node_counts.get(n.type.value, 0) + 1
                    edge_count += len(res.edges)
                    unit_count += len(res.units)
                    handled += 1
                    file_handled = True
                except Exception as e:  # noqa: BLE001
                    msg = f"[warn] {ext.artifact_type} failed on {f.name}: {e}"
                    errors.append(msg)
                    click.echo(msg, err=True)
            if not file_handled:
                continue
    else:
        with click.progressbar(
            files,
            label="Building",
            item_show_func=lambda f: str(f) if f else "",
        ) as bar:
            for f in bar:
                file_handled = False
                for ext in extractors:
                    try:
                        if not ext.can_handle(f):
                            continue
                        res = ext.extract(f, codebase_id=codebase_id)
                        store.add_nodes(res.nodes)
                        store.add_edges(res.edges)
                        for n in res.nodes:
                            node_counts[n.type.value] = node_counts.get(n.type.value, 0) + 1
                        edge_count += len(res.edges)
                        unit_count += len(res.units)
                        handled += 1
                        file_handled = True
                    except Exception as e:  # noqa: BLE001
                        msg = f"[warn] {ext.artifact_type} failed on {f.name}: {e}"
                        errors.append(msg)
                        click.echo(msg, err=True)
                if not file_handled:
                    continue

    nodes = store.all_nodes()
    preferred_types = {NodeType.PROGRAM.value, NodeType.PARAGRAPH.value, NodeType.BUSINESS_RULE.value}
    preferred_nodes = [n for n in nodes if n.type.value in preferred_types]
    other_nodes = [n for n in nodes if n.type.value not in preferred_types]
    accessible_nodes = [
        {
            "id": n.id,
            "name": n.name,
            "type": n.type.value,
            "confidence": round(n.parse_confidence, 2),
            "hash": n.content_hash[:12] if n.content_hash else "",
        }
        for n in sorted(
            preferred_nodes + other_nodes,
            key=lambda item: (
                0 if item.type.value in preferred_types else 1,
                item.type.value,
                item.name.lower(),
            ),
        )[:10]
    ]

    logical_units = sum(1 for n in nodes if n.type == NodeType.PARAGRAPH)
    store.close()

    payload = {
        "status": "ok",
        "command": "build",
        "summary": {
            "files_scanned": len(files),
            "files_handled": handled,
            "logical_units": logical_units,
            "edges": edge_count,
            "nodes_by_type": dict(sorted(node_counts.items())),
            "accessible_nodes": accessible_nodes,
        },
        "data": None,
        "errors": errors,
    }

    if as_json:
        click.echo(json.dumps(payload, indent=2, default=str))
    else:
        click.echo(f"files scanned: {len(files)}")
        click.echo(f"files handled: {handled}")
        click.echo(f"logical units: {logical_units}")
        click.echo(f"edges: {edge_count}")
        click.echo("nodes by type:")
        for t, c in sorted(node_counts.items()):
            click.echo(f"  {t}: {c}")
        if accessible_nodes:
            click.echo("sample accessible nodes:")
            for item in accessible_nodes:
                click.echo(
                    f"  {item['id']} [{item['type']}] {item['name']} conf={item['confidence']:.2f}"
                )
