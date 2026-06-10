"""OpenAI-compatible chat completions provider."""

from __future__ import annotations

import json
from urllib import request

from backend.src.provider.base import LLMProviderConfig


class OpenAICompatibleProvider:
    def __init__(self, config: LLMProviderConfig, extra_headers: dict[str, str] | None = None):
        self.config = config
        self.extra_headers = extra_headers or {}

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def model(self) -> str:
        return self.config.model

    @property
    def is_configured(self) -> bool:
        return bool(self.config.api_key and self.config.base_url)

    def generate(self, prompt: str) -> str:
        if not self.config.base_url:
            raise ValueError(f"{self.name} base URL is not configured.")
        if not self.config.api_key:
            raise ValueError(f"{self.name} API key is not configured.")

        payload = {
            "model": self.config.model,
            "temperature": self.config.temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.config.api_key}",
            **self.extra_headers,
        }
        url = f"{self.config.base_url.rstrip('/')}/chat/completions"
        req = request.Request(url, data=body, headers=headers, method="POST")

        with request.urlopen(req, timeout=60) as response:
            response_data = json.loads(response.read().decode("utf-8"))

        try:
            content = response_data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError(f"{self.name} did not return chat completion content.") from exc
        if not content:
            raise ValueError(f"{self.name} returned an empty response.")
        return str(content)
