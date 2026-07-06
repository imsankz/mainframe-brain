"""extract — walk source tree and run matching extractors."""
from __future__ import annotations

import json
from pathlib import Path

import click

from mainframe_brain.cli._common import _open, get_extractors


@click.command()
@click.argument("path", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--codebase-id", default="default")
@click.option("--out", default="brain.db")
@click.option("--json", "as_json", is_flag=True, help="Output JSON to stdout.")
def extract(path: Path, codebase_id: str, out: str, as_json: bool) -> None:
    """Walk PATH, run matching extractors, populate graph store."""
    store = _open(out, codebase_id)
    extractors = get_extractors()
    files = [p for p in path.rglob("*") if p.is_file()]
    node_counts: dict[str, int] = {}
    edge_count = 0
    unit_count = 0
    handled = 0
    errors: list[str] = []

    with click.progressbar(
        files,
        label="Extracting",
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

    store.close()

    if as_json:
        click.echo(json.dumps({
            "status": "ok",
            "command": "extract",
            "summary": {
                "files_scanned": len(files),
                "files_handled": handled,
                "logical_units": unit_count,
                "edges": edge_count,
                "nodes_by_type": node_counts,
            },
            "data": None,
            "errors": errors,
        }, indent=2, default=str))
    else:
        click.echo(f"files scanned: {len(files)}")
        click.echo(f"files handled: {handled}")
        click.echo(f"logical units: {unit_count}")
        click.echo(f"edges: {edge_count}")
        click.echo("nodes by type:")
        for t, c in sorted(node_counts.items()):
            click.echo(f"  {t}: {c}")
