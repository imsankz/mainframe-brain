"""OpenAI adapter — lazily imported."""
from __future__ import annotations

from .base import LLMAdapter


class OpenAIAdapter(LLMAdapter):
    def __init__(self, api_key: str | None = None, model: str = "gpt-4o-mini"):
        self._api_key = api_key
        self._model = model

    @property
    def name(self) -> str:
        return self._model

    @property
    def provider(self) -> str:
        return "openai"

    def complete(self, system: str, user: str, max_tokens: int = 1024) -> tuple[str, dict]:
        try:
            import openai  # noqa: PLC0415
        except ImportError as e:
            raise RuntimeError("openai SDK not installed; pip install 'mainframe-brain[llm]'") from e

        client = openai.OpenAI(api_key=self._api_key)
        resp = client.chat.completions.create(
            model=self._model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        text = resp.choices[0].message.content or ""
        usage = resp.usage
        return text, {
            "input_tokens": getattr(usage, "prompt_tokens", 0),
            "output_tokens": getattr(usage, "completion_tokens", 0),
            "model": self._model,
        }


__all__ = ["OpenAIAdapter"]