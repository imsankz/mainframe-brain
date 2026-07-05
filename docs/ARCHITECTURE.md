# Mainframe Brain — Architecture & Design Document

**An open-source, model-agnostic knowledge system for legacy mainframe applications**

Author: Sankalp Singh
Status: Draft v2 — pre-implementation design (gaps folded)
License target: Apache 2.0 (permissive, business-friendly, encourages enterprise adoption without scaring legal departments)

---

## 1. Executive summary

Most "AI for mainframe" tooling on the market today does one of two things: it's a **parser** (turns COBOL into an AST or an XML dump and stops there), or it's a **migration accelerator** (vendor-locked, black-box, sells you a rewrite). Neither one builds something that *persists* and *compounds* — a team's understanding of their own system, owned by the team, growing more valuable the longer it's used.

Mainframe Brain is the missing middle layer: an open-source system that

1. **Extracts structure deterministically** (no LLM, no tokens, no vendor lock-in) from COBOL, JCL, CICS, DB2, and VSAM/flat-file artifacts.
2. **Builds a persistent knowledge graph** of how the system actually fits together — programs, paragraphs, copybooks, fields, jobs, tables, datasets, triggers — as a portable, versionable artifact your team owns.
3. **Selectively and cheaply uses an LLM** to narrate the *business logic* — the undocumented 80% — only where deterministic parsing can't reach, and only once per unique piece of logic, ever.
4. **Never re-does work.** Every subsequent run costs tokens proportional to what *changed*, not what *exists*.
5. **Exposes the result** as an explorable graph, a queryable chat interface, and a set of Claude Skills anyone can drop into Claude Code, Claude Desktop, or Cowork.

The design goal is that a mid-size bank's mainframe estate — millions of lines of COBOL — should be analyzable on a normal token budget, and re-analyzable on almost no budget at all, because the system remembers what it already figured out.

---

## 2. Problem statement

Three separate problems keep getting bundled together and solved badly as one:

| Problem | Naive approach | Why it fails |
|---|---|---|
| "Understand what this program does" | Paste source into an LLM, ask it to explain | Burns enormous tokens on every run; explanation isn't stored anywhere; re-running from scratch every time; doesn't scale past a handful of programs |
| "Document a legacy estate" | Vendor migration tool | Closed-source, output trapped in a dashboard, optimized for "convert to Java" not "help engineers understand," expensive licensing |
| "Preserve institutional knowledge before people retire" | Wiki pages written by hand | Goes stale immediately, nobody maintains it, disconnected from the actual code |

The insight that unlocks a better answer: **most of what you need to know about a mainframe program is derivable without an LLM at all.** Call graphs, data lineage, job flows, copybook usage — that's all mechanical parsing. The LLM should only ever be asked the one question a parser genuinely can't answer: *"what business rule is this conditional logic actually implementing?"* Everything else is graph traversal.

---

## 3. Core design philosophy

Three principles drive every architectural decision below:

**Principle 1 — Separate the free layer from the expensive layer, and make the boundary explicit.**
Deterministic extraction (regex/grammar-based parsing) costs compute, not tokens. It should do as much of the work as physically possible before an LLM is ever invoked. If you find yourself asking an LLM "what does this PERFORM statement call," that's a parser bug, not a prompt problem.

**Principle 2 — Never pay to learn the same thing twice.**
Every unit of logic that gets sent to an LLM is content-hashed. If the hash already has a cached, validated narration, reuse it — even across different programs, since copybooks and boilerplate paragraphs repeat constantly in mainframe codebases. Re-running the tool on an unchanged codebase should cost close to zero tokens. **The hash is computed POST-expansion** (see 5.5) and **POST-redaction** (see 4.4b), so the cache is keyed to the exact text the LLM sees.

**Principle 3 — The graph is the product, not a side effect.**
Everything the system learns — mechanically or via LLM — gets written to one persistent, portable, versioned knowledge graph. The graph is what a team actually owns at the end of this. Chat interfaces, visualizations, and reports are just views over it.

---

