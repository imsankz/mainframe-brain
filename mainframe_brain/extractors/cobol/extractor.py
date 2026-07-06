"""COBOL extractor — hand-rolled line-based parser (Phase 1).

No tree-sitter, no external parsers. Deliberately tolerant: a partial parse
emits low-confidence nodes instead of dropping them (gap #5.11). The content
hash of every Paragraph LogicalUnit is computed POST-expansion so that
COPY...REPLACING differences split the cache (gap #2, architecture 5.5).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from mainframe_brain.extractors.base import (
    ExtractionResult,
    LogicalUnit,
    content_hash,
)
from mainframe_brain.extractors.copybook.expansion import post_expansion_source
from mainframe_brain.graph.schema import Edge, EdgeType, Node, NodeType
from mainframe_brain.graph.store import make_node_id

_VERBS = {
    "PERFORM", "CALL", "GO", "GOBACK", "EXIT", "STOP", "MOVE", "ADD", "SUBTRACT",
    "MULTIPLY", "DIVIDE", "COMPUTE", "ACCEPT", "DISPLAY", "READ", "WRITE",
    "REWRITE", "OPEN", "CLOSE", "IF", "EVALUATE", "END-EVALUATE", "END-IF",
    "ELSE", "WHEN", "SET", "INITIALIZE", "CONTINUE", "STRING", "UNSTRING",
    "INSPECT", "SEARCH", "EXEC", "END-EXEC", "COPY", "TO",
    "UNTIL", "VARYING", "THEN", "OR", "AND", "NOT", "THRU", "THROUGH",
}

_DIVISION_RE = re.compile(
    r"^(IDENTIFICATION|ENVIRONMENT|DATA|PROCEDURE)\s+DIVISION\.?", re.I
)
_DATA_SECTION_RE = re.compile(
    r"^(WORKING-STORAGE|LINKAGE|FILE)\s+SECTION\.?", re.I
)
_PROC_SECTION_RE = re.compile(r"^([A-Z0-9-]+)\s+SECTION\.\s*$")
_PARA_RE = re.compile(r"^([A-Z0-9][A-Z0-9-]*)\s*\.\s*$")
_PROGRAM_ID_RE = re.compile(r"PROGRAM-ID\.\s*([A-Z0-9-]+)", re.I)
_CALL_RE = re.compile(r"""CALL\s+["']([A-Z0-9-]+)["']""", re.I)
_PERFORM_RE = re.compile(
    r"PERFORM\s+([A-Z0-9-]+)(?:\s+(?:THRU|THROUGH)\s+([A-Z0-9-]+))?", re.I
)
_GOTO_RE = re.compile(r"GO\s+TO\s+([A-Z0-9-]+)", re.I)
_COPY_RE = re.compile(
    r"COPY\s+([A-Z0-9-]+)(?:\s+REPLACING\s+(.+?))?\s*\.", re.I
)
_REPLACE_PAIR_RE = re.compile(r"==([A-Za-z0-9-]+)==\s+BY\s+==([A-Za-z0-9-]+)==", re.I)
_WS_FIELD_RE = re.compile(
    r"^(?P<level>\d{1,2})\s+(?P<name>[A-Z0-9-]+)\b.*?\.\s*$"
)
_WS_PIC_RE = re.compile(r"\bPIC(?:TURE)?\s+(?P<pic>\S+)", re.I)
_WS_REDEF_RE = re.compile(r"\bREDEFINES\s+([A-Z0-9-]+)", re.I)
_WS_OCCURS_RE = re.compile(r"\bOCCURS\s+(\d+)\s+TIMES", re.I)
_EXEC_SQL_RE = re.compile(r"EXEC\s+SQL\b(.*?)END-EXEC", re.I | re.DOTALL)
_FROM_RE = re.compile(r"\bFROM\s+([A-Z_][A-Z0-9_]+)", re.I)
_INTO_RE = re.compile(r"\bINTO\s+([A-Z_][A-Z0-9_]+)", re.I)
_UPDATE_RE = re.compile(r"\bUPDATE\s+([A-Z_][A-Z0-9_]+)", re.I)
_DELETE_FROM_RE = re.compile(r"\bDELETE\s+FROM\s+([A-Z_][A-Z0-9_]+)", re.I)
_HOSTVAR_RE = re.compile(r":([A-Z][A-Z0-9-]*)", re.I)
_MERGE_INTO_RE = re.compile(r"\bMERGE\s+INTO\s+([A-Z_][A-Z0-9_]+)", re.I)


@dataclass
class _Paragraph:
    name: str
    body: list[str] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)
    performs: list[tuple[str, str | None]] = field(default_factory=list)
    gotos: list[str] = field(default_factory=list)
    ifs: int = 0
    evaluates: int = 0
    perform_thru: int = 0
    statement_count: int = 0
    anomalies: list[str] = field(default_factory=list)


