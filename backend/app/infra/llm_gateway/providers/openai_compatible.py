from __future__ import annotations

from uuid import uuid4

import httpx

from app.core.context import get_request_context
from app.infra.llm_gateway.errors import LLMProviderError, LLMProviderUnavailable
from app.infra.llm_gateway.schemas import ChatRequest, ChatResponse, EmbeddingResponse


class OpenAICompatibleProvider:
    def __init__(
        self,
        *,
        name: str,
        base_url: str,
        api_key: str | None,
        chat_model: str,
        embedding_model: str,
        timeout_seconds: float,
    ) -> None:
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.chat_model = chat_model
        self.embedding_model = embedding_model
        self.timeout_seconds = timeout_seconds

    def chat(self, request: ChatRequest) -> ChatResponse:
        self._ensure_available()
        model = request.model or self.chat_model
        body = {
            "model": model,
            "messages": [
                {"role": message.role, "content": message.content} for message in request.messages
            ],
            "temperature": request.temperature,
        }
        if request.max_tokens is not None:
            body["max_tokens"] = request.max_tokens
        if request.response_format is not None:
            body["response_format"] = request.response_format

        data = self._post("/chat/completions", body)
        try:
            content = data["choices"][0]["message"].get("content") or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMProviderError(self.name, "Unexpected chat response shape") from exc
        usage = data.get("usage") or {}
        return ChatResponse(
            content=content,
            provider=self.name,
            model=data.get("model", model),
            input_tokens=int(usage.get("prompt_tokens", 0) or 0),
            output_tokens=int(usage.get("completion_tokens", 0) or 0),
            raw=data,
        )

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

    def _ensure_available(self) -> None:
        if self.name in {"openai", "gemini"} and not self.api_key:
            raise LLMProviderUnavailable(f"{self.name} API key is not configured")

    def _post(self, path: str, body: dict) -> dict:
        headers = {"Content-Type": "application/json", "X-Client-Request-Id": _request_id()}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
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
