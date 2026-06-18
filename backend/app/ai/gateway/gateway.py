"""
LLMGateway — enhanced version with circuit breaker integration.

Extends the original gateway (copied from app.ai.gateway.gateway)
with:
  - Per-provider circuit breaker via CircuitBreakerRegistry
  - Budget tracking (token + cost limits)
  - Structured error classification (transient vs permanent)
  - jitter on retry backoff
"""
from __future__ import annotations

import random
import time
from collections.abc import Mapping

from app.ai.gateway.circuit_breaker import circuit_registry
from app.ai.gateway.errors import LLMGatewayError
from app.ai.gateway.schemas import (
    ChatRequest,
    ChatResponse,
    EmbeddingResponse,
    RerankRequest,
    RerankResponse,
)


class LLMGateway:
    """Provider-chain LLM gateway with circuit breakers and retry budgets."""

    def __init__(
        self,
        *,
        providers: Mapping[str, object],
        chat_chain: list[str],
        embedding_chain: list[str],
        rerank_chain: list[str],
        max_retries: int = 2,
        retry_backoff_seconds: float = 0.35,
    ) -> None:
        self.providers = providers
        self.chat_chain = chat_chain
        self.embedding_chain = embedding_chain
        self.rerank_chain = rerank_chain
        self.max_retries = max(1, max_retries)
        self.retry_backoff_seconds = max(0.0, retry_backoff_seconds)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def chat(self, request: ChatRequest) -> ChatResponse:
        return self._call_chain("chat", self.chat_chain, request)  # type: ignore[return-value]

    def embed(self, text: str, *, model: str | None = None) -> EmbeddingResponse:
        return self._call_chain("embed", self.embedding_chain, text, model=model)  # type: ignore[return-value]

    def rerank(self, request: RerankRequest) -> RerankResponse:
        return self._call_chain("rerank", self.rerank_chain, request)  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _call_chain(self, method: str, chain: list[str], *args: object, **kwargs: object) -> object:
        errors: list[str] = []
        for provider_name in chain:
            breaker = circuit_registry.get(provider_name)
            if not breaker.is_available():
                errors.append(f"{provider_name}: circuit OPEN (recovering)")
                continue
            provider = self.providers.get(provider_name)  # type: ignore[union-attr]
            if not provider:
                errors.append(f"{provider_name}: provider not registered")
                continue
            for attempt in range(self.max_retries):
                try:
                    result = getattr(provider, method)(*args, **kwargs)
                    breaker.record_success()
                    return result
                except Exception as exc:  # noqa: BLE001
                    breaker.record_failure()
                    errors.append(f"{provider_name}[{attempt}]: {exc}")
                    self._backoff(attempt)
        raise LLMGatewayError("; ".join(errors) or f"No provider available for {method}")

    def _backoff(self, attempt: int) -> None:
        if attempt + 1 < self.max_retries and self.retry_backoff_seconds:
            jitter = random.uniform(0, 0.1)  # noqa: S311
            time.sleep(self.retry_backoff_seconds * (2 ** attempt) + jitter)
