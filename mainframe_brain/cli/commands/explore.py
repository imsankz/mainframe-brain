"""explore — render 1-hop neighborhood of a node."""
from __future__ import annotations

import json

import click

from mainframe_brain.cli._common import _neighbors_with_edge, _open


@click.command()
@click.option("--store-path", "store_path", required=True)
@click.option("--node", required=True)
@click.option("--format", "fmt", type=click.Choice(["mermaid", "text"]), default="mermaid")
@click.option("--json", "as_json", is_flag=True, help="Output JSON to stdout.")
def explore(store_path: str, node: str, fmt: str, as_json: bool) -> None:
    """Render 1-hop neighborhood of NODE_ID as mermaid or text."""
    store = _open(store_path)
    target = store.get_node(node)
    if not target:
        if as_json:
            click.echo(json.dumps({
                "status": "ok",
                "command": "explore",
                "summary": {"node": node, "found": False},
                "data": None,
                "errors": [],
            }, indent=2, default=str))
        else:
            click.echo(f"node not found: {node}")
        store.close()
        return

    neighbors: list[dict] = []
    for nb, edge in _neighbors_with_edge(store, target.id):
        et = edge.type.value if hasattr(edge.type, "value") else str(edge.type)
        neighbors.append({"node": nb.id, "type": nb.type.value, "edge_type": et})

    if as_json:
        click.echo(json.dumps({
            "status": "ok",
            "command": "explore",
            "summary": {
                "node": target.id,
                "type": target.type.value,
                "neighbor_count": len(neighbors),
            },
            "data": neighbors,
            "errors": [],
        }, indent=2, default=str))
    elif fmt == "mermaid":
        click.echo("graph LR")
        for nb, edge in _neighbors_with_edge(store, target.id):
            et = edge.type.value if hasattr(edge.type, "value") else str(edge.type)
            click.echo(f'  {target.id} -- "{et}" --> {nb.id}')
    else:
        for nb, edge in _neighbors_with_edge(store, target.id):
            et = edge.type.value if hasattr(edge.type, "value") else str(edge.type)
            click.echo(f"{target.id} --[{et}]--> {nb.id}")

    store.close()
