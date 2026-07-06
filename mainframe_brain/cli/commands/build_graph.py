"""build-graph — print node/edge counts from an existing brain."""
from __future__ import annotations

import json
from collections import defaultdict

import click

from mainframe_brain.cli._common import _open
from mainframe_brain.graph.schema import NodeType


@click.command(name="build-graph")
@click.option("--store-path", "store_path", required=True)
@click.option(
    "--from-json",
    "from_json",
    default=None,
    type=click.Path(),
    help="Reserved for forward-compat (MVP reads the store).",
)
@click.option("--json", "as_json", is_flag=True, help="Output JSON to stdout.")
def build_graph(store_path: str, from_json: str | None, as_json: bool) -> None:
    """Print node/edge counts and logical-unit discoverability from an existing brain."""
    store = _open(store_path)
    node_counts: dict[str, int] = defaultdict(int)
    edge_counts: dict[str, int] = defaultdict(int)
    units = 0
    for n in store.all_nodes():
        node_counts[n.type.value] += 1
        if n.type == NodeType.PARAGRAPH:
            units += 1
    for e in store.all_edges():
        et = e.type.value if hasattr(e.type, "value") else str(e.type)
        edge_counts[et] += 1
    store.close()

    if as_json:
        click.echo(json.dumps({
            "status": "ok",
            "command": "build-graph",
            "summary": {
                "nodes_by_type": dict(sorted(node_counts.items())),
                "edges_by_type": dict(sorted(edge_counts.items())),
                "logical_units_discoverable": units,
            },
            "data": None,
            "errors": [],
        }, indent=2, default=str))
    else:
        click.echo("nodes by type:")
        for t, c in sorted(node_counts.items()):
            click.echo(f"  {t}: {c}")
        click.echo("edges by type:")
        for t, c in sorted(edge_counts.items()):
            click.echo(f"  {t}: {c}")
        click.echo(f"logical units discoverable: {units}")
