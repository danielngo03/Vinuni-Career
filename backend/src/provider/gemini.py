"""Gemini provider implementation."""

from __future__ import annotations

from backend.src.provider.base import LLMProviderConfig


class GeminiProvider:
    def __init__(self, config: LLMProviderConfig):
        self.config = config

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def model(self) -> str:
        return self.config.model

    @property
    def is_configured(self) -> bool:
        return bool(self.config.api_key)

    def generate(self, prompt: str) -> str:
        try:
            from google import genai
        except ImportError as exc:
            raise RuntimeError("Install google-genai to use Gemini parsing.") from exc

        client = genai.Client(api_key=self.config.api_key)
        try:
            try:
                from google.genai import types

                response = client.models.generate_content(
                    model=self.config.model,
                    contents=prompt,
                    config=types.GenerateContentConfig(temperature=self.config.temperature),
                )
            except (ImportError, AttributeError, TypeError):
                response = client.models.generate_content(model=self.config.model, contents=prompt)
        finally:
            close = getattr(client, "close", None)
            if callable(close):
                close()

        text = getattr(response, "text", "")
        if not text:
            raise ValueError("Gemini returned an empty response.")
        return text
