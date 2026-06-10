"""Ollama native provider implementation."""

from __future__ import annotations

import json
from urllib import request

from backend.src.provider.base import LLMProviderConfig


class OllamaProvider:
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
        return bool(self.config.base_url)

    def generate(self, prompt: str) -> str:
        if not self.config.base_url:
            raise ValueError("Ollama base URL is not configured.")

        payload = {
            "model": self.config.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": self.config.temperature},
        }
        body = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        url = f"{self.config.base_url.rstrip('/')}/api/generate"
        req = request.Request(url, data=body, headers=headers, method="POST")

        with request.urlopen(req, timeout=60) as response:
            response_data = json.loads(response.read().decode("utf-8"))

        content = response_data.get("response")
        if not content:
            raise ValueError("Ollama returned an empty response.")
        return str(content)
