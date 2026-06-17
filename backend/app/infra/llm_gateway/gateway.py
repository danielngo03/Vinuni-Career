from __future__ import annotations

from collections.abc import Mapping

from app.infra.llm_gateway.errors import LLMGatewayError
from app.infra.llm_gateway.providers.base import LLMProvider
from app.infra.llm_gateway.schemas import ChatRequest, ChatResponse, EmbeddingResponse


class LLMGateway:
    def __init__(
        self,
        *,
        providers: Mapping[str, LLMProvider],
        chat_chain: list[str],
        embedding_chain: list[str],
        max_retries: int,
    ) -> None:
        self.providers = providers
        self.chat_chain = chat_chain
        self.embedding_chain = embedding_chain
        self.max_retries = max(1, max_retries)

    def chat(self, request: ChatRequest) -> ChatResponse:
        errors: list[str] = []
        for provider_name in self.chat_chain:
            provider = self.providers.get(provider_name)
            if not provider:
                errors.append(f"{provider_name}: provider is not registered")
                continue
            for _ in range(self.max_retries):
                try:
                    return provider.chat(request)
                except Exception as exc:  # noqa: BLE001 - gateway records provider failures.
                    errors.append(str(exc))
        raise LLMGatewayError("; ".join(errors) or "No LLM provider configured")

    def embed(self, text: str, *, model: str | None = None) -> EmbeddingResponse:
        errors: list[str] = []
        for provider_name in self.embedding_chain:
            provider = self.providers.get(provider_name)
            if not provider:
                errors.append(f"{provider_name}: provider is not registered")
                continue
            for _ in range(self.max_retries):
                try:
                    return provider.embed(text, model=model)
                except Exception as exc:  # noqa: BLE001 - gateway records provider failures.
                    errors.append(str(exc))
        raise LLMGatewayError("; ".join(errors) or "No embedding provider configured")
