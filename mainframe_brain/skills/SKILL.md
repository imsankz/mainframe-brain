---
name: mainframe-brain
description: Point Mainframe Brain at a mainframe source tree (COBOL/JCL/DB2/VSAM), extract
  a knowledge graph deterministically, optionally enrich undocumented business rules with
  an LLM (cached, redacted, provenance-tracked), and query the graph for call/lineage/trigger
  impact, blast radius, and trigger chains. Use when the user says "mainframe brain",
  "analyze this COBOL/DB2 estate", "what touches this table", "impact of changing this field",
  "show trigger chains", "extract structure from COBOL", or wants the Mainframe Brain pipeline
  run against a path. Works fully offline with the mock adapter; set ANTHROPIC_API_KEY or
  OPENAI_API_KEY and pass --adapter anthropic|openai for real LLM enrichment.
---

# Mainframe Brain Skill

Deterministic-extraction + selective-LLM-enrichment knowledge system for legacy mainframe code.

## Pipeline

1. **Extract** (Layer 1, zero tokens) — walk a source tree, run a matching extractor per artifact type, persist nodes/edges to a SQLite `brain.db`.
2. **Triage** (Layer 3, zero tokens) — diff by content hash, dedup, risk-rank (cyclomatic + goto + external calls + cascade/trigger depth).
3. **Redact** (Layer 3.5, hard gate) — SSN/card/IBAN/credential patterns scrubbed before any LLM call. Cache keys are post-redaction hashes.
4. **Enrich** (Layer 4, only tokens) — narrate BusinessRules for paragraphs with cache hit short-circuit. New/changed units only.
5. **Query** (Layer 6, zero tokens) — `what touches X`, `impact of X`, `show triggers on T`.

## Commands

Run from repo root (after `pip install -e ".[dev]"`):

```bash
# Extract structure to a graph file (offline, zero LLM)
mainframe-brain extract PATH --out brain.db --codebase-id default

# Inspect
mainframe-brain list-nodes --store-path brain.db [--type Paragraph]

# Pure-graph queries (offline)
mainframe-brain query --store-path brain.db "what touches ACCOUNTS"
mainframe-brain query --store-path brain.db "impact of WS-ACCOUNT-ID"
mainframe-brain query --store-path brain.db "show triggers on ACCOUNTS"

# Mermaid neighborhood
mainframe-brain explore --store-path brain.db --node "Program:default:INTCALC01" --format mermaid

# LLM enrichment (mock by default; --adapter anthropic|openai for real)
mainframe-brain enrich --store-path brain.db --budget 20000 --adapter mock

# Human sign-off on an inferred rule
mainframe-brain verify --store-path brain.db "BusinessRule:default:2000-CALC-INTEREST:987b31a8"
```

## What to do when invoked

1. If the user gives a path, run `extract` against it.
2. Run `list-nodes` to summarize what was found.
3. Ask the user which query they want (touching / impact / triggers) — or pick from their phrasing.
4. If they want LLM narration, default to `--adapter mock` for offline demos; offer to switch to real provider if `ANTHROPIC_API_KEY`/`OPENAI_API_KEY` is set.
5. After enrichment, surface unverified BusinessRules (human_verified=False) for review and call `verify` when the user signs off.

## Constraints

- Never send raw source to an LLM. Redaction is a hard gate — if redaction is disabled, refuse to enrich.
- Treat LLM-derived BusinessRules as unverified documentation, never ground truth, until `verify` is called.
- Cache keys are post-redaction, post-expansion (COPY REPLACING) content hashes — that's why a re-run on unchanged code costs nearly zero tokens.

See `docs/ARCHITECTURE.md` and `docs/SCHEMA.md` for the full design and schema contract.