## 4. System architecture

Seven stages, strictly ordered, each with a narrow contract to the next:

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

### 4.1 Layer 1 — Deterministic extractors

One plugin per artifact type. No LLM involvement whatsoever. Each extractor implements a common contract:

```python
class Extractor(Protocol):
    artifact_type: str  # "cobol", "jcl", "cics_bms", "db2_ddl", "vsam", ...

    def can_handle(self, file_path: Path) -> bool: ...

    def extract(self, file_path: Path) -> ExtractionResult:
        """Returns nodes + edges + a content hash per logical unit."""
```

Initial extractors (MVP emit bold):

- **`cobol_extractor`** — walks IDENTIFICATION/DATA/PROCEDURE DIVISION. Produces Program/Paragraph nodes, PERFORM/CALL edges, working-storage fields. Embedded SQL gets *real SQL parsing*, not a regex grab of table names (5.3).
- **`copybook_extractor`** — parses field layouts (REDEFINES, OCCURS, 88-levels), tracks which programs include which copybooks. Hashing is post-expansion (5.5).
- **`vsam_extractor`** — VSAM and sequential files. Parses `SELECT/ASSIGN/FD` clauses, record layouts (tied to copybooks), and `READ/WRITE/REWRITE/DELETE/START` verbs against KSDS/ESDS/RRDS and sequential files, emitting the same `READS`/`WRITES` lineage edges DB2 tables get. In many real estates this is a bigger gap than DB2. (5.6)
- **`jcl_extractor`** — Job → Step → Program/Utility → Dataset chains, condition codes, restart logic.
- **`cics_bms_extractor`** — BMS maps → Screen nodes with fields, linked via `EXEC CICS SEND/RECEIVE MAP`.
- **`db2_ddl_extractor`** — tables/columns/indexes/views/constraints (PK/FK, cascade rules).
- **`sql_pl_extractor`** — stored procedures (SQL PL and COBOL-based) into control-flow graphs (5.1).
- **`trigger_extractor`** — trigger DDL + chain detection (5.2).
- **`report_extractor`** — Report nodes capturing what a job's SYSOUT output *means* to the business (5.8).
- **`external_boundary_extractor`** — MQ Series, CICS web services, anything outside the estate → generic `ExternalSystem` node so outbound edges are marked rather than silently dropped (5.7).

Deferred extractors (documented only — see section 12):
- `ims_db_extractor`, `ims_dc_extractor` — IMS DB/DC (5.9).
- `cics_control_flow_extractor` — XCTL/LINK/RETURN chains, COMMAREA, TSQ/TDQ (5.10).

Recommended parsing approach: **tree-sitter grammars** where mature ones exist (COBOL has community grammars), hand-rolled recursive-descent for JCL/BMS. Avoid pure regex beyond simple field extraction — COBOL's fixed-column format and continuation rules will break naive regex. Every extractor sets `parse_confidence < 1.0` on any node it could not parse cleanly instead of silently dropping or misparsing content (5.11).

Each extractor emits a **content hash per logical unit** (per paragraph, per copybook, per job step) — this hash is the load-bearing piece that makes Layer 3 possible.

### 4.2 Layer 2 — Knowledge graph construction

Deterministic facts from Layer 1 get assembled into a graph. No new information is created here — pure structural assembly.

**Node types:**

| Node type | Key properties |
|---|---|
| `Program` | name, division headers, LOC, last-modified, content hash, `invoked_as_stored_procedure?` |
| `Paragraph` | name, parent program, content hash, cyclomatic complexity, parse_confidence |
| `Copybook` | name, included-by list, field count, `replacing_applied` |
| `Field` | name, PIC clause, level, REDEFINES target, parent copybook/program |
| `JCLJob` | name, steps, schedule info if known |
| `JCLStep` | program/utility invoked, condition codes, datasets touched |
| `Dataset` | name, DSORG, referencing jobs/programs |
| `VSAMDataset` | name, organization (KSDS/ESDS/RRDS), key, record-layout copybook |
| `CICSMap` | map name, fields, screen layout |
| `DB2Table` | name, columns, referencing programs |
| `DB2Column` | name, type, parent table |
| `StoredProcedure` | name, language (SQL PL / COBOL), parameters, complexity, source (catalog vs. file) |
| `Trigger` | name, table, timing, event, referencing clause, complexity |
| `View` | name, defining SQL, underlying tables |
| `Constraint` | type (PK/FK/check), table, cascade rule |
| `Report` | name, triggering job, business purpose, SYSOUT descriptor |
| `ExternalSystem` | name, kind (MQ/HTTP/Vendor), boundary descriptor |
| `BusinessRule` | **LLM-derived** — see 4.4 |

