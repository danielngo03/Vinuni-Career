from __future__ import annotations

import math
from uuid import uuid4

import httpx

from app.core.context import get_request_context
from app.infra.llm_gateway.errors import LLMProviderError, LLMProviderUnavailable
from app.infra.llm_gateway.schemas import ChatRequest, ChatResponse, EmbeddingResponse


class GeminiNativeProvider:
    name = "gemini"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None,
        chat_model: str,
        embedding_model: str,
        timeout_seconds: float,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.chat_model = chat_model
        self.embedding_model = embedding_model
        self.timeout_seconds = timeout_seconds

    def chat(self, request: ChatRequest) -> ChatResponse:
        self._ensure_available()
        model = request.model or self.chat_model
        body = self._chat_body(request)
        data = self._post(f"/models/{model}:generateContent", body)
        try:
            parts = data["candidates"][0]["content"].get("parts", [])
            content = "".join(part.get("text", "") for part in parts)
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMProviderError(self.name, "Unexpected generateContent response shape") from exc
        usage = data.get("usageMetadata") or {}
        return ChatResponse(
            content=content,
            provider=self.name,
            model=model,
            input_tokens=int(usage.get("promptTokenCount", 0) or 0),
            output_tokens=int(usage.get("candidatesTokenCount", 0) or 0),
            raw=data,
        )

    def embed(self, text: str, *, model: str | None = None) -> EmbeddingResponse:
        self._ensure_available()
        selected_model = model or self.embedding_model
        data = self._post(
            f"/models/{selected_model}:embedContent",
            {"content": {"parts": [{"text": text}]}},
        )
        try:
            values = data["embedding"]["values"]
        except (KeyError, TypeError) as exc:
            raise LLMProviderError(self.name, "Unexpected embedContent response shape") from exc
        return EmbeddingResponse(
            embedding=[float(value) for value in values],
            provider=self.name,
            model=selected_model,
            input_tokens=_estimate_tokens(text),
            raw=data,
        )

    def _chat_body(self, request: ChatRequest) -> dict:
        contents = []
        system_parts = []
        for message in request.messages:
            if message.role in {"system", "developer"}:
                system_parts.append({"text": message.content})
                continue
            role = "model" if message.role == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": message.content}]})

        body: dict = {
            "contents": contents,
            "generationConfig": {"temperature": request.temperature},
        }
        if request.max_tokens is not None:
            body["generationConfig"]["maxOutputTokens"] = request.max_tokens
        if system_parts:
            body["systemInstruction"] = {"parts": system_parts}
        if request.response_format:
            body["generationConfig"]["responseMimeType"] = "application/json"
        return body

    def _ensure_available(self) -> None:
        if not self.api_key:
            raise LLMProviderUnavailable("gemini API key is not configured")

    def _post(self, path: str, body: dict) -> dict:
        headers = {"Content-Type": "application/json", "X-Client-Request-Id": _request_id()}
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.post(
                    f"{self.base_url}{path}",
                    params={"key": self.api_key},
                    headers=headers,
                    json=body,
                )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:500]
            raise LLMProviderError(self.name, f"HTTP {exc.response.status_code}: {detail}") from exc
        except httpx.HTTPError as exc:
            raise LLMProviderError(self.name, str(exc)) from exc


def _estimate_tokens(text: str) -> int:
    return max(1, math.ceil(len(text) / 4))


def _request_id() -> str:
    context = get_request_context()
    return context.trace_id if context else str(uuid4())
