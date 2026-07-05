"""Abstract LLM adapter — model-agnostic. New provider = new module here."""
from __future__ import annotations

from abc import ABC, abstractmethod


class LLMAdapter(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def provider(self) -> str: ...

    @abstractmethod
    def complete(self, system: str, user: str, max_tokens: int = 1024) -> tuple[str, dict]:
        """Return (text, usage) where usage = {input_tokens, output_tokens, model}."""
        ...


__all__ = ["LLMAdapter"]