**Edge types:** `CALLS`, `PERFORMS`, `INCLUDES`, `READS`, `WRITES`, `DERIVED_FROM`, `IMPLEMENTS_RULE`, `RENDERS_ON`, `INVOKES_PROC`, `FIRES_ON`, `TRIGGERS_TRIGGER`, `ABSTRACTS`, `CASCADES_TO`, `PRODUCES_REPORT`, `CALLS_EXTERNAL`, `XCTLS` (deferred).

Every node carries `content_hash`, `last_verified`, and `parse_confidence` — these three make incremental re-analysis and partial-parse reporting possible.

### 4.3 Layer 3 — Change & risk triage

Before any token is spent, this stage decides **what's worth analyzing** on this run:

1. **Diff detection** — compare current content hashes against the last stored run. Unchanged nodes are skipped entirely; they already have valid narrations in the brain.
2. **Deduplication** — group nodes by content hash. Analyze each unique hash once; fan the result out to every node sharing it.
3. **Risk-based prioritization** — rank paragraphs by a cheap deterministic score (cyclomatic complexity, GOTO density, external calls, undocumented literals) plus **trigger-chain depth and FK cascade depth as independent risk signals**, since a three-deep cascade is higher-risk to touch than its COBOL complexity alone suggests (see 5).

Output: a prioritized work queue of exactly which logical units go to Layer 4, in what order, respecting a configurable token budget.

### 4.4 Redaction pass — Layer 3.5 (must-have)

A hard gate between triage and any LLM call. Mainframe source routinely contains hardcoded test account numbers, embedded credentials in JCL/FTP scripts, and PII in comments.

- **Default regex patterns:** SSN-shapes, card-shapes, IBAN, US routing numbers, `PASS=/USERID=` assignments, FTP USER/PASS lines, long hex blobs (keys/tokens).
- **Team overrides:** a config of `name -> known secret value` for site-specific secrets that don't match generic shapes.
- **Post-redaction hashing:** the content hash that keys a cached narration is computed on the *redacted* text the LLM actually saw. Adding a new redaction rule does **not** force every paragraph to re-narrate — the *meaning* didn't change, only the scrubbed surface.
- **Report findings, mutate text.** Every redaction produces a `RedactionReport` (kind, span) so the team has an audit trail of what was scrubbed without the raw values themselves being logged back.

Skipped redaction = no enrichment. The gate refuses to open.

### 4.5 Layer 4 — Selective LLM enrichment

The only stage that spends tokens. Spend as few as possible per unit of new understanding:

- **Tiered model use** — fast/cheap model for structural classification ("is this paragraph error-handling boilerplate or business logic?"), strong model for genuinely ambiguous conditional narration.
- **Hierarchical summarization** — narrate at paragraph level once; compose program-level summaries from already-narrated paragraph summaries (cheap concat + one lightweight synthesis call).
- **Structured output** — fixed schema (rule description, confidence, cited line range, edge-case flags), not free text, so it drops straight into the graph.
- **Provenance is mandatory** — every `BusinessRule` records: source content hash, model + prompt version, confidence, `human_verified: bool` (defaults `false`).
- **Budget manifest** — `max_tokens_per_run`, `priority_threshold` let a team run incrementally over weeks instead of one enormous first pass.

### 4.6 Layer 5 — Persistent brain

The accumulated graph, versioned like code:

