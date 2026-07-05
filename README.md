# Mainframe Brain

**Open-source, model-agnostic knowledge system for legacy mainframe applications.**

Mainframe Brain extracts structure deterministically from COBOL, JCL, CICS, and DB2
artifacts, builds a persistent knowledge graph you own, and selectively uses an LLM
only for the undocumented business logic a parser can't reach — once, ever, per
unique piece of logic.

* **Free layer** — deterministic extraction. Zero LLM tokens.
* **Expensive layer** — selective LLM enrichment. Content-hashed, cached, provenance-tracked.
* **The product** — a portable, versioned knowledge graph a team owns.

## Install

```bash
pip install -e ".[dev]"
```

## Quickstart

```bash
mainframe-brain extract examples/cobol/ --out brain.db   # Layer 1 → graph
mainframe-brain build-graph --store-path brain.db        # summarize counts
mainframe-brain triage     --store-path brain.db         # Layer 3 → re-enrichment queue
mainframe-brain enrich     --store-path brain.db --budget 50000  # Layer 4 (mock adapter)
mainframe-brain verify     --store-path brain.db <rule-id>       # approve (review workflow)
mainframe-brain flag       --store-path brain.db --rule <id> --reason "wrong"  # flag-as-wrong
mainframe-brain edit-rule  --store-path brain.db --rule <id> --rule-text "..."  # edit
mainframe-brain query      --store-path brain.db "what touches ACCOUNTS?"
mainframe-brain explore    --store-path brain.db --node Program:default:INTCALC01
```

## Architecture

Six layers: extractors → graph → triage → selective LLM enrichment → persistent brain → interfaces.
See [`docs/SCHEMA.md`](docs/SCHEMA.md) for the versioned graph schema and
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full design.

## Status

Pre-alpha. Phase 1 (COBOL + copybook → SQLite graph) under construction.

## License

Apache 2.0. Explicit patent grant — chosen for enterprise adoption in a regulated industry.