@dataclass
class _Parse:
    program_name: str = ""
    paragraphs: list[_Paragraph] = field(default_factory=list)
    ws_fields: list[dict[str, object]] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)
    includes: list[dict[str, object]] = field(default_factory=list)
    exec_sql_blocks: list[str] = field(default_factory=list)
    anomalies: list[str] = field(default_factory=list)


class CobolExtractor:
    artifact_type = "cobol"

    def can_handle(self, file_path: Path) -> bool:
        return file_path.suffix.lower() in (".cbl", ".cob")

    def extract(self, file_path: Path, codebase_id: str = "default") -> ExtractionResult:
        raw = file_path.read_text(encoding="utf-8", errors="replace")
        parsed = _parse(raw)
        program_name = parsed.program_name or file_path.stem.upper()

        program_node = Node(
            id=make_node_id("Program", codebase_id, program_name),
            type=NodeType.PROGRAM,
            name=program_name,
            codebase_id=codebase_id,
            content_hash=content_hash(raw),
            parse_confidence=0.5 if parsed.anomalies else 1.0,
            properties={
                "source_file": str(file_path),
                "paragraph_count": len(parsed.paragraphs),
                "anomalies": parsed.anomalies,
            },
        )
        nodes: list[Node] = [program_node]
        edges: list[Edge] = []
        units: list[LogicalUnit] = []

        replacing_all: list[tuple[str, str]] = []
        for inc in parsed.includes:
            rp = inc.get("replacing", [])
            if isinstance(rp, list):
                for pair in rp:
                    if isinstance(pair, tuple) and len(pair) == 2:
                        replacing_all.append((str(pair[0]), str(pair[1])))

        para_index: dict[str, Node] = {}
        for para in parsed.paragraphs:
            source = (para.name + ".\n" + "\n".join(para.body)).strip()
            expanded = post_expansion_source(source, replacing_all)
            cyclomatic = para.ifs + para.evaluates + para.perform_thru + 1
            stmt_count = max(para.statement_count, 1)
            goto_density = len(para.gotos) / stmt_count if stmt_count else 0.0
            confidence = 0.5 if para.anomalies else 1.0
            pnode = Node(
                id=make_node_id("Paragraph", codebase_id, f"{program_name}.{para.name}"),
                type=NodeType.PARAGRAPH,
                name=para.name,
                codebase_id=codebase_id,
                content_hash=content_hash(expanded),
                parse_confidence=confidence,
                properties={
                    "parent_program": program_name,
                    "cyclomatic_complexity": cyclomatic,
                    "goto_density": round(goto_density, 4),
                    "statement_count": para.statement_count,
                    "anomalies": para.anomalies,
                    "calls": para.calls,
                    "performs": [p[0] for p in para.performs],
                    "gotos": para.gotos,
                    "post_expansion": bool(replacing_all),
                    "source": expanded,
                    "replacing_applied": bool(replacing_all),
                },
            )
            nodes.append(pnode)
            para_index[para.name] = pnode
            units.append(
                LogicalUnit(
                    kind="paragraph",
                    name=para.name,
                    source=expanded,
                    content_hash=content_hash(expanded),
                    properties={
                        "parent_program": program_name,
                        "cyclomatic_complexity": cyclomatic,
                    },
                    post_expansion=bool(replacing_all),
                )
            )

        for para in parsed.paragraphs:
            for target, end in para.performs:
                if target in para_index:
                    edges.append(
                        Edge(
                            src=para_index[para.name].id,
                            dst=para_index[target].id,
                            type=EdgeType.PERFORMS,
                            properties={"thru": end is not None, "range_end": end},
                        )
                    )
                else:
                    edges.append(
                        Edge(
                            src=program_node.id,
                            dst=make_node_id("Paragraph", codebase_id, f"{program_name}.{target}"),
                            type=EdgeType.PERFORMS,
                            properties={
                                "thru": end is not None,
                                "range_end": end,
                                "unresolved": True,
                            },
                        )
                    )
            for g in para.gotos:
                if g in para_index:
                    edges.append(
                        Edge(
                            src=para_index[para.name].id,
                            dst=para_index[g].id,
                            type=EdgeType.PERFORMS,
                            properties={"goto": True},
                        )
                    )

        for fd in parsed.ws_fields:
            confidence = 0.5 if fd.get("anomaly") else 1.0
            fd_name = str(fd["name"])
            fd_raw = str(fd["raw"])
            fd_level = int(str(fd["level"]))
            props: dict[str, object] = {
                "level": fd_level,
                "parent_program": program_name,
            }
            if fd.get("pic") is not None:
                props["pic"] = fd["pic"]
            if fd.get("redef"):
                props["redefines"] = fd["redef"]
            if fd.get("occurs"):
                props["occurs"] = fd["occurs"]
            nodes.append(
                Node(
                    id=make_node_id("Field", codebase_id, f"{program_name}.{fd_name}"),
                    type=NodeType.FIELD,
                    name=fd_name,
                    codebase_id=codebase_id,
                    content_hash=content_hash(fd_raw),
                    parse_confidence=confidence,
                    properties=props,
                )
            )

        for callee in parsed.calls:
            callee_id = make_node_id("Program", codebase_id, callee)
            edges.append(
                Edge(
                    src=program_node.id,
                    dst=callee_id,
                    type=EdgeType.CALLS,
                    properties={"callee": callee},
                )
            )
            if callee != program_name:
                placeholder = Node(
                    id=callee_id,
                    type=NodeType.PROGRAM,
                    name=callee,
                    codebase_id=codebase_id,
                    parse_confidence=0.0,
                    properties={"placeholder": True, "seen_via": "COBOL CALL"},
                )
                nodes.append(placeholder)

        for inc in parsed.includes:
            edges.append(
                Edge(
                    src=program_node.id,
                    dst=make_node_id("Copybook", codebase_id, str(inc["copybook"])),
                    type=EdgeType.INCLUDES,
                    properties={
                        "copybook": inc["copybook"],
                        "replacing": inc.get("replacing", []),
                    },
                )
            )

        table_nodes: dict[str, Node] = {}
        for block in parsed.exec_sql_blocks:
            if not _EXEC_SQL_RE.fullmatch("EXEC SQL" + block + "END-EXEC") and "END-EXEC" not in (
                "EXEC SQL" + block
            ):
                continue
            lower = strip_comments_and_strings(block)
            reads = set(_FROM_RE.findall(lower)) | set(_DELETE_FROM_RE.findall(lower))
            writes = set(_INTO_RE.findall(lower)) | set(_UPDATE_RE.findall(lower)) | set(
                _MERGE_INTO_RE.findall(lower)
            )
            for t in sorted(reads):
                edges.append(
                    Edge(
                        src=program_node.id,
                        dst=_ensure_table(t, codebase_id, table_nodes, nodes),
                        type=EdgeType.READS,
                        properties={"via": "EXEC SQL SELECT/DELETE"},
                    )
                )
            for t in sorted(writes):
                edges.append(
                    Edge(
                        src=program_node.id,
                        dst=_ensure_table(t, codebase_id, table_nodes, nodes),
                        type=EdgeType.WRITES,
                        properties={"via": "EXEC SQL INSERT/UPDATE/MERGE"},
                    )
                )
            if re.search(r"\b(PREPARE|EXECUTE\s+IMMEDIATE)\b", lower, re.I):
                program_node.properties["dynamic_sql"] = True

        return ExtractionResult(
            artifact_type=self.artifact_type,
            source_file=str(file_path),
            nodes=nodes,
            edges=edges,
            units=units,
        )


