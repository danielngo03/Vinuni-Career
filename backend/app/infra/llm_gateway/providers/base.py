from __future__ import annotations

from typing import Protocol

from app.infra.llm_gateway.schemas import ChatRequest, ChatResponse, EmbeddingResponse


class LLMProvider(Protocol):
    name: str

    def chat(self, request: ChatRequest) -> ChatResponse: ...

    def embed(self, text: str, *, model: str | None = None) -> EmbeddingResponse: ...
