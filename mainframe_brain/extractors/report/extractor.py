"""Report / SYSOUT extractor — schema-ready stub (deferred scope, section 5.8).

Auto-naming from JCL SYSOUT ships with Phase 2. Out-of-scope for MVP pipeline
wiring but registered so the schema reservation is concrete.
"""
from __future__ import annotations

from pathlib import Path

from mainframe_brain.extractors.base import ExtractionResult


class ReportExtractor:
    artifact_type = "report"

    def can_handle(self, file_path: Path) -> bool:
        return False

    def extract(self, file_path: Path, codebase_id: str = "default") -> ExtractionResult:
        return ExtractionResult(artifact_type=self.artifact_type, source_file=str(file_path))


__all__ = ["ReportExtractor"]