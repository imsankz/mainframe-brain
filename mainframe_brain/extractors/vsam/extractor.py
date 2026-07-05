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

_VSAM_ORG = {
    "INDEXED": "KSDS",
    "RELATIVE": "RRDS",
}

_SELECT_RE = re.compile(
    r"SELECT\s+(\S+)\s+ASSIGN\s+TO\s+(\S+)\.?(.*?)(?=SELECT\b|\Z)",
    re.IGNORECASE | re.DOTALL,
)
_ORG_RE = re.compile(
    r"ORGANIZATION\s+IS\s+(LINE\s+SEQUENTIAL|SEQUENTIAL|INDEXED|RELATIVE)\b",
    re.IGNORECASE,
)
_ACCESS_RE = re.compile(r"ACCESS\s+MODE\s+IS\s+(SEQUENTIAL|RANDOM|DYNAMIC)\b", re.IGNORECASE)
_RECORD_KEY_RE = re.compile(r"RECORD\s+KEY\s+IS\s+([\w-]+)", re.IGNORECASE)
_ALT_KEY_RE = re.compile(
    r"ALTERNATE\s+RECORD\s+KEY\s+IS\s+([\w-]+)(?:\s+(?:WITH\s+DUPLICATES))?",
    re.IGNORECASE,
)
_FD_RE = re.compile(
    r"\bFD\s+(\S+)(.*?)(?=\b(?:FD|SD)\b|PROCEDURE\s+DIVISION|WORKING-STORAGE|LINKAGE|\Z)",
    re.IGNORECASE | re.DOTALL,
)
_RECORD_NAME_RE = re.compile(r"^\s*\d+\s+([\w-]+)", re.MULTILINE)

_PROGRAM_ID_RE = re.compile(r"PROGRAM-ID\s*\.\s*([\w-]+)", re.IGNORECASE)
_PROC_DIV_RE = re.compile(r"PROCEDURE\s+DIVISION", re.IGNORECASE)

def _normalize_ws(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.splitlines())


