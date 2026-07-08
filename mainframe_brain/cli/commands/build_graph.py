"""build-graph — print node/edge counts from an existing brain."""
from __future__ import annotations

import json

import click

from mainframe_brain.analytics import build_graph_summary
from mainframe_brain.cli._common import _open


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
    summary = build_graph_summary(store)
    store.close()

    if as_json:
        click.echo(json.dumps({
            "status": "ok",
            "command": "build-graph",
            "summary": {
                "nodes_by_type": dict(sorted(summary["nodes_by_type"].items())),
                "edges_by_type": dict(sorted(summary["edges_by_type"].items())),
                "logical_units_discoverable": summary["logical_units_discoverable"],
                "top_risk_nodes": summary["top_risk_nodes"],
                "hub_nodes": summary["hub_nodes"],
                "graph_health": summary["graph_health"],
            },
            "data": None,
            "errors": [],
        }, indent=2, default=str))
    else:
        click.echo("nodes by type:")
        for t, c in sorted(summary["nodes_by_type"].items()):
            click.echo(f"  {t}: {c}")
        click.echo("edges by type:")
        for t, c in sorted(summary["edges_by_type"].items()):
            click.echo(f"  {t}: {c}")
        click.echo(f"logical units discoverable: {summary['logical_units_discoverable']}")
        click.echo(f"graph health: {summary['graph_health']}")
        click.echo("top risk nodes:")
        for item in summary["top_risk_nodes"]:
            click.echo(f"  {item['node']['name']} ({item['risk_score']})")
        click.echo("hub nodes:")
        for item in summary["hub_nodes"]:
            click.echo(f"  {item['node']['name']} ({item['degree']})")
