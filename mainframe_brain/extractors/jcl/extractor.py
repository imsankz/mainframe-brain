from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from mainframe_brain.extractors.base import (
    ExtractionResult,
    LogicalUnit,
    content_hash,
)
from mainframe_brain.graph.schema import Edge, EdgeType, Node, NodeType
from mainframe_brain.graph.store import make_node_id

_VERBS = {
    "JOB",
    "EXEC",
    "DD",
    "IF",
    "THEN",
    "ELSE",
    "ENDIF",
    "OUTPUT",
    "JCLLIB",
    "INCLUDE",
    "SET",
    "COMMAND",
    "PROC",
    "PEND",
}

_DSN_RE = re.compile(r"\bDSN\s*=\s*'?([^',\s()]+)'?", re.IGNORECASE)
_DISP_RE = re.compile(
    r"\bDISP\s*=\s*\(?\s*([A-Za-z]+)\s*(?:,([A-Za-z]+))?\s*(?:,([A-Za-z]+))?",
    re.IGNORECASE,
)
_PGM_RE = re.compile(r"\bPGM\s*=\s*'?([^',\s()]+)'?", re.IGNORECASE)
_PROC_RE = re.compile(r"\bPROC\s*=\s*'?([^',\s()]+)'?", re.IGNORECASE)
_COND_RE = re.compile(r"\bCOND\s*=\s*\(([^)]*)\)", re.IGNORECASE)
_CLASS_RE = re.compile(r"\bCLASS\s*=\s*'?(\w+)'?", re.IGNORECASE)
_MSGCLASS_RE = re.compile(r"\bMSGCLASS\s*=\s*'(\w+)'?", re.IGNORECASE)
_MSGCLASS_BARE_RE = re.compile(r"\bMSGCLASS\s*=\s*(\w+)", re.IGNORECASE)
_RESTART_RE = re.compile(r"\bRESTART\s*=\s*'?([\w.\-]+)'?", re.IGNORECASE)
_SYSOUT_RE = re.compile(r"\bSYSOUT\s*=\s*'?(\w+)'?", re.IGNORECASE)
_HEADER_RE = re.compile(
    r"\s*([A-Z0-9$#@.\-]*)\s*([A-Z]*)\s*(.*)$",
    re.IGNORECASE,
)


def _operands_open(text: str) -> bool:
    stripped = text.rstrip()
    if not stripped:
        return False
    if stripped.endswith(","):
        return True
    depth = 0
    for ch in stripped:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
    return depth > 0


def _msgclass(operands: str) -> str:
    m = _MSGCLASS_RE.search(operands) or _MSGCLASS_BARE_RE.search(operands)
    return m.group(1) if m else ""


def _accounting(operands: str) -> str:
    positional: list[str] = []
    depth = 0
    cur = ""
    for ch in operands:
        if ch == "(":
            depth += 1
            cur += ch
        elif ch == ")":
            depth -= 1
            cur += ch
        elif ch == "," and depth == 0:
            token = cur.strip()
            cur = ""
            if not token:
                continue
            if "=" in token:
                break
            positional.append(token)
        else:
            cur += ch
    tail = cur.strip()
    if tail and "=" not in tail:
        positional.append(tail)
    return ",".join(positional)


def _disp_status(operands: str) -> dict[str, str]:
    m = _DISP_RE.search(operands)
    if not m:
        return {"status": "", "normal": "", "abnormal": ""}
    return {
        "status": (m.group(1) or "").upper(),
        "normal": (m.group(2) or "").upper(),
        "abnormal": (m.group(3) or "").upper(),
    }


def _parse_header(content: str, line: str) -> dict[str, Any]:
    m = _HEADER_RE.match(content)
    if not m:
        return {
            "name": "",
            "verb": "",
            "operands": "",
            "_lines": [line],
            "_instream": False,
            "_instream_data": [],
            "_anomaly": True,
            "_closed": True,
        }
    name = (m.group(1) or "").strip()
    verb = (m.group(2) or "").upper()
    operands = (m.group(3) or "").strip()
    anomaly = False
    if not verb or verb not in _VERBS:
        anomaly = True
    up = operands.upper()
    instream = verb == "DD" and (
        operands.startswith("*")
        or up == "DATA"
        or up.startswith("DATA,")
        or up.startswith("DATA ")
        or up == "DUMMY"
    )
    closed = instream or not _operands_open(operands)
    return {
        "name": name,
        "verb": verb,
        "operands": operands,
        "_lines": [line],
        "_instream": instream,
        "_instream_data": [],
        "_anomaly": anomaly,
        "_closed": closed,
    }


def _tokenize(raw: str) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    cur: dict[str, Any] | None = None
    for line in raw.splitlines():
        if line.startswith("//*"):
            continue
        if line.startswith("/*") or line.strip() == "//":
            if cur is not None:
                cards.append(cur)
                cur = None
            continue
        if not line.startswith("//"):
            if cur is not None:
                cur["_lines"].append(line)
                if cur.get("_instream"):
                    cur["_instream_data"].append(line)
            continue
        content = line[2:]
        if cur is not None:
            if cur.get("_instream"):
                cards.append(cur)
                cur = None
            elif not cur.get("_closed") and _operands_open(cur["operands"]):
                cur["operands"] = (cur["operands"] + content).rstrip()
                cur["_lines"].append(line)
                if not _operands_open(cur["operands"]):
                    cur["_closed"] = True
                continue
            else:
                cards.append(cur)
                cur = None
        cur = _parse_header(content, line)
    if cur is not None:
        cards.append(cur)
    return cards


