"""enrich — run selective LLM enrichment."""
from __future__ import annotations

import json

import click

from mainframe_brain.cli._common import _open, _triage_candidates


@click.command()
@click.option("--store-path", "store_path", required=True)
@click.option("--budget", default=20000, type=int)
@click.option("--adapter", type=click.Choice(["mock", "anthropic", "openai"]), default="mock")
@click.option("--adapter-model", "adapter_model", default=None)
@click.option("--json", "as_json", is_flag=True, help="Output JSON to stdout.")
def enrich(
    store_path: str,
    budget: int,
    adapter: str,
    adapter_model: str | None,
    as_json: bool,
) -> None:
    """Run selective LLM enrichment (MockAdapter default for offline demos)."""
    store = _open(store_path)

    from mainframe_brain.enrichment import Enricher
    from mainframe_brain.enrichment.cache import NarrationCache
    from mainframe_brain.enrichment.models.anthropic_adapter import AnthropicAdapter
    from mainframe_brain.enrichment.models.mock_adapter import MockAdapter
    from mainframe_brain.enrichment.models.openai_adapter import OpenAIAdapter
    from mainframe_brain.extractors.base import LogicalUnit
    from mainframe_brain.redaction import RedactionConfig

    if adapter == "anthropic":
        adapter_inst = AnthropicAdapter(model=adapter_model or "claude-3-5-haiku-20241022")
    elif adapter == "openai":
        adapter_inst = OpenAIAdapter(model=adapter_model or "gpt-4o-mini")
    else:
        adapter_inst = MockAdapter()

    redaction_config = RedactionConfig()
    enricher = Enricher(adapter_inst, store, redaction_config, budget_tokens=budget)
    cache = NarrationCache(store._conn)

    candidates = _triage_candidates(store, cache, redaction_config)
    items: list[dict] = []
    for n, _reason, cur_hash in candidates:
        items.append(
            {
                "unit": LogicalUnit(
                    kind="paragraph",
                    name=n.name,
                    source=n.properties.get("source", ""),
                    content_hash=cur_hash,
                    post_expansion=bool(n.properties.get("replacing_applied")),
                ),
                "source_node_id": n.id,
                "codebase_id": n.codebase_id,
            }
        )

    with click.progressbar(
        items,
        label="Enriching",
        item_show_func=lambda i: i["source_node_id"] if i else "",
    ) as bar:
        r = enricher.enrich([i for i in bar])

    store.close()

    if as_json:
        click.echo(json.dumps({
            "status": "ok",
            "command": "enrich",
            "summary": {
                "created": len(r.created),
                "cache_hits": r.cache_hit,
                "tokens_used": r.tokens_used,
                "redacted_total": r.redacted_total,
                "skipped": r.skipped,
            },
            "data": None,
            "errors": [],
        }, indent=2, default=str))
    else:
        click.echo(f"created: {len(r.created)}")
        click.echo(f"cache_hits: {r.cache_hit}")
        click.echo(f"tokens_used: {r.tokens_used}")
        click.echo(f"redacted_total: {r.redacted_total}")
        click.echo(f"skipped: {r.skipped}")