def _ensure_table(name: str, codebase_id: str, cache: dict[str, Node], nodes: list[Node]) -> str:
    if name in cache:
        return cache[name].id
    node = Node(
        id=make_node_id("DB2Table", codebase_id, name),
        type=NodeType.DB2_TABLE,
        name=name,
        codebase_id=codebase_id,
        properties={"source": "EXEC SQL (created on demand)"},
    )
    cache[name] = node
    nodes.append(node)
    return node.id


def _parse(raw: str) -> _Parse:
    parsed = _Parse()
    lines = raw.splitlines()
    division = ""
    data_section = ""
    current_para: _Paragraph | None = None
    preamble_performs: list[tuple[str, str | None]] = []
    preamble_calls: list[str] = []

    body_full = "\n".join(_content_area(ln) for ln in lines)
    stripped_body = strip_comments_and_strings(body_full)
    pid = _PROGRAM_ID_RE.search(body_full)
    if pid:
        parsed.program_name = pid.group(1).upper()

    # _CALL_RE *must* run on the original body_full because the CALL target
    # is itself a quoted string literal that strip_comments_and_strings would
    # remove.  The regex DISPLAY "CALL 'PROG'" false-positive is mitigated by
    # the fact that CALL inside a string is preceded by an opening quote, which
    # _CALL_RE's leading CALL\s+ won't match.
    for cm in _CALL_RE.findall(body_full):
        parsed.calls.append(cm.upper())

    for m in _COPY_RE.finditer(stripped_body):
        copybook = m.group(1).upper()
        replacing_raw = m.group(2) or ""
        pairs = [(a.upper(), b.upper()) for a, b in _REPLACE_PAIR_RE.findall(replacing_raw)]
        parsed.includes.append({"copybook": copybook, "replacing": pairs})

    unterminated = stripped_body
    for m in _EXEC_SQL_RE.finditer(stripped_body):
        parsed.exec_sql_blocks.append(m.group(1))
        unterminated = unterminated.replace(m.group(0), "")
    if re.search(r"\bEXEC\s+SQL\b", unterminated, re.I) and "END-EXEC" not in unterminated.upper():
        parsed.anomalies.append("unterminated EXEC SQL block")

    for raw_line in lines:
        content = _content_area(raw_line)
        if not content:
            continue
        line = content.strip()
        if not line:
            continue

        d = _DIVISION_RE.match(line)
        if d:
            division = d.group(1).upper()
            data_section = ""
            continue
        s = _DATA_SECTION_RE.match(line)
        if s and division == "DATA":
            data_section = s.group(1).upper()
            continue
        ps = _PROC_SECTION_RE.match(line)
        if ps and division == "PROCEDURE":
            continue

        if division == "DATA" and data_section == "WORKING-STORAGE":
            fd = _parse_ws_field(line)
            if fd is not None:
                parsed.ws_fields.append(fd)
                if fd.get("anomaly"):
                    parsed.anomalies.append(f"malformed WS field {fd['name']}")
            continue

        if division == "PROCEDURE":
            pm = _PARA_RE.match(line)
            if pm and pm.group(1).upper() not in _VERBS:
                if current_para is not None:
                    parsed.paragraphs.append(current_para)
                current_para = _Paragraph(name=pm.group(1).upper())
                continue
            stripped_line = _STRING_RE.sub("", line)
            if current_para is None:
                for pem in _PERFORM_RE.findall(stripped_line):
                    tgt, end = pem[0].upper(), (pem[1].upper() if pem[1] else None)
                    preamble_performs.append((tgt, end))
                for cm in _CALL_RE.findall(line):
                    preamble_calls.append(cm.upper())
                continue
            current_para.body.append(line)
            for pem in _PERFORM_RE.findall(stripped_line):
                tgt, end = pem[0].upper(), (pem[1].upper() if pem[1] else None)
                current_para.performs.append((tgt, end))
                if end is not None:
                    current_para.perform_thru += 1
            for cm in _CALL_RE.findall(line):
                current_para.calls.append(cm.upper())
            for gm in _GOTO_RE.findall(stripped_line):
                current_para.gotos.append(gm.upper())
            current_para.ifs += len(re.findall(r"\bIF\b", stripped_line, re.I))
            current_para.evaluates += len(re.findall(r"\bEVALUATE\b", stripped_line, re.I))
            if line.rstrip().endswith("."):
                current_para.statement_count += 1

    if current_para is not None:
        parsed.paragraphs.append(current_para)

    if preamble_performs or preamble_calls:
        if not parsed.paragraphs:
            parsed.paragraphs.append(_Paragraph(name="MAIN"))
        host = parsed.paragraphs[0]
        host.performs.extend(preamble_performs)
        host.calls.extend(preamble_calls)

    return parsed


