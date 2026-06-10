"""Shared provider interface."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class LLMProviderConfig:
    name: str
    model: str
    temperature: float = 0.0
    api_key: str | None = None
    base_url: str | None = None
    site_url: str | None = None
    app_name: str | None = None


class LLMProvider(Protocol):
    config: LLMProviderConfig

    @property
    def name(self) -> str:
        ...

    @property
    def model(self) -> str:
        ...

    @property
    def is_configured(self) -> bool:
        ...

    def generate(self, prompt: str) -> str:
        ...
