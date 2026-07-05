# Mainframe Brain — Graph Schema

**Version:** `1.1.0` — public contract. Breaking changes require a migration path.
See `mainframe_brain/graph/schema.py` for the canonical definition.

## Node types

| Type | Description | Key properties |
|---|---|---|
| `Program` | COBOL program (or COBOL-based stored proc) | program_id, division headers, LOC, `invoked_as_stored_procedure?` |
| `Paragraph` | COBOL paragraph | parent_program, cyclomatic_complexity, goto_density, statement_count, anomalies, `source`, `replacing_applied`, `parse_confidence` |
| `Copybook` | Reusable field layout | included_by list, field_count, `replacing_applied` |
| `Field` | Working-storage / copybook field | level, PIC, REDEFINES target, OCCURS, 88-levels |
| `JCLJob` | JCL job stream | steps, schedule info |
| `JCLStep` | JCL step | program/utility, condition codes, datasets |
| `Dataset` | Generic flat/sequential file (`DSORG=PS`) | external_dataset_name, referencing jobs/programs |
| `VSAMDataset` | VSAM file — KSDS/ESDS/RRDS | organization, access_mode, record_key, alternate_keys |
| `CICSMap` | BMS screen map | fields, screen layout |
| `DB2Table` | DB2 table | columns, referencing programs |
| `DB2Column` | DB2 column | type, parent_table, NOT NULL |
| `StoredProcedure` | SQL PL or COBOL stored procedure | language, parameters, complexity, source |
| `Trigger` | DB2 trigger | timing, event, table, referencing aliases, complexity |
| `View` | DB2 view | defining SQL, underlying tables |
| `Constraint` | PK/FK/check | kind, table, references, cascade_rule |
| `Report` | SYSOUT / business output (deferred) | name, triggering job, business purpose |
| `ExternalSystem` | MQ/HTTP/vendor boundary (deferred-class, schema-ready) | kind, boundary descriptor |
| `BusinessRule` | **LLM-derived** — see ARCHITECTURE §8 | rule, confidence, line_range, edge_cases, model, prompt_version, `human_verified`, redacted_count, content_hash |

Every node carries: `id`, `codebase_id`, `content_hash`, `last_verified`, `parse_confidence`.

### Node id convention

`{type}:{codebase_id}:{name}` — e.g. `Program:bank_a:INTCALC01`. Globally unique within a brain.

### `parse_confidence`

`0.0..1.0`. `<1.0` = partial/low-confidence parse. Extractors NEVER silently drop
a partially-parsed node — they emit it with confidence < 1.0 and a list of anomalies.
Triage downweights low-confidence nodes to avoid spending tokens on garbage.

## Edge types

| Edge | From → To | Meaning |
|---|---|---|
| `CALLS` | Program → Program | `CALL "name"` |
| `PERFORMS` | Paragraph → Paragraph | `PERFORM` / `PERFORM THRU` |
| `INCLUDES` | Program → Copybook | `COPY` (REPLACING clause in edge properties) |
| `READS` | {Program, StoredProcedure, Paragraph} → {DB2Table, VSAMDataset, Dataset} | READ verb / SQL SELECT |
| `WRITES` | {Program, StoredProcedure} → {DB2Table, VSAMDataset, Dataset} | WRITE/REWRITE / SQL INSERT/UPDATE/DELETE |
| `DERIVED_FROM` | BusinessRule → source node | provenance back-pointer |
| `IMPLEMENTS_RULE` | source node → BusinessRule | which source unit the rule narrates |
| `RENDERS_ON` | Program → CICSMap | `EXEC CICS SEND/RECEIVE MAP` |
| `INVOKES_PROC` | caller → StoredProcedure | `CALL procname()` in SQL PL body |
| `FIRES_ON` | Trigger → Table | trigger's target table |
| `TRIGGERS_TRIGGER` | Trigger → Trigger | cascade chain (often the dangerous invisible edge) |
| `ABSTRACTS` | View → Table | view's underlying base table |
| `CASCADES_TO` | Table → Table | FK with `ON DELETE/UPDATE CASCADE` |
| `PRODUCES_REPORT` | {JCLJob, JCLStep} → Report | job's business output (deferred) |
| `CALLS_EXTERNAL` | Program → ExternalSystem | MQ/HTTP/vendor outbound (deferred-class) |
| `XCTLS` | Program → Program | CICS pseudo-conversational handoff (deferred) |

## Schema versioning

Stored in `schema_meta(key='schema_version', value)` in the SQLite store at init.
Bump on any breaking change to node/edge types or required property shape. Provide a
migration path documented in `docs/MIGRATIONS.md` (create when first needed).

## Cache table (enrichment)

`narration_cache(content_hash PRIMARY KEY, payload TEXT, created_at TEXT, human_verified INTEGER, stale INTEGER)`

The cache key is the **post-redaction** content hash, so adding new redaction rules
does not force re-narration — the meaning never changed, only the scrubbed surface.