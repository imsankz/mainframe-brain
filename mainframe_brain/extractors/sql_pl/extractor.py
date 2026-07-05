"""SQL PL stored procedure extractor — CREATE PROCEDURE/FUNCTION bodies.

Builds a control-flow skeleton (IF/WHILE/FOR/CASE), counts cyclomatic
complexity, links CALL targets via INVOKES_PROC, and READS/WRITES edges
to tables referenced by DML in the body. Body text is matched with
regex (Phase-1-grade); any partially-matched proc keeps the unit and a
parse_confidence < 1.0 (gap #5.11).
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

_CREATE_HEAD_RE = re.compile(
    r"CREATE\s+(?P<kind>PROCEDURE|FUNCTION)\s+(?P<name>[A-Za-z_][\w$#]*)\s*\(",
    _KW,
)
_LANG_RE = re.compile(r"LANGUAGE\s+(SQL|COBOL|JAVA|C)", _KW)
_DYN_RE = re.compile(r"DYNAMIC\s+RESULT\s+SETS\s+(\d+)", _KW)
_IF_RE = re.compile(r"\bIF\b", _KW)
_WHILE_RE = re.compile(r"\bWHILE\b", _KW)
_FOR_RE = re.compile(r"\bFOR\b", _KW)
_CASE_RE = re.compile(r"\bCASE\b", _KW)
_CALL_RE = re.compile(r"\bCALL\s+([A-Za-z_][\w$#]*)\s*\(", _KW)

_INSERT_RE = re.compile(r"\bINSERT\s+INTO\s+([A-Za-z_][\w$#]*)", _KW)
_UPDATE_RE = re.compile(r"\bUPDATE\s+([A-Za-z_][\w$#]*)\s+SET\b", _KW)
_DELETE_RE = re.compile(r"\bDELETE\s+FROM\s+([A-Za-z_][\w$#]*)", _KW)
_SELECT_FROM_RE = re.compile(r"SELECT\b.*?\bFROM\s+([A-Za-z_][\w$#]*)", _KW | re.DOTALL)


def _normalize_body(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _balanced_paren(text: str, open_pos: int) -> int:
    depth = 0
    for i in range(open_pos, len(text)):
        c = text[i]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i
    return -1


def _find_procs(text: str) -> list[dict]:
    out: list[dict] = []
    for m in _CREATE_HEAD_RE.finditer(text):
        head_start = m.start()
        open_idx = m.end() - 1
        close_idx = _balanced_paren(text, open_idx)
        if close_idx < 0:
            continue
        params = text[open_idx + 1:close_idx]
        tail = text[close_idx + 1:]
        end_re = re.compile(r"\bEND\s+" + m.group("kind") + r"\s*;", _KW)
        em = end_re.search(tail)
        if not em:
            continue
        rest = tail[: em.start()]
        full = text[head_start: close_idx + 1 + em.end()]
        out.append({
            "kind": m.group("kind").upper(),
            "name": m.group("name"),
            "params": params,
            "rest": rest,
            "full": full,
        })
    return out


def _parse_params(params: str) -> list[dict]:
    out: list[dict] = []
    if not params.strip():
        return out
    parts: list[str] = []
    depth = 0
    buf: list[str] = []
    for ch in params:
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
    for p in parts:
        toks = p.split()
        if not toks:
            continue
        if toks[0].upper() in ("IN", "OUT", "INOUT"):
            mode = toks[0].upper()
            name = toks[1]
            ptype = " ".join(toks[2:])
        else:
            mode = "IN"
            name = toks[0]
            ptype = " ".join(toks[1:])
        out.append({"name": name, "mode": mode, "type": ptype.strip()})
    return out


def _complexity(body: str) -> int:
    n = 1
    n += len(_IF_RE.findall(body))
    n += len(_WHILE_RE.findall(body))
    n += len(_FOR_RE.findall(body))
    n += len(_CASE_RE.findall(body))
    return n


def _dml_tables(body: str) -> dict[str, set[str]]:
    reads: set[str] = set()
    writes: set[str] = set()
    for m in _INSERT_RE.finditer(body):
        writes.add(m.group(1))
    for m in _UPDATE_RE.finditer(body):
        writes.add(m.group(1))
    for m in _DELETE_RE.finditer(body):
        writes.add(m.group(1))
    for m in _SELECT_FROM_RE.finditer(body):
        reads.add(m.group(1))
    return {"reads": reads, "writes": writes}


class SQLPLExtractor:
    artifact_type = "sql_pl"

    def can_handle(self, file_path: Path) -> bool:
        if file_path.suffix.lower() != ".sql":
            return False
        try:
            text = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return False
        return bool(re.search(r"CREATE\s+(PROCEDURE|FUNCTION)\b", text, _KW))

    def extract(
        self, file_path: Path, codebase_id: str = "default"
    ) -> ExtractionResult:
        text = file_path.read_text(encoding="utf-8", errors="replace")
        result = ExtractionResult(
            artifact_type=self.artifact_type,
            source_file=str(file_path),
        )
        for proc in _find_procs(text):
            self._emit_proc(proc, codebase_id, result)
        return result

    def _emit_proc(
        self, proc: dict, codebase_id: str, result: ExtractionResult
    ) -> None:
        name = proc["name"]
        kind = proc["kind"]
        params = _parse_params(proc["params"])
        rest = proc["rest"] or ""

        begin_m = re.search(r"\bBEGIN\b", rest, _KW)
        body = rest[begin_m.end():] if begin_m else rest
        parse_conf = 1.0 if begin_m else 0.5
        norm_body = _normalize_body(proc["full"])

        lang_match = _LANG_RE.search(rest)
        lang = lang_match.group(1).upper() if lang_match else "SQL PL"
        if lang == "SQL":
            lang = "SQL PL"
        dyn_match = _DYN_RE.search(rest)
        dyn = int(dyn_match.group(1)) if dyn_match else 0

        scan_body = body or rest
        comp = _complexity(scan_body)
        dml = _dml_tables(scan_body)
        calls = {c for c in _CALL_RE.findall(scan_body) if c.upper() != name.upper()}

        node = Node(
            id=make_node_id("StoredProcedure", codebase_id, name),
            type=NodeType.STORED_PROCEDURE,
            name=name,
            codebase_id=codebase_id,
            content_hash=content_hash(norm_body),
            parse_confidence=parse_conf,
            properties={
                "language": lang,
                "kind": kind,
                "parameters": params,
                "complexity_score": comp,
                "dynamic_result_sets": dyn,
                "source": "ddl_export",
                "called_procs": sorted(calls),
                "reads": sorted(dml["reads"]),
                "writes": sorted(dml["writes"]),
            },
        )
        result.nodes.append(node)
        result.units.append(LogicalUnit(
            kind="stored_procedure", name=name,
            source=norm_body,
            content_hash=content_hash(norm_body),
            properties={"complexity_score": comp},
        ))

        for c in calls:
            result.edges.append(Edge(
                src=node.id,
                dst=make_node_id("StoredProcedure", codebase_id, c),
                type=EdgeType.INVOKES_PROC,
                properties={},
            ))
        for t in dml["writes"]:
            result.edges.append(Edge(
                src=node.id,
                dst=make_node_id("DB2Table", codebase_id, t),
                type=EdgeType.WRITES,
                properties={},
            ))
        for t in dml["reads"]:
            result.edges.append(Edge(
                src=node.id,
                dst=make_node_id("DB2Table", codebase_id, t),
                type=EdgeType.READS,
                properties={},
            ))


__all__ = ["SQLPLExtractor"]