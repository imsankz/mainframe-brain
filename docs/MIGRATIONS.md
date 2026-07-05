# Graph Schema Migrations

The graph schema (`mainframe_brain/graph/schema.py`) is a public contract. This file tracks every change. Additive changes (new node/edge type, new optional property) get a minor row. Breaking changes (rename/remove, required-property change) get a major row and a migration entry under the "Migration code" column.

| Version | Date       | Change                                                                                                | Migration code |
|---------|------------|-------------------------------------------------------------------------------------------------------|----------------|
| 1.0.0   | 2026-07-05 | Initial schema (14 node types, 13 edge types).                                                         | n/a            |
| 1.1.0   | 2026-07-05 | Add VSAMDataset, Report, ExternalSystem node types; FIRES_ON, TRIGGERS_TRIGGER, ABSTRACTS, CASCADES_TO, PRODUCES_REPORT, CALLS_EXTERNAL, XCTLS edge types; `parse_confidence` field on Node; `codebase_id` namespace. | Additive only — SQLiteGraphStore lazily `CREATE TABLE IF NOT EXISTS` so existing stores auto-upgrade on first open. |
| 1.2.0   | 2026-07-05 | Add `EXECUTES` edge type (JCLStep → Program) and `placeholder: True` Program nodes for unresolved `CALL`/`EXEC PGM` targets, so cross-file call chains are no longer orphan edges. JCLStep gains `parent_job` property linking back to its JCLJob. | Additive only — pure additions, no rename/remove/required-property change. Existing stores auto-upgrade on first open. |
|         |            |                                                                                                       |                |

## How to add a row

1. Bump `SCHEMA_VERSION` in `mainframe_brain/graph/schema.py` (`MAJOR.MINOR.PATCH`).
2. Append a row above using the same format.
3. If the change is **breaking**, also implement the migration in `SQLiteGraphStore` (run on `__init__` based on the stored `schema_meta.schema_version`). Add a row to the "Migration code" column describing where it lives.
4. Add a golden test that opens a store created under the prior schema and asserts the new fields/types are present after migration.

## What counts as breaking

- Renaming or removing a `NodeType` or `EdgeType`.
- Making an optional Node property required.
- Changing the format of `properties` JSON for an existing node type.
- Changing the id convention (`{type}:{codebase_id}:{name}`) — avoided; this is load-bearing.

Additive changes (new NodeType/EdgeType, new optional property, new index) are **not** breaking — they get a minor bump and a `MIGRATIONS.md` row only.