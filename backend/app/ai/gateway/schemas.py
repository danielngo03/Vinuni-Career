from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Role = Literal["system", "developer", "user", "assistant"]


@dataclass(frozen=True)
class ChatMessage:
    role: Role
    content: str


@dataclass(frozen=True)
class ChatRequest:
    messages: list[ChatMessage]
    model: str | None = None
    temperature: float = 0.2
    max_tokens: int | None = None
    response_format: dict[str, Any] | None = None
    response_schema: dict[str, Any] | None = None
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ChatResponse:
    content: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EmbeddingResponse:
    embedding: list[float]
    provider: str
    model: str
    input_tokens: int
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RerankRequest:
    query: str
    documents: list[str]
    top_n: int = 5
    model: str | None = None


@dataclass(frozen=True)
class RerankResult:
    index: int
    text: str
    relevance_score: float


@dataclass(frozen=True)
class RerankResponse:
    results: list[RerankResult]
    provider: str
    model: str
    input_tokens: int = 0
    raw: dict[str, Any] = field(default_factory=dict)
