"""Mainframe Brain command-line interface."""
from __future__ import annotations

import importlib
import pkgutil
from datetime import datetime, timezone
from pathlib import Path

import click

from mainframe_brain.graph.schema import Node, NodeType
from mainframe_brain.graph.sqlite_store import SQLiteGraphStore

_EXTRACTORS: list | None = None


def get_extractors() -> list:
    global _EXTRACTORS
    if _EXTRACTORS is not None:
        return _EXTRACTORS
    import mainframe_brain.extractors as pkg

    discovered: list = []
    for mod in pkgutil.iter_modules(pkg.__path__):
        if not mod.ispkg:
            continue
        try:
            m = importlib.import_module(f"mainframe_brain.extractors.{mod.name}.extractor")
        except ModuleNotFoundError:
            continue
        for attr in dir(m):
            obj = getattr(m, attr)
            if isinstance(obj, type) and attr.endswith("Extractor") and attr != "Extractor":
                inst = obj()
                if hasattr(inst, "artifact_type") and hasattr(inst, "can_handle"):
                    discovered.append(inst)
    _EXTRACTORS = discovered
    return discovered


def _open(path: str, codebase_id: str = "default") -> SQLiteGraphStore:
    return SQLiteGraphStore(path, codebase_id=codebase_id)


@click.group()
def cli() -> None:
    """Mainframe Brain — deterministic extraction + selective LLM enrichment."""