- Stored as a portable file (or small embedded DB) committable to git.
- Every write is additive-with-history — you can see how the team's understanding evolved.
- Substrate for retrieval: once a `BusinessRule` narration exists, a future question is a graph lookup, not a new LLM call.

### 4.7 Layer 6 — Interfaces

- **Graph explorer** — interactive visual browser of call graph, data lineage, job flows. Lightweight web viewer (force-directed).
- **Change-impact analysis** — a named first-class query capability: "if I change this field, what breaks?" Walks `INCLUDES` → `Field`, `READS`/`WRITES` → `DB2Table`/`VSAMDataset`, `FIRES_ON`/`TRIGGERS_TRIGGER`, `CASCADES_TO`, `ABSTRACTS` (views). Surfaced as `query-impact` in the CLI and chat layer (5.12).
- **Chat/query layer** — natural-language questions answered by graph traversal + cached narrations first, live LLM only when the graph genuinely doesn't have the answer yet (and that new answer is written back into the brain).
- **Claude Skills packaging** — the whole pipeline wrapped as SKILL.md modules.

---

## 5. Data sources, procedural logic, and gap fixes

### 5.1 Stored procedures
- **SQL PL** procedures (`IF`, `WHILE`, `FOR`, cursors, condition handlers, `SIGNAL`) and **COBOL-based** stored procedures (an ordinary COBOL program registered as callable).
- `sql_pl_extractor` builds a control-flow graph the same way the COBOL extractor does for paragraphs and scores complexity identically.
- **v1 decision: DDL exports only** (`db2look` output or equivalent). No live catalog connection. Keeps contribution barrier low; no live credentials just to test.

### 5.2 Triggers
- `Trigger` node: timing (BEFORE/AFTER/INSTEAD OF), event, table, referencing clause, and the triggered action's own procedural-SQL logic.
- `TRIGGERS_TRIGGER` (Trigger → Trigger) — the dangerous edge: when one trigger's DML fires a second. Modeled explicitly as a graph, not discovered by accident.

### 5.3 Full SQL parsing
- Embedded SQL gets a real SQL parser, not a regex table-name grab. Business logic frequently lives in `WHERE` and multi-table `JOIN` conditions.
- Capture host-variable bindings (link SQL predicates back to COBOL working-storage fields), cursors + fetch loops, and flag **dynamic SQL** (`PREPARE`/`EXECUTE IMMEDIATE`) with `dynamic_sql: true` which auto-raises risk score.

### 5.4 Views and referential integrity
- `View` → `ABSTRACTS` → underlying tables. Lineage queries see through views.
- `ON DELETE CASCADE` / `ON UPDATE CASCADE` → `CASCADES_TO` edges; cascade depth counts in risk scoring like trigger chains.

### 5.5 COPY...REPLACING — post-expansion hashing (must-have)

The token-economy design assumes "same copybook = same hash = reuse narration." But `COPY FIELDS REPLACING ==X== BY ==Y==` means identical copybooks expand differently per program.

**Fix:** content hashing happens **POST-expansion**, not on the raw copybook source.
1. `copybook_extractor` records that a `REPLACING` clause was applied (`replacing_applied: true` on the `Copybook` node).
2. The expanded text is what gets hashed and what reaches Layer 4.
3. Cache key = hash of expanded text. Two programs importing the same copybook without REPLACING share a key; two programs importing it with different REPLACING do not — exactly correct.

### 5.6 VSAM and flat-file data access (must-have)

Most estates are not DB2-only. VSAM and sequential files are often a bigger lineage surface than DB2 tables.

- `vsam_extractor` parses `SELECT ... ASSIGN TO` + `FD` clauses in `FILE SECTION`, tying each dataset's record layout to a copybook.
- Organization detection: KSDS / ESDS / RRDS / sequential.
- `READ / WRITE / REWRITE / DELETE / START` verbs emit `READS`/`WRITES` edges to a `VSAMDataset` node exactly the way SQL `SELECT`/`INSERT` emit edges to `DB2Table`.
- A flat sequential file is a `Dataset` node with `DSORG=PS`; a VSAM KSDS is a `VSAMDataset` with `organization=KSDS` and a key field reference.

