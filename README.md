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
mainframe-brain extract examples/cobol/        # Layer 1 → graph
mainframe-brain build-graph  brain.db          # assemble graph (SQLite)
mainframe-brain triage      brain.db           # Layer 3 → work queue
mainframe-brain enrich      brain.db --budget 50000   # Layer 4 (needs an LLM adapter)
mainframe-brain query       brain.db "what touches ACCOUNTS?"
mainframe-brain explore     brain.db --node Program:default:INTCALC01
```

## Architecture

Six layers: extractors → graph → triage → selective LLM enrichment → persistent brain → interfaces.
See [`docs/SCHEMA.md`](docs/SCHEMA.md) for the versioned graph schema and
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full design.

## Status

Pre-alpha. Phase 1 (COBOL + copybook → SQLite graph) under construction.

## License

Apache 2.0. Explicit patent grant — chosen for enterprise adoption in a regulated industry.