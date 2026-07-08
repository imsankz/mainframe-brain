"""Impact analysis over the extracted graph."""
from __future__ import annotations

import json

import click

from mainframe_brain.analytics import analyze_impact
from mainframe_brain.cli._common import _open


@click.command(name="impact")
@click.option("--store-path", "store_path", required=True)
@click.option("--node", "node_id", required=True, help="Node id to analyze")
@click.option("--depth", default=3, type=int, show_default=True)
@click.option("--json", "as_json", is_flag=True, help="Output JSON to stdout.")
def impact(store_path: str, node_id: str, depth: int, as_json: bool) -> None:
    """Report the blast radius of a node in the graph."""
    store = _open(store_path)
    try:
        result = analyze_impact(store, node_id, max_depth=depth)
    except KeyError:
        store.close()
        raise click.ClickException(f"node not found: {node_id}") from None
    store.close()

    if as_json:
        click.echo(json.dumps({
            "status": "ok",
            "command": "impact",
            "summary": {
                "target": result["target"],
                "impact_count": result["impact_count"],
                "max_depth": result["max_depth"],
            },
            "data": result["data"],
            "errors": [],
        }, indent=2, default=str))
    else:
        click.echo(f"impact for {node_id}:")
        click.echo(f"  impact_count: {result['impact_count']}")
        for item in result["data"]:
            click.echo(f"  {item['node']['name']} (distance {item['distance']})")