### 5.7 External system boundaries (deferred-class, schema-ready now)

MQ Series, CICS web services, anything outside the estate.

- Generic `ExternalSystem` node (`kind`: MQ / HTTP / Vendor / Unknown).
- Outbound calls emit `CALLS_EXTERNAL` (Program → ExternalSystem), never silently dropped.
- Schema ships in v1.1 so existing graphs don't need a migration when these extractors land later.

### 5.8 Reports / SYSOUT (deferred-class)

A `Report` node captures what a job's output *means* to the business — not just its code path.

- `PRODUCES_REPORT` edge: `JCLJob`/`JCLStep` → `Report`.
- Properties: name, triggering job, business purpose (manually or LLM-filled), SYSOUT descriptor.
- MVP scope: node + edge schema only; auto-naming from JCL `SYSOUT` classes. Purpose narration ships when enrichment for report descriptors does.

### 5.9 IMS DB/DC (deferred)

Placeholder extractor family `ims_db_extractor` (hierarchical database — DL/I calls, PCB/PSB, segment relationships) and `ims_dc_extractor` (IMS TM message processing). Ships after DB2/CICS are solid. Schema reservations noted in `docs/SCHEMA.md`.

### 5.10 CICS control flow beyond BMS (deferred)

`XCTL`/`LINK`/`RETURN` chains between programs, `COMMAREA` data passed between them, and TSQ/TDQ usage — how pseudo-conversational programs hand off state. Matters more than screen layout for online systems. Deferred to Phase 4+; the `XCTLS` edge type is reserved in schema now.

### 5.11 Partial-parse reporting (must-have)

Vendor COBOL dialects (Micro Focus vs IBM Enterprise COBOL) and old continuation styles will sometimes fail to parse cleanly.

- Every node carries `parse_confidence` (0..1). `<1.0` = partial/low-confidence.
- Extractors emit the partially parsed node plus a parse-warnings list in `properties`; they never silently drop or misparse.
- Triage can downweight priority for `parse_confidence < 0.5` to avoid spending tokens on garbage, but the node remains queryable.
- Golden fixture tests grow the partial-parse corpus intentionally.

### 5.12 Change-impact analysis as a first-class query (deferred-class interface)

"If I change this field, what breaks?" — currently only implied by graph structure.

- Named capability `query-impact` in Layer 6, exposed by CLI and chat.
- Walks: `Field ← INCLUDES ← Copybook/Program`, `DB2Table/VSAMDataset ← READS/WRITES ← Program`, `Table ← FIRES_ON ← Trigger ← TRIGGERS_TRIGGER`, `Table ← CASCADES_TO ← Table`, `View ← ABSTRACTS ← Table`.
- Returns a ranked blast-radius set with edge reasons.
- Pure graph traversal — zero tokens, available as soon as Layer 2 is populated.

### Why the deferred items matter

Triggers, stored procedures, cascade depth, VSAM, REPLACING, and redaction are not nice-to-haves — they are exactly where the scariest undocumented behavior tends to live in a real payments-processing estate. IMS and CICS control flow are deferred only because MVP value is delivered before they're needed; the schema reserves space for them now.

---

## 6. Graph storage & visualization — concrete choices

| Stage | Storage | Why |
|---|---|---|
| MVP / single repo | SQLite (nodes/edges tables) or embedded graph engine like **Kùzu** | Zero infra, ships as a Python dependency, good for tens of thousands of nodes |
| Team-scale | Kùzu or lightweight server graph DB | Only when query patterns actually need real graph traversal performance |
| Enterprise-scale | Neo4j / managed graph DB | Only when indexing multiple large estates concurrently |

Visualization: start with **Mermaid** or a simple **D3/Cytoscape.js force-directed graph** rendered as a static/lightly-interactive artifact for any subgraph. Don't build a custom graph-rendering engine — your differentiation is the knowledge, not the rendering.

