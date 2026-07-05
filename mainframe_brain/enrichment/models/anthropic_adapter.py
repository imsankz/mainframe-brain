"""Anthropic adapter — lazily imported. Only loaded when selected via CLI."""
from __future__ import annotations

from .base import LLMAdapter


class AnthropicAdapter(LLMAdapter):
    def __init__(self, api_key: str | None = None, model: str = "claude-3-5-haiku-20241022"):
        self._api_key = api_key
        self._model = model

    @property
    def name(self) -> str:
        return self._model

    @property
    def provider(self) -> str:
        return "anthropic"

    def complete(self, system: str, user: str, max_tokens: int = 1024) -> tuple[str, dict]:
        try:
            import anthropic  # noqa: PLC0415
        except ImportError as e:
            raise RuntimeError("anthropic SDK not installed; pip install 'mainframe-brain[llm]'") from e

        client = anthropic.Anthropic(api_key=self._api_key)
        resp = client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(getattr(b, "text", "") for b in resp.content)
        return text, {
            "input_tokens": resp.usage.input_tokens,
            "output_tokens": resp.usage.output_tokens,
            "model": self._model,
        }


__all__ = ["AnthropicAdapter"]