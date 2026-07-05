"""Trigger extractor — DB2 trigger DDL + inferred trigger-chain edges.

The dangerous invisible cascade (section 5.2): when one trigger's body
performs DML against a table that has its own trigger, this extractor
emits a `TRIGGERS_TRIGGER` edge to a placeholder target keyed by the
touched table and event, even before the target trigger has been
registered in the graph. That makes the chain visible rather than a
silent accident.
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

_CREATE_TRIGGER_RE = re.compile(
    r"CREATE\s+TRIGGER\s+(?P<name>[A-Za-z_][\w$#]*)\s*"
    r"(?P<rest>.*?)\bEND\s*;",
    _KW | re.DOTALL,
)
_NO_CASCADE_RE = re.compile(r"NO\s+CASCADE", _KW)
_TIMING_RE = re.compile(r"\b(BEFORE|AFTER|INSTEAD\s+OF)\b", _KW)
_EVENT_RE = re.compile(
    r"\b(INSERT|DELETE|UPDATE(?:\s+OF\s+[A-Za-z_][\w$#]*(?:\s*,\s*[A-Za-z_][\w$#]*)*)?)\b",
    _KW,
)
_ON_RE = re.compile(r"\bON\s+(?P<table>[A-Za-z_][\w$#]*)", _KW)
_REF_RE = re.compile(
    r"\bREFERENCING\s+(?P<ref>.*?)\b(?:FOR\s+EACH|WHEN|BEGIN|MODE|;)",
    _KW | re.DOTALL,
)
_REF_ALIAS_RE = re.compile(
    r"(?P<which>NEW|OLD)(?:\s+TABLE)?\s+AS\s+(?P<alias>[A-Za-z_][\w$#]*)",
    _KW,
)
_FOR_EACH_RE = re.compile(r"FOR\s+EACH\s+(ROW|STATEMENT)", _KW)
_MODE_RE = re.compile(r"MODE\s+(\w+)", _KW)
_BEGIN_RE = re.compile(r"\bBEGIN\b", _KW)
_WHEN_RE = re.compile(r"\bWHEN\s*\(", _KW)
_IF_RE = re.compile(r"\bIF\b", _KW)
_WHILE_RE = re.compile(r"\bWHILE\b", _KW)
_FOR_RE = re.compile(r"\bFOR\b", _KW)
_CASE_RE = re.compile(r"\bCASE\b", _KW)

_DML_RE = re.compile(
    r"\b(?P<verb>INSERT\s+INTO|UPDATE|DELETE\s+FROM|SELECT(?:\s+DISTINCT)?)\s+"
    r"(?P<tbl>[A-Za-z_][\w$#]*)",
    _KW,
)
_DML_EVENT_RE = re.compile(
    r"\b(INSERT|UPDATE|DELETE)\b", _KW,
)


def _complexity(body: str) -> int:
    n = 1
    n += len(_IF_RE.findall(body))
    n += len(_WHILE_RE.findall(body))
    n += len(_FOR_RE.findall(body))
    n += len(_CASE_RE.findall(body))
    return n


def _event_of(verb: str) -> str:
    v = verb.upper()
    if v.startswith("INSERT"):
        return "INSERT"
    if v.startswith("UPDATE"):
        return "UPDATE"
    if v.startswith("DELETE"):
        return "DELETE"
    return v


class TriggerExtractor:
    artifact_type = "trigger"

    def can_handle(self, file_path: Path) -> bool:
        if file_path.suffix.lower() not in (".sql", ".ddl"):
            return False
        try:
            text = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return False
        return bool(re.search(r"CREATE\s+TRIGGER\b", text, _KW))

    def extract(
        self, file_path: Path, codebase_id: str = "default"
    ) -> ExtractionResult:
        text = file_path.read_text(encoding="utf-8", errors="replace")
        result = ExtractionResult(
            artifact_type=self.artifact_type,
            source_file=str(file_path),
        )
        for m in _CREATE_TRIGGER_RE.finditer(text):
            self._emit_trigger(m, codebase_id, result)
        return result

    def _emit_trigger(
        self, m: re.Match, codebase_id: str, result: ExtractionResult
    ) -> None:
        name = m.group("name")
        rest = m.group("rest") or ""
        full = m.group(0)

        timing_m = _TIMING_RE.search(rest)
        timing = timing_m.group(1).upper().replace("  ", " ") if timing_m else ""

        on_m = _ON_RE.search(rest)
        table = on_m.group("table") if on_m else ""

        events: list[str] = []
        for em in _EVENT_RE.finditer(rest):
            ev = em.group(1).upper()
            if ev not in events:
                events.append(ev)
        event = events[0] if events else ""
        base_event = event.split()[0] if event else ""

        no_cascade = bool(_NO_CASCADE_RE.search(rest))
        for_each_m = _FOR_EACH_RE.search(rest)
        granularity = for_each_m.group(1) if for_each_m else ""
        mode_m = _MODE_RE.search(rest)
        mode = mode_m.group(1) if mode_m else ""

        ref_m = _REF_RE.search(rest)
        references: list[dict] = []
        if ref_m:
            for am in _REF_ALIAS_RE.finditer(ref_m.group("ref")):
                references.append({"which": am.group("which").upper(),
                                  "alias": am.group("alias")})

        begin_m = _BEGIN_RE.search(rest)
        body = rest[begin_m.end():] if begin_m else rest
        parse_conf = 1.0 if (timing and event and table and begin_m) else 0.5

        norm = re.sub(r"\s+", " ", full).strip()
        comp = _complexity(body)

        node = Node(
            id=make_node_id("Trigger", codebase_id, name),
            type=NodeType.TRIGGER,
            name=name,
            codebase_id=codebase_id,
            content_hash=content_hash(norm),
            parse_confidence=parse_conf,
            properties={
                "timing": timing,
                "event": event,
                "base_event": base_event,
                "table": table,
                "referencing": references,
                "granularity": granularity,
                "mode": mode,
                "no_cascade": no_cascade,
                "complexity_score": comp,
                "body_hash": content_hash(re.sub(r"\s+", " ", body).strip()),
            },
        )
        result.nodes.append(node)
        result.units.append(LogicalUnit(
            kind="trigger", name=name,
            source=norm,
            content_hash=content_hash(norm),
            properties={"table": table, "timing": timing, "event": event},
        ))

        if table:
            result.edges.append(Edge(
                src=node.id,
                dst=make_node_id("DB2Table", codebase_id, table),
                type=EdgeType.FIRES_ON,
                properties={},
            ))

        if no_cascade:
            return

        fire_tables: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for dm in _DML_RE.finditer(body):
            tbl = dm.group("tbl")
            if not tbl or tbl.upper() == table.upper():
                continue
            ev = _event_of(dm.group("verb"))
            key = (tbl, ev)
            if key in seen:
                continue
            seen.add(key)
            fire_tables.append(key)

        for tbl, ev in fire_tables:
            placeholder = f"Trigger:{codebase_id}:ON:{tbl}:{ev}"
            result.edges.append(Edge(
                src=node.id,
                dst=placeholder,
                type=EdgeType.TRIGGERS_TRIGGER,
                properties={
                    "inferred": True,
                    "target_table": tbl,
                    "target_event": ev,
                    "note": ("chain target inferred from DML; resolved when "
                             "target trigger is registered"),
                },
            ))


__all__ = ["TriggerExtractor"]