"""triage — build the re-enrichment work queue (stale/changed paragraphs only)."""
from __future__ import annotations

import json

import click

from mainframe_brain.cli._common import _open, _triage_candidates


@click.command()
@click.option("--store-path", "store_path", required=True)
@click.option("--budget", default=50000, type=int)
@click.option("--threshold", default=3.0, type=float)
@click.option("--json", "as_json", is_flag=True, help="Output JSON to stdout.")
def triage(store_path: str, budget: int, threshold: float, as_json: bool) -> None:
    """Layer 3 — build the re-enrichment work queue (stale/changed paragraphs only)."""
    store = _open(store_path)
    from mainframe_brain.enrichment.cache import NarrationCache
    from mainframe_brain.redaction import RedactionConfig
    from mainframe_brain.triage.risk import combined_risk, risk_score

    cache = NarrationCache(store._conn)
    candidates = _triage_candidates(store, cache, RedactionConfig())
    re_items = [
        (n, reason, cur_hash)
        for n, reason, cur_hash in candidates
        if reason != "new"
    ]

    ranked: list[dict] = []
    for n, reason, cur_hash in re_items:
        base = risk_score(n)
        score = combined_risk(store, n, base)
        tokens_est = max(1, len(n.properties.get("source", "")) // 4)
        ranked.append(
            {
                "name": n.name,
                "node_id": n.id,
                "risk_score": round(score, 4),
                "tokens_estimate": tokens_est,
                "reason": reason,
                "content_hash": cur_hash,
            }
        )

    ranked.sort(key=lambda it: it["risk_score"], reverse=True)

    chosen: list[dict] = []
    used = 0
    skipped = 0
    for item in ranked:
        if item["risk_score"] < threshold:
            skipped += 1
            continue
        if used + item["tokens_estimate"] > budget:
            skipped += 1
            continue
        chosen.append(item)
        used += item["tokens_estimate"]

    store.close()

    if as_json:
        click.echo(json.dumps({
            "status": "ok",
            "command": "triage",
            "summary": {
                "items": len(chosen),
                "total_tokens": used,
                "budget_remaining": budget - used,
                "skipped_count": skipped,
            },
            "data": chosen,
            "errors": [],
        }, indent=2, default=str))
    else:
        click.echo(
            f"work queue: {len(chosen)} item(s), {used} tokens, budget {budget}, "
            f"skipped {skipped}"
        )
        for item in chosen[:10]:
            click.echo(
                f"{item['name']} | {item['risk_score']} | "
                f"{item['tokens_estimate']} | {item['reason']}"
            )
