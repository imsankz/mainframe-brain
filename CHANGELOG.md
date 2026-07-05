# Changelog

All notable changes to Mainframe Brain will be documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- CI workflow (ruff + pytest + CLI smoke) on Python 3.10–3.14.
- `AGENTS.md` for opencode/anomaly agents.
- `CHANGELOG.md`, `CONTRIBUTING.md`, `MIGRATIONS.md`.
- `triage` CLI command — diff against the brain, build a risk-ranked work queue, emit it as JSON.
- `build-graph` CLI command — re-open an existing brain and print its summary (alias for `list-nodes --summary`).
- `flag` and `edit-rule` CLI commands — full approve / flag-as-wrong / edit review workflow per §8.
- `--low-confidence` filter for `list-nodes` — surfaces partial-parse nodes (`parse_confidence < 1.0`).
- `--include-units` flag for `extract` so logical units flow into JSON for later re-enrichment.
- JCL extractor + golden fixture (`jcl_extractor`) — Job → Step → Program/Utility → Dataset chains, condition codes, RESTART.
- CICS BMS extractor + golden fixture (`cics_bms_extractor`) — BMS maps, fields, `EXEC CICS SEND/RECEIVE MAP` edges.
- Partial-parse golden fixture — malformed continuation line emits a `Paragraph` with `parse_confidence < 1.0`.
- COPY...REPLACING golden fixture — two programs importing the same copybook with different REPLACING get different post-expansion hashes (gap #2 fix verified).
- Realistic IBM-style COBOL sample at `examples/cobol/PAYROLL01.cbl`.
- Cross-extractor ownership protocol: DB2DDLExtractor no longer emits Trigger nodes (TriggerExtractor owns them); SQLPLExtractor owns StoredProcedure nodes exclusively.

### Changed
- `extract` now runs every matching extractor per file (multi-extractor per file is a documented design property — cobol + vsam co-extract .cbl). Previously it stopped at the first match which silently dropped VSAM row lineage.
- `verify` CLI bumps `last_verified` and writes a `node_history` entry; `human_verified=False` round-trips correctly now.
- `diff_against` is now wired into the `triage` command — the incremental re-enrich loop ("only changed units") actually works end-to-end.

### Fixed
- DB2DDLExtractor emitted Trigger marker nodes that collided with TriggerExtractor's nodes (4 triggers for 2 declared). DB2DDL now owns only Table/Column/View/Constraint nodes; TriggerExtractor exclusively owns Trigger nodes.
- `trigger` and `db2_ddl` `can_handle` both matched `.ddl` files containing `CREATE TRIGGER` — now TriggerExtractor owns Trigger nodes and DB2DDL still owns Table/Column/View/Constraint in the same file with no collisions.

## [0.1.0] — 2026-07-05

### Added
- Initial public implementation: 6-layer pipeline (extract → graph → triage → redaction → enrich → interfaces) + Layer 3.5 redaction gate.
- Schema v1.1: 18 node types, 16 edge types, `parse_confidence`, `codebase_id` multi-tenancy.
- Extractors: cobol, copybook (post-expansion hashing), vsam (KSDS/ESDS/RRDS), db2_ddl, sql_pl, triggers. Deferred stubs: report, external_boundary, ims_db, ims_dc, cics_control_flow.
- SQLiteGraphStore with additive-with-history (`node_history` table), `diff_against`.
- Triage: diff, dedup, risk scoring (cyclomatic + goto + cascade depth + trigger-chain depth + parse-confidence penalty).
- Redaction gate: SSN/card/IBAN/routing/credential patterns, post-redaction hash key.
- Enrichment: MockAdapter (offline) + Anthropic + OpenAI adapters (lazy), NarrationCache, provenance, budget.
- CLI: extract, list-nodes, query (touching/impact/triggers), explore (mermaid), enrich, verify.
- Docs: ARCHITECTURE.md (gap fixes 1–9 folded), SCHEMA.md, SKILL.md.
- Examples: INTCALC01.cbl + ACCTFLDS.cpy, schema.ddl, VSMAPP01.cbl.
- 28 tests (unit + golden), ruff-clean.