class VSAMExtractor:
    artifact_type = "vsam"

    def can_handle(self, file_path: Path) -> bool:
        return file_path.suffix.lower() in (".cbl", ".cob")

    def extract(self, file_path: Path, codebase_id: str = "default") -> ExtractionResult:
        raw = file_path.read_text(encoding="utf-8", errors="replace")
        program_id = _PROGRAM_ID_RE.search(raw)
        program_name = program_id.group(1) if program_id else "unknown"
        program_node_id = make_node_id("Program", codebase_id, program_name)

        selects = self._parse_selects(raw)
        fd_map = self._parse_fds(raw)
        self._attach_fds(selects, fd_map)

        result = ExtractionResult(
            artifact_type=self.artifact_type,
            source_file=str(file_path),
        )

        record_to_select: dict[str, str] = {}
        for sel_name, sel in selects.items():
            if sel.get("record_name"):
                record_to_select[sel["record_name"]] = sel_name

        for sel_name, sel in selects.items():
            unit_text = sel["select_text"]
            if sel.get("fd_text"):
                unit_text = unit_text + "\n" + sel["fd_text"]
            normalized = _normalize_ws(unit_text)
            unit = LogicalUnit(
                kind="file_descriptor",
                name=sel_name,
                source=normalized,
                content_hash=content_hash(unit_text),
            )
            result.units.append(unit)

            label = sel["external_dataset_name"] or sel_name
            if sel["organization"] in ("INDEXED", "RELATIVE"):
                node = Node(
                    id=make_node_id("VSAMDataset", codebase_id, sel_name),
                    type=NodeType.VSAM_DATASET,
                    name=sel_name,
                    codebase_id=codebase_id,
                    content_hash=unit.content_hash,
                    parse_confidence=sel["confidence"],
                    properties={
                        "organization": _VSAM_ORG[sel["organization"]],
                        "external_dataset": label,
                        "access_mode": sel.get("access_mode", ""),
                        "record_key": sel.get("record_key", ""),
                        "alternate_keys": sel.get("alternate_keys", []),
                    },
                )
            else:
                node = Node(
                    id=make_node_id("Dataset", codebase_id, sel_name),
                    type=NodeType.DATASET,
                    name=sel_name,
                    codebase_id=codebase_id,
                    content_hash=unit.content_hash,
                    parse_confidence=sel["confidence"],
                    properties={
                        "DSORG": "PS",
                        "external_dataset": label,
                        "organization": sel["organization"],
                    },
                )
            result.nodes.append(node)

        self._emit_verb_edges(raw, selects, record_to_select, program_node_id, result)

        return result

    def _parse_selects(self, raw: str) -> dict[str, dict]:
        cased = raw
        selects: dict[str, dict] = {}
        for m in _SELECT_RE.finditer(cased):
            sel_name = m.group(1)
            external = m.group(2)
            rest = m.group(3) or ""
            org_match = _ORG_RE.search(rest)
            access_match = _ACCESS_RE.search(rest)
            rkey_match = _RECORD_KEY_RE.search(rest)
            alt_keys = [a.group(1) for a in _ALT_KEY_RE.finditer(rest)]
            confidence = 1.0
            if org_match is None:
                confidence = 0.8
            org = org_match.group(1).upper() if org_match else "SEQUENTIAL"
            selects[sel_name] = {
                "external_dataset_name": external,
                "organization": org,
                "access_mode": access_match.group(1).upper() if access_match else "",
                "record_key": rkey_match.group(1) if rkey_match else "",
                "alternate_keys": alt_keys,
                "confidence": confidence,
                "select_text": m.group(0),
                "fd_text": "",
                "record_name": "",
            }
        return selects

    def _parse_fds(self, raw: str) -> dict[str, dict]:
        fds: dict[str, dict] = {}
        for m in _FD_RE.finditer(raw):
            name = m.group(1).rstrip(".")
            body = m.group(2) or ""
            rn_match = _RECORD_NAME_RE.search(body)
            record_name = rn_match.group(1).rstrip(".") if rn_match else ""
            fds[name] = {"fd_text": m.group(0).rstrip(), "record_name": record_name}
        return fds

    def _attach_fds(self, selects: dict[str, dict], fds: dict[str, dict]) -> None:
        for name, fd in fds.items():
            if name in selects:
                selects[name]["fd_text"] = fd["fd_text"]
                selects[name]["record_name"] = fd["record_name"]

    def _emit_verb_edges(
        self,
        raw: str,
        selects: dict[str, dict],
        record_to_select: dict[str, str],
        program_node_id: str,
        result: ExtractionResult,
    ) -> None:
        proc_match = _PROC_DIV_RE.search(raw)
        proc_text = raw[proc_match.start():] if proc_match else ""

        codebase_id = next((n.codebase_id for n in result.nodes), "default")
        node_ids: dict[str, str] = {}
        for sel_name, sel in selects.items():
            node_type = "VSAMDataset" if sel["organization"] in ("INDEXED", "RELATIVE") else "Dataset"
            node_ids[sel_name] = make_node_id(node_type, codebase_id, sel_name)

        upper_selects = {k.upper(): k for k in selects}
        upper_records = {k.upper(): v for k, v in record_to_select.items()}
        counts: dict[tuple[str, str, EdgeType], int] = {}

        def bump(verb: str, sel_key: str, etype: EdgeType) -> None:
            counts[(verb, sel_key, etype)] = counts.get((verb, sel_key, etype), 0) + 1

        def resolve_select_by_name(name: str) -> str | None:
            name = name.upper().rstrip(".")
            sel_key = None
            if name in upper_selects:
                sel_key = upper_selects[name]
            return sel_key

        def resolve_select_by_record(name: str) -> str | None:
            name = name.upper().rstrip(".")
            if name in upper_records:
                return upper_records[name]
            return None

        for m in re.finditer(r"\bREAD\s+([A-Z0-9-]+)(?:\s+NEXT)?\s+RECORD\b", proc_text):
            sel = resolve_select_by_name(m.group(1))
            if sel:
                bump("READ", sel, EdgeType.READS)

        for m in re.finditer(r"\bDELETE\s+([A-Z0-9-]+)\b", proc_text):
            name = m.group(1).upper()
            sel = upper_selects.get(name) or resolve_select_by_record(name)
            if sel:
                bump("DELETE", sel, EdgeType.READS)

        for m in re.finditer(r"\bSTART\s+([A-Z0-9-]+)\b", proc_text):
            sel = resolve_select_by_name(m.group(1))
            if sel:
                bump("START", sel, EdgeType.READS)

        for m in re.finditer(r"\bWRITE\s+([\w-]+)", proc_text):
            sel = resolve_select_by_record(m.group(1))
            if sel:
                bump("WRITE", sel, EdgeType.WRITES)

        for m in re.finditer(r"\bREWRITE\s+([\w-]+)", proc_text):
            sel = resolve_select_by_record(m.group(1))
            if sel:
                bump("REWRITE", sel, EdgeType.WRITES)

        for (verb, sel_name, etype), count in counts.items():
            result.edges.append(
                Edge(
                    src=program_node_id,
                    dst=node_ids[sel_name],
                    type=etype,
                    properties={"verb": verb, "count": count},
                )
            )