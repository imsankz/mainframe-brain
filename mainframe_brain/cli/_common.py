"""Shared utility functions for CLI commands."""
from __future__ import annotations

import hashlib
import importlib
import json
import pkgutil
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone

import click

from mainframe_brain.graph.schema import EdgeType, Node, NodeType
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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _content_hash(text: str) -> str:
    normalized = "\n".join(line.rstrip() for line in text.splitlines())
    return hashlib.sha256(normalized.encode("utf-8", errors="replace")).hexdigest()


def _redact(text, config):
    from mainframe_brain.redaction import redact

    return redact(text, config)


def _triage_candidates(store, cache, redaction_config) -> list[tuple[Node, str, str]]:
    """Paragraphs needing (re-)enrichment: (node, reason, post_redaction hash)."""
    impl_edges: dict[str, list[str]] = defaultdict(list)
    for e in store.all_edges():
        if e.type == EdgeType.IMPLEMENTS_RULE:
            impl_edges[e.src].append(e.dst)
    out: list[tuple[Node, str, str]] = []
    for n in store.all_nodes():
        if n.type != NodeType.PARAGRAPH:
            continue
        source = n.properties.get("source", "")
        if not source:
            continue
        redacted, _report = _redact(source, redaction_config)
        cur_hash = _content_hash(redacted)
        br_ids = impl_edges.get(n.id, [])
        if not br_ids:
            out.append((n, "new", cur_hash))
            continue
        brs = [b for b in (store.get_node(bid) for bid in br_ids) if b is not None]
        current = any(
            b.content_hash == cur_hash and not cache.is_stale(b.content_hash) for b in brs
        )
        if current:
            continue
        reason = "stale" if any(cache.is_stale(b.content_hash) for b in brs) else "changed"
        out.append((n, reason, cur_hash))
    return out


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


def _resolve_rule(store, rule_id: str) -> Node | None:
    n = store.get_node(rule_id)
    if not n:
        for cand in store.all_nodes():
            if cand.type == NodeType.BUSINESS_RULE and rule_id in cand.name:
                n = cand
                break
    if not n or n.type != NodeType.BUSINESS_RULE:
        return None
    return n


@dataclass
class CliResult:
    """Structured output for --json mode."""
    status: str = "ok"
    command: str = ""
    summary: dict = field(default_factory=dict)
    data: object = None
    errors: list[str] = field(default_factory=list)


def _emit(result: CliResult, as_json: bool) -> None:
    """Output result as JSON or human-readable text."""
    if as_json:
        payload: dict = {
            "status": result.status,
            "command": result.command,
            "summary": result.summary,
            "data": result.data,
            "errors": result.errors,
        }
        click.echo(json.dumps(payload, indent=2, default=str))
    else:
        for key, val in result.summary.items():
            if isinstance(val, dict):
                click.echo(f"{key}:")
                for k, v in sorted(val.items()):
                    click.echo(f"  {k}: {v}")
            else:
                click.echo(f"{key}: {val}")
        if result.data is not None:
            if isinstance(result.data, list):
                for item in result.data:
                    if isinstance(item, dict):
                        click.echo(json.dumps(item, default=str))
                    else:
                        click.echo(str(item))
            elif isinstance(result.data, dict):
                click.echo(json.dumps(result.data, indent=2, default=str))
        for err in result.errors:
            click.echo(err, err=True)
