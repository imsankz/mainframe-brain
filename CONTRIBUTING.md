# Contributing to Mainframe Brain

Thanks for taking the time. Mainframe Brain is a small schema + many narrow extractors around it — most contributions land in exactly one extractor folder and never touch the core.

## Setup

```bash
git clone https://github.com/sankalpsingh/mainframe-brain.git
cd mainframe-brain
pip3 install -e ".[dev]" --break-system-packages   # macOS PEP 668
pytest tests/ -q
ruff check mainframe_brain tests --config pyproject.toml
```

CI runs `ruff` + `pytest` + a CLI smoke on Python 3.10–3.14. Local green = CI green.

## Adding a new artifact type (the common case)

1. **Create a folder:** `mainframe_brain/extractors/<your_family>/`. Add `__init__.py` and `extractor.py`.
2. **Implement the `Extractor` protocol** (see `mainframe_brain/extractors/base.py`):
   - `artifact_type: str`
   - `can_handle(self, file_path: Path) -> bool`
   - `extract(self, file_path: Path, codebase_id: str = "default") -> ExtractionResult`
3. **Pick the node/edge types your extractor owns.** The CLI runs every matching extractor per file, so two extractors can read the same `.cbl` — but they must not emit the same node type. Coordinate via ownership:
   - `cobol` → Program, Paragraph, Field (working-storage)
   - `copybook` → Copybook, Field (copybook layout)
   - `vsam` → VSAMDataset, Dataset
   - `db2_ddl` → DB2Table, DB2Column, View, Constraint
   - `sql_pl` → StoredProcedure
   - `triggers` → Trigger
   - `jcl` → JCLJob, JCLStep
   - `cics_bms` → CICSMap
4. **Set `parse_confidence < 1.0` on partial parses — never silently drop a node.** A malformed PIC, unterminated `EXEC SQL`, or old continuation style should still emit the node plus a `properties["anomalies"]` list.
5. **Compute content hashes POST-expansion** (for COPY REPLACING) and POST-redaction when applicable. The cache key is whatever text the LLM would actually see.
6. **Add a golden fixture:** `tests/golden/test_<family>_golden.py` exercising a known input → known-output. Use a synthetic example in `examples/<family>/` — never client code.
7. **Run lint + tests:**
   ```bash
   ruff check --fix mainframe_brain tests --config pyproject.toml
   pytest tests/ -q
   ```

## Adding a new LLM provider

1. Add `mainframe_brain/enrichment/models/<provider>_adapter.py` implementing `LLMAdapter` from `models/base.py`.
2. Lazy-import the provider SDK inside the adapter file only — keep `mainframe-brain[llm]` extras optional.
3. Add a `click.Choice` option in `cli.py`'s `enrich` command.
4. No changes to the Enricher, cache, or graph.

## Schema changes

The graph schema in `mainframe_brain/graph/schema.py` is a **public contract** — community extractors and enrichers depend on it.

- Breaking changes (renaming/removing a node type or edge type, changing a required property) require:
  1. Bumping `SCHEMA_VERSION` in `schema.py`.
  2. A migration row in `docs/MIGRATIONS.md`.
  3. A migration path in `SQLiteGraphStore` (or a clear `--migrate` CLI command).
- Additive changes (new node type, new edge type, new optional property) only need a `SCHEMA_VERSION` minor bump and a `MIGRATIONS.md` row — no migration code.

## Code style

- Type hints everywhere.
- No comments unless a non-obvious WHY.
- Stdlib + declared deps only. `anthropic`/`openai` are lazily imported inside their adapter files only.
- Match the existing ruff config (line-length 110, `select = ["E","F","I","UP","B","SIM"]`).

## Things explicitly out of scope for v1

- Live DB2 catalog access (DDL exports only — keeps the contribution barrier low).
- Compliance/audit tool framing (documentation aid only).
- A custom graph-rendering engine (use Mermaid/Cytoscape).

## License

By contributing you agree your contributions will be licensed under the Apache 2.0 license.