Retrieval over narrations: a small embedded vector store (FAISS/Chroma) beside the graph lets the chat layer do semantic search over `BusinessRule` descriptions before falling back to an LLM — another token-saving layer.

---

## 7. Extensibility model

Narrow, versioned interfaces so contributions don't require touching the core:

```
mainframe-brain/
├── extractors/          # one folder per artifact type — community contributes here
│   ├── cobol/
│   ├── copybook/
│   ├── vsam/            # VSAM + sequential files
│   ├── jcl/
│   ├── cics_bms/
│   ├── db2_ddl/
│   ├── sql_pl/
│   ├── triggers/
│   ├── report/
│   ├── external_boundary/
│   ├── ims_db/          # deferred
│   ├── ims_dc/          # deferred
│   └── cics_control_flow/  # deferred
├── redaction/           # Layer 3.5 — hard gate
├── graph/               # storage interface + schema (swappable backend)
├── triage/              # diff, dedup, risk scoring (incl. cascade/trigger depth)
├── enrichment/          # LLM-calling — model-agnostic, caching + provenance
│   ├── prompts/         # versioned prompt templates per node type
│   └── models/          # thin adapters per provider
├── skills/              # SKILL.md packaging
├── explorer/            # graph visualization + change-impact query
├── examples/
├── docs/SCHEMA.md       # versioned graph schema — public contract
└── tests/golden/        # known-input → known-output fixtures per extractor
```

Guidelines:

- **The graph schema is versioned and documented like an API.** Breaking changes need a migration path.
- **New language/dialect support = new extractor folder.** Add PL/I or Assembler without touching graph/triage/enrichment.
- **New model backend = new adapter in `enrichment/models/`.** The rest never knows or cares which provider runs.
- **Golden fixture tests per extractor** — including a partial-parse corpus — so contributions don't silently regress.

---

## 8. The "business knowledge" layer, specifically

A `BusinessRule` node is "what business decision does this code encode" — an interest-calc method for a regulatory requirement, a fee-deviation threshold that triggers an exception report, a condition code that determines whether a SEPA payment gets rejected.

Design requirements specific to this layer:

- **Confidence, not certainty.** Every inferred rule carries a confidence score and is visually distinguishable from human-verified knowledge until someone signs off.
- **A lightweight review workflow.** A simple "approve / flag as wrong / edit" loop (CLI or GitHub-issue-backed queue for v1) turns unverified LLM output into trusted institutional memory over time; every correction updates the cached narration so the mistake isn't repeated.
- **Traceability is non-negotiable in a banking context.** Every rule is traceable to an exact source location and hash. If the underlying code changes, the rule is flagged stale, not silently left looking current.
- **This layer is explicitly NOT a compliance or audit tool** — documentation and knowledge-preservation only.

---

## 9. MVP scope

**Phase 1 (weeks 1–3):** `cobol_extractor` + `copybook_extractor` (with post-expansion hashing) + `vsam_extractor` → SQLite graph store → CLI printing a call graph, field-lineage query, and VSAM read/write lineage over a public sample.

**Phase 2 (weeks 3–5):** `db2_ddl_extractor`, `sql_pl_extractor`, `trigger_extractor`, change/risk triage (content hashing + complexity + trigger-chain + cascade-depth), redaction Layer 3.5, selective LLM enrichment with provenance fields from day one, `query-impact` capability.

**Phase 3 (weeks 5–7):** Persistent brain versioning, Mermaid/D3 explorer showing trigger chains + call graphs in one view, basic chat-query CLI backed by graph lookups.

**Phase 4 (weeks 7+):** Claude Skills packaging, `jcl_extractor`, `cics_bms_extractor`, `report_extractor`, `external_boundary_extractor`. Open the repo publicly.

**Deferred (documented, schema-ready, post-MVP):** IMS DB/DC (5.9), CICS control flow XCTL/LINK/COMMAREA/TSQ/TDQ (5.10).

Phase 1 gives a complete demoable story — parse → understand → remember — rather than a half-finished system with nothing to show.

