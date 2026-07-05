"""DB2 DDL extractor — CREATE TABLE/INDEX/VIEW and PK/FK constraints.

Phase-1-grade regex parsing: honest about limits. Any block that doesn't
cleanly parse keeps its source and gets `parse_confidence < 1.0` rather
than being silently dropped (gap #5.11).
"""
from __future__ import annotations

import re
from pathlib import Path

from mainframe_brain.extractors.base import (
    ExtractionResult,
    LogicalUnit,
    content_hash,
)
from mainframe_brain.graph.schema import Edge, EdgeType, Node, NodeType
from mainframe_brain.graph.store import make_node_id

_KW = re.IGNORECASE

_CREATE_TABLE_RE = re.compile(
    r"CREATE\s+TABLE\s+(?P<name>[A-Za-z_][\w$#]*)\s*\((?P<body>.*?)\)\s*;",
    _KW | re.DOTALL,
)
_CREATE_INDEX_RE = re.compile(
    r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?P<name>[A-Za-z_][\w$#]*)\s+ON\s+"
    r"(?P<table>[A-Za-z_][\w$#]*)\s*\((?P<cols>[^)]*)\)\s*;",
    _KW | re.DOTALL,
)
_CREATE_VIEW_RE = re.compile(
    r"CREATE\s+VIEW\s+(?P<name>[A-Za-z_][\w$#]*)\s+AS\s+"
    r"(?P<body>SELECT\s+.*?)\s*;",
    _KW | re.DOTALL,
)
_CREATE_TRIGGER_RE = re.compile(
    r"CREATE\s+TRIGGER\s+(?P<name>[A-Za-z_][\w$#]*)\b",
    _KW,
)

_DDL_MARKER_RE = re.compile(
    r"CREATE\s+(TABLE|VIEW|INDEX|TRIGGER|PROCEDURE|FUNCTION)\b",
    _KW,
)

_FK_RE = re.compile(
    r"FOREIGN\s+KEY\s*\((?P<cols>[^)]*)\)\s+REFERENCES\s+"
    r"(?P<ref>[A-Za-z_][\w$#]*)\s*(?:\((?P<refcols>[^)]*)\))?"
    r"(?P<rest>[^,]*)",
    _KW,
)
_PK_RE = re.compile(r"PRIMARY\s+KEY\s*\((?P<cols>[^)]*)\)", _KW)
_CHECK_RE = re.compile(r"CHECK\s*\(", _KW)
_ON_DEL_RE = re.compile(r"ON\s+DELETE\s+(CASCADE|RESTRICT|SET\s+NULL)", _KW)
_ON_UPD_RE = re.compile(r"ON\s+UPDATE\s+(CASCADE|RESTRICT|SET\s+NULL)", _KW)

_COL_TYPE_RE = re.compile(
    r"^(?P<name>[A-Za-z_][\w$#]*)\s+(?P<type>[A-Za-z][\w]*(?:\s*\([^)]*\))?)",
    _KW,
)


def _split_top_level(s: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    buf: list[str] = []
    for ch in s:
        if ch == "(":
            depth += 1
            buf.append(ch)
        elif ch == ")":
            depth -= 1
            buf.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    tail = "".join(buf).strip()
    if tail:
        parts.append(tail)
    return parts


def _view_tables(body: str) -> list[str]:
    tables: list[str] = []
    _FROM_JOIN_RE = re.compile(
        r"(?:FROM|JOIN)\s+([A-Za-z_][\w$#]*)", _KW
    )
    stop = re.search(r"\bWHERE\b", body, _KW)
    scan = body[: stop.start()] if stop else body
    for m in _FROM_JOIN_RE.finditer(scan):
        t = m.group(1)
        if t not in tables:
            tables.append(t)
    return tables


class DB2DDLExtractor:
    artifact_type = "db2_ddl"

    def can_handle(self, file_path: Path) -> bool:
        if file_path.suffix.lower() not in (".ddl", ".sql"):
            return False
        try:
            text = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return False
        return bool(_DDL_MARKER_RE.search(text))

    def extract(
        self, file_path: Path, codebase_id: str = "default"
    ) -> ExtractionResult:
        text = file_path.read_text(encoding="utf-8", errors="replace")
        result = ExtractionResult(
            artifact_type=self.artifact_type,
            source_file=str(file_path),
        )

        for m in _CREATE_TABLE_RE.finditer(text):
            self._emit_table(m.group("name"), m.group("body"), text, codebase_id, result)

        for m in _CREATE_INDEX_RE.finditer(text):
            self._emit_index(
                m.group("name"), m.group("table"), m.group("cols"), codebase_id, result
            )

        for m in _CREATE_VIEW_RE.finditer(text):
            self._emit_view(m.group("name"), m.group("body"), codebase_id, result)

        for m in _CREATE_TRIGGER_RE.finditer(text):
            self._emit_trigger_marker(m.group("name"), codebase_id, result)

        return result

    def _emit_table(
        self, name: str, body: str, full_text: str, codebase_id: str, result: ExtractionResult
    ) -> None:
        table_id = make_node_id("DB2Table", codebase_id, name)
        parse_conf = 1.0
        parts = _split_top_level(body)
        if not parts:
            parse_conf = 0.4
        col_names: list[str] = []
        for p in parts:
            const_m = re.match(
                r"CONSTRAINT\s+([A-Za-z_][\w$#]*)\s+(.*)", p, _KW | re.DOTALL,
            )
            const_name = None
            clause = p
            if const_m:
                const_name = const_m.group(1)
                clause = const_m.group(2)
            clause_up = clause.upper().lstrip()
            if clause_up.startswith("PRIMARY KEY"):
                pk_search = _PK_RE.search(clause)
                pk_cols = (
                    [c.strip() for c in pk_search.group("cols").split(",")]
                    if pk_search else []
                )
                self._emit_constraint(
                    const_name or f"{name}_PK", "PK", name, codebase_id, result,
                    cols=pk_cols, parse_conf=1.0,
                )
                continue
            if clause_up.startswith("FOREIGN KEY"):
                self._emit_fk(clause, name, codebase_id, result, const_name)
                continue
            if clause_up.startswith("CHECK"):
                self._emit_constraint(
                    const_name or f"{name}_CHK", "CHECK", name, codebase_id, result,
                    expr=clause, parse_conf=0.9,
                )
                continue
            if clause_up.startswith("UNIQUE"):
                u_cols = re.findall(r"\(([^)]*)\)", clause)
                self._emit_constraint(
                    const_name or f"{name}_UNQ", "UNIQUE", name, codebase_id, result,
                    cols=[c.strip() for c in (u_cols[0].split(",") if u_cols else [])],
                    parse_conf=0.9,
                )
                continue
            cm = _COL_TYPE_RE.match(p.strip())
            if not cm:
                parse_conf = min(parse_conf, 0.6)
                continue
            cname = cm.group("name")
            ctype = cm.group("type").strip()
            not_null = re.search(r"\bNOT\s+NULL\b", p, _KW) is not None
            is_pk_col = re.search(r"\bPRIMARY\s+KEY\b", p, _KW) is not None
            col_node = Node(
                id=make_node_id("DB2Column", codebase_id, f"{name}.{cname}"),
                type=NodeType.DB2_COLUMN,
                name=cname,
                codebase_id=codebase_id,
                content_hash=content_hash(f"{name}.{cname}:{ctype}:{not_null}:{is_pk_col}"),
                parse_confidence=1.0,
                properties={"parent_table": name, "type": ctype,
                           "not_null": not_null, "is_pk": is_pk_col},
            )
            result.nodes.append(col_node)
            col_names.append(cname)
            if is_pk_col:
                self._emit_constraint(
                    f"{name}_PK", "PK", name, codebase_id, result,
                    cols=[cname], parse_conf=1.0,
                )

        table_node = Node(
            id=table_id,
            type=NodeType.DB2_TABLE,
            name=name,
            codebase_id=codebase_id,
            content_hash=content_hash(f"CREATE TABLE {name} ({body})"),
            parse_confidence=parse_conf,
            properties={"columns": col_names},
        )
        result.nodes.append(table_node)
        result.units.append(LogicalUnit(
            kind="table", name=name,
            source=f"CREATE TABLE {name} ({body});",
            content_hash=content_hash(f"CREATE TABLE {name} ({body});"),
            properties={"columns": col_names},
        ))

    def _emit_fk(self, frag: str, table: str, codebase_id: str, result: ExtractionResult,
                 const_name: str | None = None) -> None:
        m = _FK_RE.search(frag)
        if not m:
            self._emit_constraint(
                const_name or f"{table}_FK", "FK", table, codebase_id, result,
                expr=frag, parse_conf=0.4,
            )
            return
        cols = [c.strip() for c in m.group("cols").split(",")]
        ref = m.group("ref")
        refcols = m.group("refcols") or ""
        rest = m.group("rest") or ""
        on_del = _ON_DEL_RE.search(rest)
        on_upd = _ON_UPD_RE.search(rest)
        cascade_rule = ""
        if on_del:
            cascade_rule += "ON DELETE " + on_del.group(1).upper().replace("  ", " ") + " "
        if on_upd:
            cascade_rule += "ON UPDATE " + on_upd.group(1).upper().replace("  ", " ")
        cascade_rule = cascade_rule.strip()
        self._emit_constraint(
            const_name or f"{table}_FK_{ref}", "FK", table, codebase_id, result,
            cols=cols, references=ref,
            ref_cols=[c.strip() for c in refcols.split(",") if c.strip()],
            cascade_rule=cascade_rule, parse_conf=0.95,
        )
        if on_del and on_del.group(1).upper() == "CASCADE":
            result.edges.append(Edge(
                src=make_node_id("DB2Table", codebase_id, table),
                dst=make_node_id("DB2Table", codebase_id, ref),
                type=EdgeType.CASCADES_TO,
                properties={"rule": "ON DELETE CASCADE"},
            ))
        if on_upd and on_upd.group(1).upper() == "CASCADE":
            result.edges.append(Edge(
                src=make_node_id("DB2Table", codebase_id, table),
                dst=make_node_id("DB2Table", codebase_id, ref),
                type=EdgeType.CASCADES_TO,
                properties={"rule": "ON UPDATE CASCADE"},
            ))

    def _emit_constraint(
        self, name: str, kind: str, table: str, codebase_id: str,
        result: ExtractionResult, cols: list[str] | None = None,
        references: str | None = None, ref_cols: list[str] | None = None,
        cascade_rule: str = "", expr: str = "", parse_conf: float = 1.0,
    ) -> None:
        props: dict = {"kind": kind, "table": table}
        if cols is not None:
            props["cols"] = cols
        if references:
            props["references"] = references
        if ref_cols:
            props["ref_cols"] = ref_cols
        if cascade_rule:
            props["cascade_rule"] = cascade_rule
        if expr:
            props["expr"] = expr
        result.nodes.append(Node(
            id=make_node_id("Constraint", codebase_id, name),
            type=NodeType.CONSTRAINT,
            name=name,
            codebase_id=codebase_id,
            content_hash=content_hash(f"{name}:{kind}:{table}:{props}"),
            parse_confidence=parse_conf,
            properties=props,
        ))
        result.units.append(LogicalUnit(
            kind="constraint", name=name,
            source=expr or f"CONSTRAINT {name} {kind} on {table}",
            content_hash=content_hash(f"{name}:{kind}:{table}:{props}"),
            properties=props,
        ))

    def _emit_index(
        self, name: str, table: str, cols: str, codebase_id: str, result: ExtractionResult
    ) -> None:
        col_list = [c.strip() for c in cols.split(",")]
        result.nodes.append(Node(
            id=make_node_id("Constraint", codebase_id, name),
            type=NodeType.CONSTRAINT,
            name=name,
            codebase_id=codebase_id,
            content_hash=content_hash(f"INDEX {name} {table} {col_list}"),
            parse_confidence=0.9,
            properties={"kind": "INDEX", "table": table, "cols": col_list},
        ))
        result.units.append(LogicalUnit(
            kind="index", name=name,
            source=f"CREATE INDEX {name} ON {table} ({cols});",
            content_hash=content_hash(f"CREATE INDEX {name} ON {table} ({cols});"),
            properties={"table": table, "cols": col_list},
        ))

    def _emit_view(
        self, name: str, body: str, codebase_id: str, result: ExtractionResult
    ) -> None:
        tables = _view_tables(body)
        parse_conf = 1.0 if tables else 0.6
        result.nodes.append(Node(
            id=make_node_id("View", codebase_id, name),
            type=NodeType.VIEW,
            name=name,
            codebase_id=codebase_id,
            content_hash=content_hash(f"CREATE VIEW {name} AS SELECT ... FROM {body}"),
            parse_confidence=parse_conf,
            properties={"underlying_tables": tables, "defining_sql": body.strip()},
        ))
        vid = make_node_id("View", codebase_id, name)
        for t in tables:
            result.edges.append(Edge(
                src=vid,
                dst=make_node_id("DB2Table", codebase_id, t),
                type=EdgeType.ABSTRACTS,
                properties={},
            ))
        result.units.append(LogicalUnit(
            kind="view", name=name,
            source=f"CREATE VIEW {name} AS SELECT ... FROM {body};",
            content_hash=content_hash(f"CREATE VIEW {name} AS SELECT ... FROM {body};"),
            properties={"underlying_tables": tables},
        ))

    def _emit_trigger_marker(
        self, name: str, codebase_id: str, result: ExtractionResult
    ) -> None:
        result.nodes.append(Node(
            id=make_node_id("Trigger", codebase_id, name),
            type=NodeType.TRIGGER,
            name=name,
            codebase_id=codebase_id,
            content_hash="",
            parse_confidence=0.3,
            properties={"note": "DDL marker only; full extraction by trigger_extractor"},
        ))


__all__ = ["DB2DDLExtractor"]