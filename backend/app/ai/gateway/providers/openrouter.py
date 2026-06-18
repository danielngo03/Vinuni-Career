from __future__ import annotations

from uuid import uuid4

import httpx

from app.ai.gateway.errors import LLMProviderError, LLMProviderUnavailable
from app.ai.gateway.schemas import (
    ChatRequest,
    ChatResponse,
    EmbeddingResponse,
    RerankRequest,
    RerankResponse,
    RerankResult,
)
from app.shared.context import get_request_context


class OpenRouterProvider:
    name = "openrouter"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None,
        chat_model: str,
        chat_model_fallbacks: list[str],
        embedding_model: str,
        rerank_model: str,
        http_referer: str | None,
        app_title: str,
        timeout_seconds: float,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.chat_model = chat_model
        self.chat_model_fallbacks = chat_model_fallbacks
        self.embedding_model = embedding_model
        self.rerank_model = rerank_model
        self.http_referer = http_referer
        self.app_title = app_title
        self.timeout_seconds = timeout_seconds

    def chat(self, request: ChatRequest) -> ChatResponse:
        self._ensure_available()
        model_candidates = _dedupe([request.model or self.chat_model, *self.chat_model_fallbacks])
        errors: list[str] = []
        for model in model_candidates:
            body = {
                "model": model,
                "messages": [
                    {"role": message.role, "content": message.content}
                    for message in request.messages
                ],
                "temperature": request.temperature,
            }
            if request.max_tokens is not None:
                body["max_tokens"] = request.max_tokens
            if request.response_format is not None:
                body["response_format"] = request.response_format
            try:
                data = self._post("/chat/completions", body)
                content = data["choices"][0]["message"].get("content") or ""
                usage = data.get("usage") or {}
                return ChatResponse(
                    content=content,
                    provider=self.name,
                    model=data.get("model", model),
                    input_tokens=int(usage.get("prompt_tokens", 0) or 0),
                    output_tokens=int(usage.get("completion_tokens", 0) or 0),
                    raw=data,
                )
            except Exception as exc:  # noqa: BLE001 - tries next free model.
                errors.append(f"{model}: {exc}")
        raise LLMProviderError(self.name, "; ".join(errors) or "All OpenRouter models failed")

    def embed(self, text: str, *, model: str | None = None) -> EmbeddingResponse:
        self._ensure_available()
        selected_model = model or self.embedding_model
        data = self._post(
            "/embeddings",
            {"model": selected_model, "input": text, "encoding_format": "float"},
        )
        try:
            embedding = data["data"][0]["embedding"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMProviderError(self.name, "Unexpected embedding response shape") from exc
        usage = data.get("usage") or {}
        return EmbeddingResponse(
            embedding=[float(value) for value in embedding],
            provider=self.name,
            model=data.get("model", selected_model),
            input_tokens=int(usage.get("prompt_tokens", usage.get("total_tokens", 0)) or 0),
            raw=data,
        )

    def rerank(self, request: RerankRequest) -> RerankResponse:
        self._ensure_available()
        selected_model = request.model or self.rerank_model
        data = self._post(
            "/rerank",
            {
                "model": selected_model,
                "query": request.query,
                "documents": request.documents,
                "top_n": request.top_n,
            },
        )
        results = []
        for item in data.get("results") or []:
            index = int(item.get("index", 0))
            document = item.get("document") or {}
            text = document.get("text") if isinstance(document, dict) else None
            if text is None and 0 <= index < len(request.documents):
                text = request.documents[index]
            results.append(
                RerankResult(
                    index=index,
                    text=str(text or ""),
                    relevance_score=float(item.get("relevance_score", 0.0) or 0.0),
                )
            )
        usage = data.get("usage") or {}
        return RerankResponse(
            results=results,
            provider=self.name,
            model=data.get("model", selected_model),
            input_tokens=int(usage.get("total_tokens", 0) or 0),
            raw=data,
        )

    def _ensure_available(self) -> None:
        if not self.api_key:
            raise LLMProviderUnavailable("OpenRouter API key is not configured")

    def _post(self, path: str, body: dict) -> dict:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-Client-Request-Id": _request_id(),
            "X-OpenRouter-Title": self.app_title,
        }
        if self.http_referer:
            headers["HTTP-Referer"] = self.http_referer
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.post(f"{self.base_url}{path}", headers=headers, json=body)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:500]
            raise LLMProviderError(self.name, f"HTTP {exc.response.status_code}: {detail}") from exc
        except httpx.HTTPError as exc:
            raise LLMProviderError(self.name, str(exc)) from exc


def _request_id() -> str:
    context = get_request_context()
    return context.trace_id if context else str(uuid4())


def _dedupe(values: list[str | None]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result
