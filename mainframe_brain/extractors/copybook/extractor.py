"""Copybook extractor — parses field layouts (REDEFINES, OCCURS, 88-levels).

Hashing is post-expansion (architecture 5.5): a copybook imported with
COPY...REPLACING hashes differently from the same copybook imported raw.
The expansion itself runs in the cobol extractor (where the REPLACING clause
lives); this extractor records whether the copybook file *itself* carries a
REPLACING directive (rare) and parses its field tree.
"""
from __future__ import annotations

import re
from pathlib import Path

from mainframe_brain.extractors.base import (
    ExtractionResult,
    LogicalUnit,
    content_hash,
)
from mainframe_brain.extractors.copybook.expansion import expand_copybook
from mainframe_brain.graph.schema import Edge, Node, NodeType
from mainframe_brain.graph.store import make_node_id

_LEVEL_RE = re.compile(r"^(?P<level>\d{1,2})\s+(?P<name>[A-Z0-9-]+)\b.*?\.\s*$")
_COND_RE = re.compile(r"^88\s+(?P<name>[A-Z0-9-]+)\b.*?\.\s*$")
_REDEFINES_RE = re.compile(r"\bREDEFINES\s+([A-Z0-9-]+)", re.I)
_OCCURS_RE = re.compile(r"\bOCCURS\s+(\d+)\s+TIMES", re.I)
_PIC_RE = re.compile(r"\bPIC(?:TURE)?\s+(?P<pic>\S+)", re.I)
_PIC_VALID_RE = re.compile(r"^[A-Z0-9()$/.+\-*VS]+$|^[A-Z0-9()$/.+\-*V]+$", re.I)
_REPLACING_RE = re.compile(r"==([A-Za-z0-9-]+)==\s+BY\s+==([A-Za-z0-9-]+)==")


class CopybookExtractor:
    artifact_type = "copybook"

    def can_handle(self, file_path: Path) -> bool:
        return file_path.suffix.lower() in (".cpy", ".copy")

    def extract(self, file_path: Path, codebase_id: str = "default") -> ExtractionResult:
        raw = file_path.read_text(encoding="utf-8", errors="replace")
        name = file_path.stem.upper()
        anomalies: list[str] = []
        replacing_in_file = _REPLACING_RE.findall(raw)
        replaced = [(a, b) for a, b in replacing_in_file]

        program_node = Node(
            id=make_node_id("Copybook", codebase_id, name),
            type=NodeType.COPYBOOK,
            name=name,
            codebase_id=codebase_id,
            content_hash=content_hash(expand_copybook(raw, replaced)),
            properties={
                "replacing_applied": bool(replaced),
                "source_file": str(file_path),
            },
        )
        nodes: list[Node] = [program_node]
        edges: list[Edge] = []
        units: list[LogicalUnit] = []

        expanded = expand_copybook(raw, replaced)
        buffer: list[str] = []
        for raw_line in expanded.splitlines():
            line = _content_area(raw_line)
            if not line:
                continue
            stripped = line.strip()
            if not stripped:
                continue
            buffer.append(stripped)
            if not stripped.endswith("."):
                continue
            stmt = " ".join(buffer)
            buffer = []
            if _COND_RE.match(stmt):
                continue
            m = _LEVEL_RE.match(stmt)
            if not m:
                if re.match(r"^\d{1,2}\s", stmt):
                    anomalies.append(f"malformed data entry: {stmt}")
                    nm = re.match(r"^\d{1,2}\s+([A-Z0-9-]+)", stmt)
                    lvl = re.match(r"(\d{1,2})", stmt)
                    extra_level = int(lvl.group(1)) if lvl else 0
                    extra_name = nm.group(1) if nm else "UNKNOWN"
                    nodes.append(
                        Node(
                            id=make_node_id("Field", codebase_id, f"{name}.{extra_name}"),
                            type=NodeType.FIELD,
                            name=extra_name,
                            codebase_id=codebase_id,
                            content_hash=content_hash(stmt),
                            parse_confidence=0.5,
                            properties={
                                "level": extra_level,
                                "parent_copybook": name,
                                "anomaly": True,
                            },
                        )
                    )
                continue
            level = int(m.group("level"))
            field_name = m.group("name")
            pic_m = _PIC_RE.search(stmt)
            pic = pic_m.group("pic") if pic_m else None
            redef_m = _REDEFINES_RE.search(stmt)
            redef = redef_m.group(1) if redef_m else None
            occ_m = _OCCURS_RE.search(stmt)
            occurs = occ_m.group(1) if occ_m else None

            confidence = 1.0
            if pic is not None and not _PIC_VALID_RE.match(pic):
                anomalies.append(f"malformed PIC on field {field_name}: {pic}")
                confidence = 0.5

            props: dict[str, object] = {
                "level": level,
                "parent_copybook": name,
            }
            if pic is not None:
                props["pic"] = pic
            if redef is not None:
                props["redefines"] = redef
            if occurs is not None:
                props["occurs"] = int(occurs)
            cond_names = _collect_88_levels(expanded, field_name)
            if cond_names:
                props["condition_names"] = cond_names

            nodes.append(
                Node(
                    id=make_node_id("Field", codebase_id, f"{name}.{field_name}"),
                    type=NodeType.FIELD,
                    name=field_name,
                    codebase_id=codebase_id,
                    content_hash=content_hash(stmt),
                    parse_confidence=confidence,
                    properties=props,
                )
            )

        if anomalies:
            program_node.parse_confidence = 0.5
            program_node.properties["anomalies"] = anomalies

        units.append(
            LogicalUnit(
                kind="copybook",
                name=name,
                source=expanded,
                content_hash=content_hash(expanded),
                properties={"replacing_applied": bool(replaced)},
                post_expansion=bool(replaced),
            )
        )
        return ExtractionResult(
            artifact_type=self.artifact_type,
            source_file=str(file_path),
            nodes=nodes,
            edges=edges,
            units=units,
        )


def _collect_88_levels(expanded_text: str, parent_field: str) -> list[str]:
    """Collect 88-level condition names that follow `parent_field` declaration."""
    found: list[str] = []
    pattern = re.compile(
        rf"{re.escape(parent_field)}\b.*?\.((?:\s*88\s+[A-Z0-9-]+\s+[^\.]*\.)+)",
        re.DOTALL,
    )
    block = pattern.search(expanded_text)
    if not block:
        return found
    for cm in re.finditer(r"88\s+([A-Z0-9-]+)", block.group(1)):
        found.append(cm.group(1))
    return found


def _content_area(line: str) -> str:
    if len(line) >= 7 and line[6] in ("*", "/"):
        return ""
    if len(line) >= 7 and line[6] not in (" ", "-"):
        return line[:72].rstrip()
    return line[7:72].rstrip() if len(line) > 7 else line.rstrip()


__all__ = ["CopybookExtractor", "expand_copybook"]