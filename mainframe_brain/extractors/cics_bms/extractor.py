"""CICS BMS macro extractor — Phase 4 (architecture §4.1, §5.10).

Parses BMS mapset source (DFHMSD / DFHMDI / DFHMDF macros) into CICSMap
nodes with field definitions, one LogicalUnit per mapset block. Also
handles COBOL files containing EXEC CICS SEND/RECEIVE MAP by emitting
RENDERS_ON edges from the host program to the map nodes — but never
creates Program nodes (those are owned by the cobol extractor).
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

_DFHMSD_RE = re.compile(
    r"(?P<name>[A-Za-z][\w$#]*)\s+DFHMSD\b(?!\s*TYPE\s*=\s*FINAL)"
    r"(?P<rest>.*?)"
    r"(?=\b[A-Za-z][\w$#]*\s+DFHMSD\b(?!\s*TYPE\s*=\s*FINAL)|\Z)",
    _KW | re.DOTALL,
)
_DFHMDI_RE = re.compile(
    r"(?P<name>[A-Za-z][\w$#]*)\s+DFHMDI\b(?P<rest>[^\n]*)",
    _KW,
)
_DFHMDF_RE = re.compile(
    r"(?P<name>[A-Za-z][\w$#]*)\s+DFHMDF\b(?P<rest>.*?)"
    r"(?=\b[A-Za-z][\w$#]*\s+DFHM(?:DI|DF|SD)\b|\Z)",
    _KW | re.DOTALL,
)
_POS_RE = re.compile(r"POS\s*=\s*\(\s*(?P<line>\d+)\s*,\s*(?P<col>\d+)\s*\)", _KW)
_LENGTH_RE = re.compile(r"LENGTH\s*=\s*(?P<len>\d+)", _KW)
_ATTRB_RE = re.compile(r"ATTRB\s*=\s*\(?([\w,]+)\)?", _KW)
_INITIAL_RE = re.compile(r"INITIAL\s*=\s*'([^']*)'", _KW)
_FINAL_RE = re.compile(r"DFHMSD\s+TYPE\s*=\s*FINAL", _KW)

_PROGRAM_ID_RE = re.compile(r"PROGRAM-ID\.\s*([A-Z0-9-]+)", re.I)
_SEND_MAP_RE = re.compile(
    r"EXEC\s+CICS\s+SEND\s+MAP\s*\(\s*['\"]?(?P<map>[A-Za-z0-9_]+)['\"]?\s*\)",
    _KW,
)
_RECEIVE_MAP_RE = re.compile(
    r"EXEC\s+CICS\s+RECEIVE\s+MAP\s*\(\s*['\"]?(?P<map>[A-Za-z0-9_]+)['\"]?\s*\)",
    _KW,
)


class CICSBMSExtractor:
    artifact_type = "cics_bms"

    def can_handle(self, file_path: Path) -> bool:
        suffix = file_path.suffix.lower()
        if suffix in (".bms", ".map", ".cbs"):
            return True
        if suffix in (".cbl", ".cob"):
            try:
                text = file_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                return False
            return bool(re.search(r"EXEC\s+CICS\s+(SEND|RECEIVE)\s+MAP\b", text, _KW))
        return False

    def extract(self, file_path: Path, codebase_id: str = "default") -> ExtractionResult:
        text = file_path.read_text(encoding="utf-8", errors="replace")
        result = ExtractionResult(
            artifact_type=self.artifact_type,
            source_file=str(file_path),
        )
        suffix = file_path.suffix.lower()
        if suffix in (".cbl", ".cob"):
            self._emit_cics_edges(text, codebase_id, file_path, result)
            return result
        for m in _DFHMSD_RE.finditer(text):
            self._emit_mapset(m, codebase_id, result)
        return result

    def _emit_mapset(
        self, m: re.Match, codebase_id: str, result: ExtractionResult
    ) -> None:
        mapset_name = m.group("name")
        block = m.group(0)

        fields: list[dict] = []
        anomalies: list[str] = []
        maps: list[dict] = []
        for di in _DFHMDI_RE.finditer(block):
            maps.append({"name": di.group("name"), "header": di.group("rest").strip()})

        for df in _DFHMDF_RE.finditer(block):
            fname = df.group("name")
            fbody = df.group("rest") or ""
            pos_m = _POS_RE.search(fbody)
            length_m = _LENGTH_RE.search(fbody)
            attrb_m = _ATTRB_RE.search(fbody)
            initial_m = _INITIAL_RE.search(fbody)

            field: dict = {"name": fname}
            if pos_m:
                field["pos"] = [int(pos_m.group("line")), int(pos_m.group("col"))]
            else:
                field["pos"] = None
                anomalies.append(f"DFHMDF {fname}: missing POS")
            if length_m:
                field["length"] = int(length_m.group("len"))
            else:
                field["length"] = None
            field["attrb"] = attrb_m.group(1).upper() if attrb_m else ""
            field["initial"] = initial_m.group(1) if initial_m else ""
            fields.append(field)

        is_final = bool(_FINAL_RE.search(block))
        parse_conf = 1.0 if not anomalies and is_final else (0.8 if anomalies else 0.9)

        norm = "\n".join(line.rstrip() for line in block.splitlines())
        chash = content_hash(norm)

        props: dict = {
            "fields": fields,
            "maps": maps,
            "maps_seen": len(maps),
            "fields_seen": len(fields),
            "final_seen": is_final,
        }
        if anomalies:
            props["anomalies"] = anomalies

        node = Node(
            id=make_node_id("CICSMap", codebase_id, mapset_name),
            type=NodeType.CICS_MAP,
            name=mapset_name,
            codebase_id=codebase_id,
            content_hash=chash,
            parse_confidence=parse_conf,
            properties=props,
        )
        result.nodes.append(node)
        result.units.append(LogicalUnit(
            kind="bms_mapset",
            name=mapset_name,
            source=block,
            content_hash=chash,
            properties={"fields_seen": len(fields), "maps_seen": len(maps)},
        ))

    def _emit_cics_edges(
        self,
        text: str,
        codebase_id: str,
        file_path: Path,
        result: ExtractionResult,
    ) -> None:
        pid_m = _PROGRAM_ID_RE.search(text)
        prog_name = pid_m.group(1) if pid_m else file_path.stem
        prog_id = make_node_id("Program", codebase_id, prog_name.upper())

        referenced: set[str] = set()
        for rx in (_SEND_MAP_RE, _RECEIVE_MAP_RE):
            for mm in rx.finditer(text):
                referenced.add(mm.group("map").upper())

        for map_name in sorted(referenced):
            result.edges.append(Edge(
                src=prog_id,
                dst=make_node_id("CICSMap", codebase_id, map_name),
                type=EdgeType.RENDERS_ON,
                properties={
                    "inferred": True,
                    "source_program": prog_name.upper(),
                    "note": "edge only; Program node owned by cobol extractor",
                },
            ))


__all__ = ["CICSBMSExtractor"]