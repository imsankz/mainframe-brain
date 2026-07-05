from __future__ import annotations

from mainframe_brain.enrichment import Enricher, MockAdapter
from mainframe_brain.extractors.base import LogicalUnit, content_hash
from mainframe_brain.graph import make_node_id
from mainframe_brain.graph.schema import Node, NodeType
from mainframe_brain.graph.sqlite_store import SQLiteGraphStore
from mainframe_brain.redaction import RedactionConfig


def _make_store():
    store = SQLiteGraphStore(":memory:")
    store.add_node(
        Node(
            id=make_node_id("Paragraph", "default", "CALC-INTEREST"),
            type=NodeType.PARAGRAPH,
            name="CALC-INTEREST",
            codebase_id="default",
        )
    )
    return store


def test_enrich_creates_business_rule_and_caches():
    store = _make_store()
    adapter = MockAdapter()
    enricher = Enricher(adapter, store, RedactionConfig(), budget_tokens=100000)

    unit = LogicalUnit(
        kind="paragraph",
        name="CALC-INTEREST",
        source="PERFORM UNTIL EOF\n  COMPUTE RATE = 0.5\nEND-PERFORM.",
        content_hash=content_hash("PERFORM UNTIL EOF\n  COMPUTE RATE = 0.5\nEND-PERFORM."),
        post_expansion=False,
    )

    items = [{"unit": unit, "source_node_id": make_node_id("Paragraph", "default", "CALC-INTEREST")}]

    r1 = enricher.enrich(items)
    assert len(r1.created) == 1
    br = r1.created[0]
    assert br.type == NodeType.BUSINESS_RULE
    assert br.properties["human_verified"] is False
    assert br.properties["confidence"] == 0.5
    assert "redacted_count" in br.properties

    r2 = enricher.enrich(items)
    assert len(r2.created) == 0
    assert r2.cache_hit == 1


def test_redaction_gate():
    store = _make_store()

    captured = []

    class _Spy(MockAdapter):
        def complete(self, system, user, max_tokens=1024):
            captured.append(user)
            return super().complete(system, user, max_tokens)

    adapter = _Spy()

    class _Config(RedactionConfig):
        pass

    enricher = Enricher(adapter, store, RedactionConfig(), budget_tokens=100000)

    ssn_text = "* comment 123-45-6789\nPERFORM X."
    unit = LogicalUnit(
        kind="paragraph",
        name="PAR-X",
        source=ssn_text,
        content_hash=content_hash(ssn_text),
        post_expansion=False,
    )
    items = [{"unit": unit, "source_node_id": make_node_id("Paragraph", "default", "CALC-INTEREST")}]

    r = enricher.enrich(items)
    assert r.redacted_total >= 1
    assert r.created
    assert r.created[0].properties["redacted_count"] >= 1
    assert "[REDACTED]:SSN" in captured[0]