class JCLExtractor:
    artifact_type = "jcl"

    def can_handle(self, file_path: Path) -> bool:
        return file_path.suffix.lower() in (".jcl",)

    def extract(self, file_path: Path, codebase_id: str = "default") -> ExtractionResult:
        raw = file_path.read_text(encoding="utf-8", errors="replace")
        cards = _tokenize(raw)
        result = ExtractionResult(
            artifact_type=self.artifact_type,
            source_file=str(file_path),
        )

        emitted_datasets: dict[str, Node] = {}
        current_step: Node | None = None
        step_lines: list[str] = []

        def flush_step() -> None:
            nonlocal current_step, step_lines
            if current_step is None:
                current_step = None
                step_lines = []
                return
            source = "\n".join(step_lines)
            ch = content_hash(source)
            current_step.content_hash = ch
            result.units.append(
                LogicalUnit(
                    kind="job_step",
                    name=current_step.name,
                    source=source,
                    content_hash=ch,
                    properties={"step_id": current_step.id},
                )
            )
            current_step = None
            step_lines = []

        def dataset_node(dsname: str) -> Node:
            node_id = make_node_id("Dataset", codebase_id, dsname)
            if node_id in emitted_datasets:
                return emitted_datasets[node_id]
            node = Node(
                id=node_id,
                type=NodeType.DATASET,
                name=dsname,
                codebase_id=codebase_id,
                content_hash="",
                properties={"dds": []},
            )
            emitted_datasets[node_id] = node
            result.nodes.append(node)
            return node

        for card in cards:
            if card.get("_anomaly"):
                anom = Node(
                    id=make_node_id(
                        "JCLStep", codebase_id, card["name"] or "ANOMALY"
                    ),
                    type=NodeType.JCL_STEP,
                    name=card["name"] or "ANOMALY",
                    codebase_id=codebase_id,
                    content_hash=content_hash("\n".join(card["_lines"])),
                    parse_confidence=0.5,
                    properties={
                        "anomaly": True,
                        "verb": card["verb"],
                        "operands": card["operands"],
                    },
                )
                result.nodes.append(anom)
                continue

            verb = card["verb"]
            operands = card["operands"]

            if verb == "JOB":
                flush_step()
                jobname = card["name"] or "UNKNOWN"
                cond_m = _COND_RE.search(operands)
                job = Node(
                    id=make_node_id("JCLJob", codebase_id, jobname),
                    type=NodeType.JCL_JOB,
                    name=jobname,
                    codebase_id=codebase_id,
                    content_hash=content_hash("\n".join(card["_lines"])),
                    properties={
                        "accounting": _accounting(operands),
                        "class": _CLASS_RE.search(operands).group(1)
                        if _CLASS_RE.search(operands)
                        else "",
                        "msgclass": _msgclass(operands),
                        "restart": _RESTART_RE.search(operands).group(1)
                        if _RESTART_RE.search(operands)
                        else "",
                        "cond": cond_m.group(1) if cond_m else "",
                    },
                )
                result.nodes.append(job)

            elif verb == "EXEC":
                flush_step()
                stepname = card["name"] or "ANONSTEP"
                pgm_m = _PGM_RE.search(operands)
                proc_m = _PROC_RE.search(operands)
                cond_m = _COND_RE.search(operands)
                program = pgm_m.group(1) if pgm_m else ""
                invoked_proc = proc_m.group(1) if proc_m else ""
                step = Node(
                    id=make_node_id("JCLStep", codebase_id, stepname),
                    type=NodeType.JCL_STEP,
                    name=stepname,
                    codebase_id=codebase_id,
                    content_hash="",
                    properties={
                        "exec_kind": "PROGRAM" if program else "PROC",
                        "program": program,
                        "proc": invoked_proc,
                        "cond": cond_m.group(1) if cond_m else "",
                        "sysouts": [],
                        "conditions": [],
                    },
                )
                result.nodes.append(step)
                current_step = step
                step_lines = list(card["_lines"])

            elif verb == "DD":
                if current_step is None:
                    continue
                step_lines.extend(card["_lines"])
                step_lines.extend(card["_instream_data"])
                sysout_m = _SYSOUT_RE.search(operands)
                if sysout_m:
                    current_step.properties["sysouts"].append(sysout_m.group(1))
                dsn_m = _DSN_RE.search(operands)
                if not dsn_m:
                    continue
                dsname = dsn_m.group(1)
                ds = dataset_node(dsname)
                ds.properties["dds"].append(card["name"])
                disp = _disp_status(operands)
                status = disp["status"]
                reads = status in ("SHR", "OLD")
                writes = status in ("NEW", "MOD")
                if status == "MOD" and "DELETE" in (disp["normal"], disp["abnormal"]):
                    reads = True
                if reads:
                    result.edges.append(
                        Edge(
                            src=current_step.id,
                            dst=ds.id,
                            type=EdgeType.READS,
                            properties={"disp": status},
                        )
                    )
                if writes:
                    result.edges.append(
                        Edge(
                            src=current_step.id,
                            dst=ds.id,
                            type=EdgeType.WRITES,
                            properties={"disp": status},
                        )
                    )

            elif verb in ("IF", "THEN", "ELSE", "ENDIF"):
                if current_step is not None:
                    cond_text = operands or verb
                    current_step.properties["conditions"].append(f"{verb}: {cond_text}")
                step_lines.extend(card["_lines"])

        flush_step()
        return result