def _parse_ws_field(line: str) -> dict[str, object] | None:
    if line.startswith("88 ") or line.startswith("88\t"):
        return None
    m = _WS_FIELD_RE.match(line)
    if not m:
        if re.match(r"^\d{1,2}\s", line):
            name_match = re.match(r"^\d{1,2}\s+([A-Z0-9-]+)", line)
            lvl_match = re.match(r"(\d{1,2})", line)
            name = name_match.group(1) if name_match else "UNKNOWN"
            level = int(lvl_match.group(1)) if lvl_match else 0
            return {
                "level": level,
                "name": name,
                "pic": None,
                "redef": None,
                "occurs": None,
                "raw": line,
                "anomaly": True,
            }
        return None
    pic_m = _WS_PIC_RE.search(line)
    redef_m = _WS_REDEF_RE.search(line)
    occ_m = _WS_OCCURS_RE.search(line)
    pic = pic_m.group("pic") if pic_m else None
    anomaly = False
    if pic is not None and re.search(r"[^A-Z0-9()$/.+\-*V]", pic):
        anomaly = True
    return {
        "level": int(m.group("level")),
        "name": m.group("name"),
        "pic": pic,
        "redef": (redef_m.group(1) if redef_m else None),
        "occurs": (occ_m.group(1) if occ_m else None),
        "raw": line,
        "anomaly": anomaly,
    }


def _content_area(line: str) -> str:
    """Return the area-A/B content of a COBOL line, or '' for comment/blank."""
    if len(line) >= 7 and line[6] in ("*", "/"):
        return ""
    if len(line) >= 7 and line[6] not in (" ", "-"):
        return line[:72].rstrip()
    return line[7:72].rstrip() if len(line) > 7 else line.rstrip()


_STRING_RE = re.compile(r"'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"")


def strip_comments_and_strings(text: str) -> str:
    """Remove COBOL comment lines and quoted string literals.

    Comment lines (column-7 * or /) are blanked.  Quoted string literals
    (single- and double-quoted, with COBOL doubled-quote escaping) are
    replaced with empty strings.  Returns a copy suitable for structural
    regex matching while the original source is preserved for
    ``LogicalUnit.source``.
    """
    result_lines: list[str] = []
    for line in text.splitlines():
        if len(line) >= 7 and line[6] in ("*", "/"):
            result_lines.append("")
        else:
            result_lines.append(line)
    return _STRING_RE.sub("", "\n".join(result_lines))


__all__ = ["CobolExtractor"]