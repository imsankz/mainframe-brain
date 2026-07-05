"""IMS DC extractor — deferred scope (section 5.9). IMS TM message processing."""
from __future__ import annotations

from pathlib import Path

from mainframe_brain.extractors.base import ExtractionResult


class IMSDCExtractor:
    artifact_type = "ims_dc"

    def can_handle(self, file_path: Path) -> bool:
        return False

    def extract(self, file_path: Path, codebase_id: str = "default") -> ExtractionResult:
        return ExtractionResult(artifact_type=self.artifact_type, source_file=str(file_path))


__all__ = ["IMSDCExtractor"]