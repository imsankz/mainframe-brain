"""list-nodes — list nodes in the graph store."""
from __future__ import annotations

import json

import click

from mainframe_brain.cli._common import _open


@click.command(name="list-nodes")
@click.option("--store-path", "store_path", required=True)
@click.option("--type", "type_", default=None)
@click.option(
    "--low-confidence",
    "low_confidence",
    is_flag=True,
    default=False,
    help="Only print nodes with parse_confidence < 1.0 (partial-parse survivors).",
)
@click.option("--json", "as_json", is_flag=True, help="Output JSON to stdout.")
def list_nodes(store_path: str, type_: str | None, low_confidence: bool, as_json: bool) -> None:
    """List nodes in the store (optionally filtered by type and confidence)."""
    store = _open(store_path)
    data: list[str] = []
    for n in store.all_nodes():
        if type_ and n.type.value != type_:
            continue
        if low_confidence and n.parse_confidence >= 1.0:
            continue
        h = n.content_hash[:8] if n.content_hash else "-"
        line = f"{n.id}  hash={h}  conf={n.parse_confidence:.2f}"
        data.append(line)

    if as_json:
        click.echo(json.dumps({
            "status": "ok",
            "command": "list-nodes",
            "summary": {"count": len(data)},
            "data": data,
            "errors": [],
        }, indent=2, default=str))
    else:
        for line in data:
            click.echo(line)

    store.close()
