"""CICS control-flow extractor — deferred scope (section 5.10).

XCTL/LINK/RETURN chains, COMMAREA state handoff, TSQ/TDQ usage — how
pseudo-conversational programs hand off state. The `XCTLS` edge type is
already reserved in schema v1.1.
"""
from __future__ import annotations

from pathlib import Path

from mainframe_brain.extractors.base import ExtractionResult


class CICSControlFlowExtractor:
    artifact_type = "cics_control_flow"

    def can_handle(self, file_path: Path) -> bool:
        return False

    def extract(self, file_path: Path, codebase_id: str = "default") -> ExtractionResult:
        return ExtractionResult(artifact_type=self.artifact_type, source_file=str(file_path))


__all__ = ["CICSControlFlowExtractor"]