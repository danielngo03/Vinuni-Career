from __future__ import annotations

import hashlib
import math
import re
from collections import Counter

from app.ai.gateway.schemas import (
    ChatRequest,
    ChatResponse,
    EmbeddingResponse,
    RerankRequest,
    RerankResponse,
    RerankResult,
)


class OfflineProvider:
    name = "offline"

    def __init__(self, *, dimensions: int = 32) -> None:
        self.dimensions = dimensions

    def chat(self, request: ChatRequest) -> ChatResponse:
        last_user = next(
            (message.content for message in reversed(request.messages) if message.role == "user"),
            "",
        )
        content = (
            "Offline fallback response. Configure OPENROUTER_API_KEY, OPENAI_API_KEY, or "
            "GEMINI_API_KEY to enable a real model. Input summary: "
            f"{last_user[:240]}"
        )
        input_text = "\n".join(message.content for message in request.messages)
        return ChatResponse(
            content=content,
            provider=self.name,
            model=request.model or "offline-deterministic",
            input_tokens=_estimate_tokens(input_text),
            output_tokens=_estimate_tokens(content),
        )

    def embed(self, text: str, *, model: str | None = None) -> EmbeddingResponse:
        return EmbeddingResponse(
            embedding=_hash_embedding(text, self.dimensions),
            provider=self.name,
            model=model or "offline-hash-embedding",
            input_tokens=_estimate_tokens(text),
        )

    def rerank(self, request: RerankRequest) -> RerankResponse:
        query_embedding = _hash_embedding(request.query, self.dimensions)
        scored = []
        for index, document in enumerate(request.documents):
            doc_embedding = _hash_embedding(document, self.dimensions)
            score = sum(a * b for a, b in zip(query_embedding, doc_embedding, strict=True))
            scored.append(
                RerankResult(
                    index=index,
                    text=document,
                    relevance_score=round(float(score), 6),
                )
            )
        scored.sort(key=lambda item: item.relevance_score, reverse=True)
        return RerankResponse(
            results=scored[: request.top_n],
            provider=self.name,
            model=request.model or "offline-hash-rerank",
            input_tokens=_estimate_tokens(request.query + "\n".join(request.documents)),
        )


def _estimate_tokens(text: str) -> int:
    return max(1, math.ceil(len(text) / 4))


def _hash_embedding(text: str, dimensions: int) -> list[float]:
    buckets = [0.0] * dimensions
    words = re.findall(r"[a-zA-Z0-9+#.]+", text.lower())
    for word, count in Counter(words).items():
        digest = hashlib.sha256(word.encode("utf-8")).digest()
        buckets[digest[0] % dimensions] += 1.0 + math.log(count)
    norm = math.sqrt(sum(value * value for value in buckets)) or 1.0
    return [round(value / norm, 6) for value in buckets]
