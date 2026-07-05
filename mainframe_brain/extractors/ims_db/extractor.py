"""IMS DB extractor — deferred scope (section 5.9). Hierarchical DB, DL/I calls, PCB/PSB."""
from __future__ import annotations

from pathlib import Path

from mainframe_brain.extractors.base import ExtractionResult


class IMSDBExtractor:
    artifact_type = "ims_db"

    def can_handle(self, file_path: Path) -> bool:
        return False

    def extract(self, file_path: Path, codebase_id: str = "default") -> ExtractionResult:
        return ExtractionResult(artifact_type=self.artifact_type, source_file=str(file_path))


__all__ = ["IMSDBExtractor"]