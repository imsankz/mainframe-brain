# AGENTS.md — Mainframe Brain

Commands opencode/anomaly agents should run on this repo before considering work finished.

## Install (dev)

```bash
pip3 install -e ".[dev]" --break-system-packages
```

Python ≥ 3.10. macOS system Python 3.14 used in CI/local; the `--break-system-packages` flag is needed there because of PEP 668.

## Lint

```bash
python3 -m ruff check mainframe_brain tests --config pyproject.toml
```

Must pass with zero errors before any commit. Ruff auto-fixes most issues:
```bash
python3 -m ruff check --fix mainframe_brain tests --config pyproject.toml
```

## Test

```bash
python3 -m pytest tests/ -q
```

Currently 28 tests (unit + golden). Must stay green. Run a single file:
```bash
python3 -m pytest tests/unit/test_*.py -q
python3 -m pytest tests/golden/test_*_golden.py -q
```

## Smoke (end-to-end CLI run)

```bash
rm -f /tmp/mb.db
python3 -m mainframe_brain.cli extract examples/cobol    --out /tmp/mb.db
python3 -m mainframe_brain.cli extract examples/db2      --out /tmp/mb.db
python3 -m mainframe_brain.cli extract examples/jcl      --out /tmp/mb.db
python3 -m mainframe_brain.cli extract examples/cics_bms --out /tmp/mb.db
python3 -m mainframe_brain.cli triage                    --store-path /tmp/mb.db
python3 -m mainframe_brain.cli list-nodes --store-path /tmp/mb.db
python3 -m mainframe_brain.cli list-nodes --store-path /tmp/mb.db --low-confidence
python3 -m mainframe_brain.cli query    --store-path /tmp/mb.db "what touches ACCOUNTS"
python3 -m mainframe_brain.cli query    --store-path /tmp/mb.db "impact of ACCOUNTS"
python3 -m mainframe_brain.cli query    --store-path /tmp/mb.db "show triggers on TXNLOG"
python3 -m mainframe_brain.cli enrich   --store-path /tmp/mb.db --budget 20000 --adapter mock
python3 -m mainframe_brain.cli triage                    --store-path /tmp/mb.db
python3 -m mainframe_brain.cli verify   --store-path /tmp/mb.db "BusinessRule:default:2000-CALC-INTEREST:987b31a8"
python3 -m mainframe_brain.cli flag    --store-path /tmp/mb.db --rule "BusinessRule:default:9000-ERROR:7b1c624e" --reason "needs SME review"
python3 -m mainframe_brain.cli edit-rule --store-path /tmp/mb.db --rule "BusinessRule:default:0000-MAIN:e8b6f26b" --rule-text "Main driver schedule paragraph"

## Type-check (optional, not enforced yet)

```bash
python3 -m mypy mainframe_brain --ignore-missing-imports
```

## Repo layout

- `mainframe_brain/extractors/<family>/extractor.py` — one file per artifact type. New language = new folder. Don't touch graph/triage/enrichment when adding one.
- `mainframe_brain/graph/{schema,store,sqlite_store}.py` — versioned public contract. Read `docs/SCHEMA.md` before changing.
- `mainframe_brain/triage/` — Layer 3 (diff, dedup, risk scoring, work queue).
- `mainframe_brain/redaction/` — Layer 3.5 (hard gate). Nothing reaches an LLM without passing through here.
- `mainframe_brain/enrichment/` — Layer 4. Model-agnostic. New provider = new adapter in `models/`.
- `mainframe_brain/cli.py` — Layer 6 entry. Thin orchestrator only.
- `tests/unit/` — extractor/store/triage/enrichment tests. `tests/golden/` — fixture-level parse tests.

## Conventions

- No comments in code unless a non-obvious WHY.
- Type hints everywhere.
- `parse_confidence < 1.0` on partial parse — never silently drop a node.
- Content hashes are POST-expansion (COPY REPLACING) and POST-redaction.
- Multi-extractor per file is allowed (cobol + vsam both read .cbl). Avoid emitting the same node from two extractors — coordinate via owned node types.
- Use only stdlib + declared deps (click, pydantic, jinja2). anthropic/openai lazily imported inside their adapter files only.
- Schema changes bump `SCHEMA_VERSION` in `mainframe_brain/graph/schema.py` and add a row to `docs/MIGRATIONS.md`.

## Things explicitly NOT in scope for v1

- Live DB2 catalog access (DDL exports only).
- Compliance/audit tool framing (documentation aid only).
- A custom graph-rendering engine (use Mermaid/Cytoscape).