---

## 10. Distribution strategy

- **YoPro Germany as a built-in pilot audience.** "I built the tool I was talking about" is a stronger story than a cold launch; Bad Homburg/Nuremberg gives real mainframe engineers to pressure-test before going public.
- **An existing LinkedIn audience primed for exactly this narrative.** A "here's the open-source tool" follow-up with a short screen-recording of the business-rule extractor narrating an undocumented paragraph is a natural next post.
- **Positioning against vendor lock-in.** Open-source and model-agnostic vs. IBM Watsonx Code Assistant for Z; portable Markdown/graph artifacts a team owns vs. a vendor dashboard.

---

## 11. Open questions worth deciding before writing code

- **License**: Apache 2.0 over MIT — explicit patent grant matters for regulated-industry enterprise adoption.
- **Where does the review workflow live for v1?** Flat file / GitHub issues is enough to start.
- **How much of the risk-scoring heuristic is configurable vs. opinionated defaults?** Expose as config, ship sane defaults.
- **Multi-tenancy in the graph schema** — `codebase_id` namespace from day one.
- **DB2 catalog access**: DDL exports only for v1. Live catalog querying deferred to opt-in.
- **Redaction pattern provenance** — keep the report's finding list but never the raw secret text. Audit what was scrubbed without re-logging it.

---

## 12. Deferred scope (documented, not MVP-blocking)

These are recorded here so the schema reserves space and future contributions don't need a migration:

| Item | Schema reservation | Why deferred |
|---|---|---|
| IMS DB/DC extractors (5.9) | `ims_db`/`ims_dc` extractor folders | Discrete community; DB2/CICS cover most early adopters first |
| CICS control flow — XCTL/LINK/RETURN, COMMAREA, TSQ/TDQ (5.10) | `XCTLS` edge type already reserved | BMS screens are the visible surface; control flow matters more after Phase 3 |
| External boundary extractor (5.7) | `ExternalSystem` node + `CALLS_EXTERNAL` already in schema v1.1 | Ships as soon as a real MQ/HTTP sample is available for a golden fixture |
| Report extractor (5.8) | `Report` node + `PRODUCES_REPORT` already in schema v1.1 | Auto-naming from JCL SYSOUT first; purpose narration later |
| Change-impact `query-impact` (5.12) | Pure-graph traversal, no schema change | Lands with Phase 2 once the graph is populated end-to-end |
| Live DB2 catalog queries | N/A (data source, not schema) | Opt-in later; never a v1 requirement |

---

## Appendix: worked example (with redaction + post-expansion hashing)

1. `cobol_extractor` parses `CALC-INTEREST-RATE` in `INTCALC01.cbl`. The program `COPY`s `ACCTFIELDS` with `REPLACING ==ACCT-ID== BY ==CUST-ID==`; the expanded paragraph text is hashed (`a3f9...`), not the raw copybook.
2. Layer 2 writes a `Paragraph` node with that post-expansion hash; no LLM involved.
3. Layer 3 checks the brain: hash `a3f9...` unseen; complexity 6 places it in top risk quartile → queued.
4. Layer 3.5 redacts the queued source — one SSN-shaped literal in a comment becomes `[REDACTED]:SSN`. The hash for cache lookup is computed on this redacted form. Redaction report logged (kind, span only — not the raw value).
5. Layer 4 sends only the redacted, post-expansion paragraph to the LLM. Result stored as a `BusinessRule` with `confidence: 0.82`, `human_verified: false`, provenance recording model+prompt version.
6. A reviewer corrects one edge case, sets `human_verified: true`.
7. Six months later, one line in `CALC-INTEREST-RATE` changes. Next run: hash differs only for this unit. Every other paragraph — untouched — hashes match, zero tokens spent. Only this one re-queues; the verified rule is flagged stale until re-approved. Critically, adding a new redaction rule two months ago did not force re-narration: the meaning never changed.

That last step is the entire point: understanding compounds, and the cost of maintaining it approaches zero over time.