"""verify / flag / edit-rule — human review commands for BusinessRule nodes."""
from __future__ import annotations

import json

import click

from mainframe_brain.cli._common import _now_iso, _open, _resolve_rule


@click.command()
@click.option("--store-path", "store_path", required=True)
@click.argument("rule_id")
@click.option("--json", "as_json", is_flag=True, help="Output JSON to stdout.")
def verify(store_path: str, rule_id: str, as_json: bool) -> None:
    """Mark a BusinessRule node human_verified=True (approve). Clears any stale flag."""
    store = _open(store_path)
    from mainframe_brain.enrichment.cache import NarrationCache

    n = _resolve_rule(store, rule_id)
    if not n:
        if as_json:
            click.echo(json.dumps({
                "status": "error",
                "command": "verify",
                "summary": {"rule_id": rule_id, "verified": False,
                            "reason": f"no BusinessRule matching '{rule_id}'"},
                "data": None,
                "errors": [],
            }, indent=2, default=str))
        else:
            click.echo(f"no BusinessRule matching '{rule_id}'")
        store.close()
        return

    n.properties["human_verified"] = True
    n.properties.pop("flagged_reason", None)
    n.properties.pop("flagged_at", None)
    n.last_verified = _now_iso()
    store.add_node(n)
    cache = NarrationCache(store._conn)
    cache.mark_verified(n.content_hash, True)
    cache.mark_stale(n.content_hash, False)

    if as_json:
        click.echo(json.dumps({
            "status": "ok",
            "command": "verify",
            "summary": {"node": n.id, "verified": True, "content_hash": n.content_hash},
            "data": None,
            "errors": [],
        }, indent=2, default=str))
    else:
        click.echo(f"verified: {n.id}")
    store.close()


@click.command(name="flag")
@click.option("--store-path", "store_path", required=True)
@click.option("--rule", "rule_id", required=True)
@click.option("--reason", required=True)
@click.option("--json", "as_json", is_flag=True, help="Output JSON to stdout.")
def flag_rule(store_path: str, rule_id: str, reason: str, as_json: bool) -> None:
    """Flag a BusinessRule as wrong. Marks the narration cache stale so triage re-queues it."""
    store = _open(store_path)
    from mainframe_brain.enrichment.cache import NarrationCache

    n = _resolve_rule(store, rule_id)
    if not n:
        if as_json:
            click.echo(json.dumps({
                "status": "error",
                "command": "flag",
                "summary": {"rule_id": rule_id, "flagged": False,
                            "reason": f"no BusinessRule matching '{rule_id}'"},
                "data": None,
                "errors": [],
            }, indent=2, default=str))
        else:
            click.echo(f"no BusinessRule matching '{rule_id}'")
        store.close()
        return

    n.properties["human_verified"] = False
    n.properties["flagged_reason"] = reason
    n.properties["flagged_at"] = _now_iso()
    store.add_node(n)
    NarrationCache(store._conn).mark_stale(n.content_hash, True)

    if as_json:
        click.echo(json.dumps({
            "status": "ok",
            "command": "flag",
            "summary": {"node": n.id, "flagged": True, "reason": reason},
            "data": None,
            "errors": [],
        }, indent=2, default=str))
    else:
        click.echo(f"flagged: {n.id} reason={reason!r}")
    store.close()


@click.command(name="edit-rule")
@click.option("--store-path", "store_path", required=True)
@click.option("--rule", "rule_id", required=True)
@click.option("--rule-text", "text", required=True)
@click.option("--json", "as_json", is_flag=True, help="Output JSON to stdout.")
def edit_rule(store_path: str, rule_id: str, text: str, as_json: bool) -> None:
    """Replace a BusinessRule's rule text and mark it human-verified/edited."""
    store = _open(store_path)
    from mainframe_brain.enrichment.cache import NarrationCache

    n = _resolve_rule(store, rule_id)
    if not n:
        if as_json:
            click.echo(json.dumps({
                "status": "error",
                "command": "edit-rule",
                "summary": {"rule_id": rule_id, "edited": False,
                            "reason": f"no BusinessRule matching '{rule_id}'"},
                "data": None,
                "errors": [],
            }, indent=2, default=str))
        else:
            click.echo(f"no BusinessRule matching '{rule_id}'")
        store.close()
        return

    n.properties["rule"] = text
    n.properties["human_verified"] = True
    n.properties["edited_by_human"] = True
    n.last_verified = _now_iso()
    store.add_node(n)

    cache = NarrationCache(store._conn)
    payload = cache.get(n.content_hash)
    if payload is not None:
        payload.pop("stale", None)
        payload["rule"] = text
        payload["human_verified"] = True
        cache.put(n.content_hash, payload, human_verified=True)
        cache.mark_stale(n.content_hash, False)

    if as_json:
        click.echo(json.dumps({
            "status": "ok",
            "command": "edit-rule",
            "summary": {"node": n.id, "edited": True},
            "data": None,
            "errors": [],
        }, indent=2, default=str))
    else:
        click.echo(f"edited: {n.id}")
    store.close()
