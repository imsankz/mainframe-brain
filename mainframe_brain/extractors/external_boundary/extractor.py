"""External boundary extractor — schema-ready stub (deferred scope, section 5.7).

Captures outbound MQ Series, CICS web services, vendor calls so they are marked
rather than silently dropped. Ships when a real sample is available for a golden
fixture.
"""
from __future__ import annotations

from pathlib import Path

from mainframe_brain.extractors.base import ExtractionResult


class ExternalBoundaryExtractor:
    artifact_type = "external_boundary"

    def can_handle(self, file_path: Path) -> bool:
        return False

    def extract(self, file_path: Path, codebase_id: str = "default") -> ExtractionResult:
        return ExtractionResult(artifact_type=self.artifact_type, source_file=str(file_path))


__all__ = ["ExternalBoundaryExtractor"]