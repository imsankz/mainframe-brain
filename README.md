[![License: Apache 2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](https://www.apache.org/licenses/LICENSE-2.0)
[![Python 3.10–3.14](https://img.shields.io/badge/python-3.10–3.14-blue.svg)](https://www.python.org/downloads/)
[![CI](https://github.com/imsankz/mainframe-brain/actions/workflows/ci.yml/badge.svg)](https://github.com/imsankz/mainframe-brain/actions/workflows/ci.yml)
[![Tests: 61 passing](https://img.shields.io/badge/tests-61%20passing-brightgreen.svg)](#)
[![Scope: open-source, model-agnostic](https://img.shields.io/badge/scope-open--source,%20model--agnostic-orange.svg)](#)

# Mainframe Brain

**An open-source, model-agnostic knowledge system for legacy mainframe applications.**

> Deterministic extraction of COBOL, JCL, CICS, DB2, and VSAM structure into a portable knowledge graph you own — with selective, content-hashed LLM enrichment of undocumented business rules, so the cost of maintaining institutional knowledge approaches **zero over time.**

If your team has millions of lines of COBOL and the engineers who understand it are retiring, this is the missing middle layer between *parser* and *migration accelerator*: a tool that builds something a team **owns**, that **persists**, and that **compounds** the longer it's used — without vendor lock-in and without re-paying token costs for unchanged code.

## Why this exists

Most "AI for mainframe" tooling does one of two things:
- **Parses** COBOL into an AST/XML dump and stops there.
- **Sells a migration** — vendor-locked, black-box, optimized for "convert to Java" not "help engineers understand."

Neither builds persistent team-owned understanding. Mainframe Brain does, by separating the **free layer** (deterministic structure extraction — zero LLM tokens) from the **expensive layer** (selective LLM narration of undocumented business logic — once per unique piece of logic, ever), and writing the result to a portable, versionable knowledge graph.

## What it does

1. **Extract** (Layer 1, zero tokens) — parses COBOL, JCL, CICS BMS, DB2 DDL, SQL PL stored procedures, DB2 triggers, and VSAM/sequential files.
2. **Triage** (Layer 3, zero tokens) — content-hash diffs against the last run, deduplicates near-identical paragraphs, ranks by deterministic risk (cyclomatic + GOTO density + external calls + cascade depth + trigger-chain depth + parse-confidence penalty).
3. **Redact** (Layer 3.5, hard gate) — SSN-shaped numbers, card numbers, IBAN, routing numbers, embedded credentials are scrubbed before anything reaches a model.
4. **Enrich** (Layer 4, only new/changed units) — narrates the undocumented 80% of business logic. Cache keys are *post-expansion-and-post-redaction* content hashes — re-running on unchanged code costs nearly zero tokens.
5. **Query** (Layer 6, zero tokens) — call-graph, data-lineage, trigger-chain, and change-impact queries answered by graph traversal alone.

## Demo

A full JCL → Program → Subprogram call chain, end-to-end, offline (zero LLM secrets needed — the mock adapter narrates for demo purposes):

```bash
pip3 install -e ".[dev]" --break-system-packages
rm -f /tmp/mb.db
mainframe-brain extract examples/cobol    --out /tmp/mb.db
mainframe-brain extract examples/db2      --out /tmp/mb.db
mainframe-brain extract examples/jcl      --out /tmp/mb.db
mainframe-brain extract examples/cics_bms --out /tmp/mb.db

# Which job runs which program? (canonical mainframe question)
mainframe-brain query --store-path /tmp/mb.db "what runs INTCALC01"
# → Program:default:INTCALC01 is invoked by:
#     --EXEC from--> JCLStep:default:STEP-CALC2 [JCLJob:default:PAYRUN]

# Which program CALLs which subprogram?
mainframe-brain query --store-path /tmp/mb.db "what runs SUBPROG"
# → Program:default:SUBPROG is invoked by:
#     --CALL from--> Program:default:INTCALC01

# Impact analysis — "if I change this, what breaks"
mainframe-brain query --store-path /tmp/mb.db "impact of ACCOUNTS"
mainframe-brain query --store-path /tmp/mb.db "show triggers on TXNLOG"
mainframe-brain query --store-path /tmp/mb.db "what touches ACCTFLDS"

# Selective LLM enrichment — defaults to mock adapter for offline demos
mainframe-brain enrich --store-path /tmp/mb.db --budget 20000 --adapter mock
# → created: 6, cache_hits: 0, tokens_used: 182

# Review workflow
mainframe-brain verify   --store-path /tmp/mb.db "BusinessRule:default:2000-CALC-INTEREST:987b31a8"
mainframe-brain flag     --store-path /tmp/mb.db --rule "BusinessRule:default:9000-ERROR:7b1c624e" --reason "needs SME review"
mainframe-brain edit-rule --store-path /tmp/mb.db --rule "BusinessRule:default:0000-MAIN:e8b6f26b" --rule-text "Main driver schedule paragraph"
```

For real LLM enrichment, set `ANTHROPIC_API_KEY` (or `OPENAI_API_KEY`) and pass `--adapter anthropic` (or `--adapter openai`).

## Architecture

```
Legacy source repo
        │
        ▼
Deterministic extractors   (Layer 1 — zero LLM tokens)
        │
        ▼
Knowledge graph            (Layer 2 — structural facts)
        │
        ▼
Change & risk triage        (Layer 3 — decides what's worth spending tokens on)
        │
        ▼
Redaction pass              (Layer 3.5 — hard gate before any token is spent)
        │
        ▼
Selective LLM enrichment    (Layer 4 — only new/changed/high-value units)
        │
        ▼
Persistent brain            (Layer 5 — versioned, queryable, portable)
        │
        ▼
Graph explorer + Change-impact + Chat/query layer   (Layer 6 — interfaces)
        │
        └──── future runs feed back into Layer 3, re-analyzing only diffs
```

Six layers, strictly ordered, each with a narrow contract to the next. Full design and rationale in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — including how the 9 review-driven gaps (VSAM, COPY REPLACING post-expansion hashing, redaction gate, IMS/CICS control flow, partial-parse reporting, change-impact, external boundaries, reports) are folded in. Versioned graph schema in [`docs/SCHEMA.md`](docs/SCHEMA.md); migration history in [`docs/MIGRATIONS.md`](docs/MIGRATIONS.md).

**Key property:** understanding compounds. The first run costs tokens proportional to the *unsolved* business logic. Every subsequent run costs tokens proportional to what *changed*. Six months later, changing one line in a 40,000-line codebase re-queues exactly one paragraph for re-enrichment — and the previously-verified rule is flagged stale until a human signs off again.

## Install

```bash
pip install mainframe-brain                # stable, when released
# or from source (development):
pip3 install -e ".[dev]" --break-system-packages
```

Python ≥ 3.10. macOS system Python 3.14 needs the `--break-system-packages` flag because of PEP 668.

## Project layout

```
mainframe_brain/
├── extractors/          # one folder per artifact type — community contributes here
│   ├── cobol/  copybook/  vsam/  jcl/  cics_bms/
│   ├── db2_ddl/  sql_pl/  triggers/        (procedural-DB first-class)
│   ├── report/  external_boundary/         (schema-ready stubs)
│   └── ims_db/  ims_dc/  cics_control_flow/  (deferred)
├── graph/                # versioned schema + SQLite store (swappable backend)
├── triage/               # diff, dedup, risk scoring
├── redaction/            # L3.5 hard gate
├── enrichment/          # LLM-calling code — model-agnostic (mock/anthropic/openai adapters)
├── cli.py                # L6 entry — thin orchestrator only
└── skills/SKILL.md      # Claude Code/Desktop/Cowork packaging
```

## Comparison positioning

**vs IBM Watsonx Code Assistant for Z:** open-source and model-agnostic vs platform-locked; portable Markdown/graph artifacts you own vs a vendor dashboard; runs offline with a mock adapter vs requires a managed service.

**vs migration-accelerator consultants:** documents and preserves understanding of the system you have — doesn't sell you a Java rewrite. The graph is a portable artifact you commit next to your source.

## Contributing

Adding a new artifact type = new folder under `extractors/`. Adding a new LLM provider = new adapter under `enrichment/models/`. See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the cross-extractor ownership protocol and golden-fixture conventions. CI runs on Python 3.10–3.14 (`ruff` + `pytest` + CLI smoke).

## Status

Pre-alpha. 61 tests (unit + golden) green, ruff clean.

**Phase 1–2 shipped:** COBOL + copybook + VSAM + DB2 DDL + SQL PL stored procedures + triggers + JCL + CICS BMS extractors, SQLite graph store, triage, redaction gate, selective LLM enrichment (mock + real adapters), CLI for extract/triage/enrich/query/explore/verify/flag/edit-rule.

**Deferred (schema-ready, deliberately not MVP-blocking):** IMS DB/DC, CICS XCTL/LINK control flow, live DB2 catalog ingestion, D3 explorer.

## License

Apache 2.0 — explicit patent grant chosen over MIT for enterprise adoption in a regulated industry. Don't let scope creep turn this into a tool that claims regulatory authority it hasn't earned: this is a documentation and knowledge-preservation aid, **not** a compliance or audit tool.

## Author

Sankalp Singh — mainframe modernization, AI-and-COBOL, knowledge preservation for retiring-engineer estates.
