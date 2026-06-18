from __future__ import annotations

from typing import Protocol

from app.ai.gateway.schemas import (
    ChatRequest,
    ChatResponse,
    EmbeddingResponse,
    RerankRequest,
    RerankResponse,
)


class LLMProvider(Protocol):
    name: str

    def chat(self, request: ChatRequest) -> ChatResponse: ...

    def embed(self, text: str, *, model: str | None = None) -> EmbeddingResponse: ...

    def rerank(self, request: RerankRequest) -> RerankResponse: ...