@cli.command()
@click.argument("path", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--codebase-id", default="default")
@click.option("--out", default="brain.db")
def extract(path: Path, codebase_id: str, out: str) -> None:
    """Walk PATH, run matching extractors, populate graph store."""
    store = _open(out, codebase_id)
    extractors = get_extractors()
    files = [p for p in path.rglob("*") if p.is_file()]
    node_counts: dict[str, int] = {}
    edge_count = 0
    unit_count = 0
    handled = 0
    for f in files:
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
                click.echo(
                    f"[warn] {ext.artifact_type} failed on {f.name}: {e}", err=True
                )
        if not file_handled:
            continue
    store.close()
    click.echo(f"files scanned: {len(files)}")
    click.echo(f"files handled: {handled}")
    click.echo(f"logical units: {unit_count}")
    click.echo(f"edges: {edge_count}")
    click.echo("nodes by type:")
    for t, c in sorted(node_counts.items()):
        click.echo(f"  {t}: {c}")


@cli.command(name="list-nodes")
@click.option("--store-path", "store_path", required=True)
@click.option("--type", "type_", default=None)
def list_nodes(store_path: str, type_: str | None) -> None:
    """List nodes in the store (optionally filtered by type)."""
    store = _open(store_path)
    for n in store.all_nodes():
        if type_ and n.type.value != type_:
            continue
        h = n.content_hash[:8] if n.content_hash else "-"
        click.echo(f"{n.id}  hash={h}  conf={n.parse_confidence:.2f}")
    store.close()


@cli.command()
@click.option("--store-path", "store_path", required=True)
@click.argument("question")
def query(store_path: str, question: str) -> None:
    """Natural-language-ish graph queries (zero LLM)."""
    store = _open(store_path)
    q = question.lower().strip()

    if q.startswith("what touches") or q.startswith("touching "):
        name = q.replace("what touches ", "").replace("touching ", "").strip()
        target = _find_node(store, name)
        if not target:
            click.echo(f"no node named '{name}'")
        else:
            click.echo(f"{target.id} ({target.type.value})")
        for nb, edge in _neighbors_with_edge(store, target.id):
            et = edge.type.value if hasattr(edge.type, "value") else str(edge.type)
            click.echo(f"  --[{et}]--> {nb.id} ({nb.type.value})")
    elif q.startswith("show triggers on "):
        table_name = q.replace("show triggers on ", "").strip()
        table = _find_node(store, table_name, NodeType.DB2_TABLE)
        if not table:
            click.echo(f"no DB2Table named '{table_name}'")
        else:
            triggers = [
                store.get_node(e.src)
                for e in store.all_edges()
                if e.type.value == "FIRES_ON" and e.dst == table.id
            ]
            triggers = [t for t in triggers if t]
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
            click.echo(f"no node named '{name}'")
        else:
            click.echo(f"impact radius of {target.id}:")
            visited: dict[str, int] = {target.id: 0}
            frontier = [(target.id, 0)]
            while frontier:
                cur, depth = frontier.pop(0)
                if depth >= 2:
                    continue
                nexts = set()
                for e in store.all_edges():
                    if e.src == cur and e.dst != cur:
                        nexts.add(e.dst)
                    elif e.dst == cur and e.src != cur:
                        nexts.add(e.src)
                for nid in nexts:
                    if nid not in visited:
                        visited[nid] = depth + 1
                        frontier.append((nid, depth + 1))
            for nid, d in sorted(visited.items(), key=lambda x: (x[1], x[0])):
                if nid == target.id:
                    continue
                click.echo(f"  hop {d}: {nid}")
    else:
        click.echo(
            "unrecognized query. try: 'what touches <name>', 'impact of <name>', "
            "'show triggers on <table>'"
        )
    store.close()


@cli.command()
@click.option("--store-path", "store_path", required=True)
@click.option("--node", required=True)
@click.option("--format", "fmt", type=click.Choice(["mermaid", "text"]), default="mermaid")
def explore(store_path: str, node: str, fmt: str) -> None:
    """Render 1-hop neighborhood of NODE_ID as mermaid or text."""
    store = _open(store_path)
    target = store.get_node(node)
    if not target:
        click.echo(f"node not found: {node}")
        store.close()
        return
    if fmt == "mermaid":
        click.echo("graph LR")
        for nb, edge in _neighbors_with_edge(store, target.id):
            et = edge.type.value if hasattr(edge.type, "value") else str(edge.type)
            click.echo(f'  {target.id} -- "{et}" --> {nb.id}')
    else:
        for nb, edge in _neighbors_with_edge(store, target.id):
            et = edge.type.value if hasattr(edge.type, "value") else str(edge.type)
            click.echo(f"{target.id} --[{et}]--> {nb.id}")
    store.close()


@cli.command()
@click.option("--store-path", "store_path", required=True)
@click.option("--budget", default=20000, type=int)
@click.option("--adapter", type=click.Choice(["mock", "anthropic", "openai"]), default="mock")
@click.option("--adapter-model", "adapter_model", default=None)
def enrich(
    store_path: str, budget: int, adapter: str, adapter_model: str | None
) -> None:
    """Run selective LLM enrichment (MockAdapter default for offline demos)."""
    store = _open(store_path)

    from mainframe_brain.enrichment import Enricher
    from mainframe_brain.enrichment.models.anthropic_adapter import AnthropicAdapter
    from mainframe_brain.enrichment.models.mock_adapter import MockAdapter
    from mainframe_brain.enrichment.models.openai_adapter import OpenAIAdapter
    from mainframe_brain.extractors.base import LogicalUnit, content_hash
    from mainframe_brain.redaction import RedactionConfig

    if adapter == "anthropic":
        adapter_inst = AnthropicAdapter(model=adapter_model or "claude-3-5-haiku-20241022")
    elif adapter == "openai":
        adapter_inst = OpenAIAdapter(model=adapter_model or "gpt-4o-mini")
    else:
        adapter_inst = MockAdapter()

    enricher = Enricher(adapter_inst, store, RedactionConfig(), budget_tokens=budget)

    enriched_src_ids = {
        e.src for e in store.all_edges() if e.type.value == "IMPLEMENTS_RULE"
    }
    items = []
    for n in store.all_nodes():
        if n.type != NodeType.PARAGRAPH or n.id in enriched_src_ids:
            continue
        source = n.properties.get("source", "")
        if not source:
            continue
        items.append(
            {
                "unit": LogicalUnit(
                    kind="paragraph",
                    name=n.name,
                    source=source,
                    content_hash=n.content_hash or content_hash(source),
                    post_expansion=bool(n.properties.get("replacing_applied")),
                ),
                "source_node_id": n.id,
                "codebase_id": n.codebase_id,
            }
        )

    r = enricher.enrich(items)
    store.close()
    click.echo(f"created: {len(r.created)}")
    click.echo(f"cache_hits: {r.cache_hit}")
    click.echo(f"tokens_used: {r.tokens_used}")
    click.echo(f"redacted_total: {r.redacted_total}")
    click.echo(f"skipped: {r.skipped}")


@cli.command()
@click.option("--store-path", "store_path", required=True)
@click.argument("rule_id")
def verify(store_path: str, rule_id: str) -> None:
    """Mark a BusinessRule node human_verified=True."""
    store = _open(store_path)
    from mainframe_brain.enrichment.cache import NarrationCache

    n = store.get_node(rule_id)
    if not n:
        for cand in store.all_nodes():
            if cand.type == NodeType.BUSINESS_RULE and rule_id in cand.name:
                n = cand
                break
    if not n or n.type != NodeType.BUSINESS_RULE:
        click.echo(f"no BusinessRule matching '{rule_id}'")
        store.close()
        return

    n.properties["human_verified"] = True
    n.last_verified = _now_iso()
    store.add_node(n)
    NarrationCache(store._conn).mark_verified(n.content_hash, True)
    click.echo(f"verified: {n.id}")
    store.close()


def _neighbors_with_edge(store, node_id: str):
    out = []
    for e in store.all_edges():
        if e.src == node_id:
            nb = store.get_node(e.dst)
            if nb:
                out.append((nb, e))
        elif e.dst == node_id:
            nb = store.get_node(e.src)
            if nb:
                out.append((nb, e))
    return out


def _find_node(store, name: str, type_: NodeType | None = None) -> Node | None:
    name_lower = name.lower()
    for n in store.all_nodes():
        if type_ and n.type != type_:
            continue
        if n.name.lower() == name_lower or n.id == name:
            return n
    for n in store.all_nodes():
        if type_ and n.type != type_:
            continue
        if name_lower in n.name.lower() or name_lower in n.id.lower():
            return n
    return None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    cli()