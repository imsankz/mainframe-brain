"""Deterministic mock adapter for tests and offline demos. No external deps."""
from __future__ import annotations

import json

from .base import LLMAdapter


class MockAdapter(LLMAdapter):
    @property
    def name(self) -> str:
        return "mock-v1"

    @property
    def provider(self) -> str:
        return "mock"

    def complete(self, system: str, user: str, max_tokens: int = 1024) -> tuple[str, dict]:
        name = user.strip().split("\n")[0][:60] if user else "unknown paragraph"
        payload = {
            "rule": f"Business rule for {name}: performs standard data processing with conditional branching.",
            "confidence": 0.5,
            "line_range": [1, max(1, user.count("\n") + 1)],
            "edge_cases": ["Review edge case around date boundary crossing"],
        }
        text = json.dumps(payload)
        return text, {
            "input_tokens": len(system) // 4 + len(user) // 4 + 10,
            "output_tokens": len(text) // 4 + 1,
            "model": "mock-v1",
        }


__all__ = ["MockAdapter"]