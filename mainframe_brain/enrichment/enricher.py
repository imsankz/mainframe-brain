"""Layer 4 — selective LLM enrichment. The only stage that spends tokens."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

from mainframe_brain.extractors.base import LogicalUnit, content_hash
from mainframe_brain.graph import make_node_id
from mainframe_brain.graph.schema import Edge, EdgeType, Node, NodeType
from mainframe_brain.redaction import RedactionConfig, redact

from .cache import NarrationCache
from .models.base import LLMAdapter
from .prompts.business_rule import PROMPT_VERSION, SYSTEM, render_prompt
from .queue import EnrichmentQueue


@dataclass
class EnrichmentResult:
    created: list[Node] = field(default_factory=list)
    reused: list[str] = field(default_factory=list)   # hashes reused from cache
    skipped: int = 0                                   # filtered out (budget)
    tokens_used: int = 0
    cache_hit: int = 0
    redacted_total: int = 0


class Enricher:
    def __init__(
        self,
        adapter: LLMAdapter,
        store,
        redaction_config: RedactionConfig | None = None,
        budget_tokens: int = 50000,
        prompt_version: str = PROMPT_VERSION,
    ):
        self.adapter = adapter
        self.store = store
        self.redaction_config = redaction_config or RedactionConfig()
        self.budget_tokens = budget_tokens
        self.prompt_version = prompt_version
        self.cache = NarrationCache(store._conn)

    def enrich(self, items: list[dict]) -> EnrichmentResult:
        """`items`: list of {unit, source_node_id, codebase_id}. Processes in priority order.

        Each item produces one BusinessRule node + one IMPLEMENTS_RULE edge,
        unless a valid cached narration covers its hash already.
        """
        result = EnrichmentResult()

        for item in items:
            if result.tokens_used >= self.budget_tokens:
                result.skipped += 1
                continue

            unit: LogicalUnit = item["unit"]
            source_node_id: str = item["source_node_id"]
            codebase_id: str = item.get("codebase_id", "default")

            redacted, report = redact(unit.source, self.redaction_config)
            if not self.redaction_config.enabled:
                result.skipped += 1
                continue
            post_hash = content_hash(redacted)
            result.redacted_total += report.redacted_count

            cached = self.cache.get(post_hash)
            if cached is not None and not cached.get("stale"):
                result.cache_hit += 1
                result.reused.append(post_hash)
                continue

            user = render_prompt(redacted, unit.kind, unit.name)
            try:
                text, usage = self.adapter.complete(SYSTEM, user)
                result.tokens_used += int(usage.get("output_tokens", 0))
            except Exception:
                result.skipped += 1
                continue

            payload = _parse_payload(text)
            payload["content_hash"] = post_hash
            payload["model"] = usage.get("model", self.adapter.name)
            payload["prompt_version"] = self.prompt_version
            payload["human_verified"] = False
            payload["redacted_count"] = report.redacted_count

            br_id = make_node_id("BusinessRule", codebase_id, f"{unit.name}:{post_hash[:8]}")
            node = Node(
                id=br_id,
                type=NodeType.BUSINESS_RULE,
                name=f"Rule for {unit.name}",
                codebase_id=codebase_id,
                content_hash=post_hash,
                last_verified=_now(),
                properties=payload,
            )
            self.store.add_node(node)
            if not _inherits_existing(node, self.store):
                self.store.add_edge(Edge(
                    src=source_node_id,
                    dst=br_id,
                    type=EdgeType.IMPLEMENTS_RULE,
                    properties={"unit_kind": unit.kind},
                ))

            self.cache.put(post_hash, payload)
            result.created.append(node)

        return result

    def enrich_from_queue(self, queue: EnrichmentQueue) -> EnrichmentResult:
        """Resumable enrichment loop that reads from a persistent queue.

        On restart, in_progress items are reset to pending and retried.
        Already-done items are skipped.
        """
        result = EnrichmentResult()

        # Crash recovery: reset any in-progress items back to pending
        reset_count = queue.reset_in_progress()
        if reset_count:
            result.skipped += reset_count

        while True:
            if result.tokens_used >= self.budget_tokens:
                break

            item = queue.next_pending()
            if item is None:
                break

            source_node_id: str = item["source_node_id"]
            source_node = self.store.get_node(source_node_id)
            if source_node is None:
                queue.mark_done(item["id"])
                result.skipped += 1
                continue

            unit = LogicalUnit(
                kind=item["unit_kind"],
                name=item["unit_name"],
                source=source_node.properties.get("source", ""),
                content_hash=item["unit_hash"],
                post_expansion=bool(source_node.properties.get("replacing_applied")),
            )

            redacted, report = redact(unit.source, self.redaction_config)
            if not self.redaction_config.enabled:
                queue.mark_done(item["id"])
                result.skipped += 1
                continue
            post_hash = content_hash(redacted)
            result.redacted_total += report.redacted_count

            cached = self.cache.get(post_hash)
            if cached is not None and not cached.get("stale"):
                result.cache_hit += 1
                result.reused.append(post_hash)
                queue.mark_done(item["id"])
                continue

            user = render_prompt(redacted, unit.kind, unit.name)
            try:
                text, usage = self.adapter.complete(SYSTEM, user)
                result.tokens_used += int(usage.get("output_tokens", 0))
            except Exception:
                queue.mark_failed(item["id"])
                result.skipped += 1
                continue

            payload = _parse_payload(text)
            payload["content_hash"] = post_hash
            payload["model"] = usage.get("model", self.adapter.name)
            payload["prompt_version"] = self.prompt_version
            payload["human_verified"] = False
            payload["redacted_count"] = report.redacted_count

            codebase_id = item.get("codebase_id", "default")
            br_id = make_node_id("BusinessRule", codebase_id, f"{unit.name}:{post_hash[:8]}")
            node = Node(
                id=br_id,
                type=NodeType.BUSINESS_RULE,
                name=f"Rule for {unit.name}",
                codebase_id=codebase_id,
                content_hash=post_hash,
                last_verified=_now(),
                properties=payload,
            )
            self.store.add_node(node)
            if not _inherits_existing(node, self.store):
                self.store.add_edge(Edge(
                    src=item["source_node_id"],
                    dst=br_id,
                    type=EdgeType.IMPLEMENTS_RULE,
                    properties={"unit_kind": unit.kind},
                ))

            self.cache.put(post_hash, payload)
            result.created.append(node)
            queue.mark_done(item["id"])

        return result


def _parse_payload(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.lower().startswith("json"):
            text = text[4:]
    try:
        return json.loads(text)
    except Exception:
        return {
            "rule": text[:500],
            "confidence": 0.0,
            "line_range": [None, None],
            "edge_cases": ["parse_failed"],
            "unparsed": text,
        }


def _inherits_existing(_node: Node, _store) -> bool:
    return False


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = ["Enricher", "EnrichmentResult"]