from __future__ import annotations

from uuid import uuid4

import httpx

from app.ai.gateway.api_key_pool import APIKeyPool, looks_like_key_exhaustion
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


class OpenAICompatibleProvider:
    def __init__(
        self,
        *,
        name: str,
        base_url: str,
        api_key: str | None,
        api_keys: list[str] | None = None,
        chat_model: str,
        embedding_model: str | None,
        rerank_model: str | None = None,
        timeout_seconds: float,
    ) -> None:
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.api_key_pool = APIKeyPool([api_key, *(api_keys or [])])
        self.chat_model = chat_model
        self.embedding_model = embedding_model
        self.rerank_model = rerank_model
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
        if not selected_model:
            raise LLMProviderUnavailable(f"{self.name} embedding model is not configured")
        payload = {"model": selected_model, "input": [text], "encoding_format": "float"}
        if "embedqa" in selected_model.lower() or "nv-embed" in selected_model.lower():
            payload["input_type"] = "query"

        data = self._post("/embeddings", payload)
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
        if not self.rerank_model:
            raise LLMProviderUnavailable(f"{self.name} rerank model is not configured")

        selected_model = request.model or self.rerank_model

        url_path = "/ranking"
        if self.name == "nvidia" and "integrate.api.nvidia.com" in self.base_url:
            # NVIDIA hosted reranking uses a different base URL
            url_path = "https://ai.api.nvidia.com/v1/retrieval/nvidia/reranking"

        data = self._post(
            url_path,
            {
                "model": selected_model,
                "query": {"text": request.query},
                "passages": [{"text": doc} for doc in request.documents],
                "top_n": request.top_n,
            },
        )
        results = []
        for item in data.get("rankings") or []:
            index = int(item.get("index", 0))
            results.append(
                RerankResult(
                    index=index,
                    text=request.documents[index] if 0 <= index < len(request.documents) else "",
                    relevance_score=float(item.get("logit", 0.0) or 0.0),
                )
            )

        if request.top_n is not None:
            results = results[:request.top_n]

        usage = data.get("usage") or {}
        return RerankResponse(
            results=results,
            provider=self.name,
            model=data.get("model", selected_model),
            input_tokens=int(usage.get("total_tokens", 0) or 0),
            raw=data,
        )

    def _ensure_available(self) -> None:
        if self.name in {"openai", "gemini", "groq"} and not self.api_key_pool.has_available_key():
            raise LLMProviderUnavailable(
                f"{self.name} API key is not configured or all keys are quota exhausted"
            )

    def _post(self, path: str, body: dict) -> dict:
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        key_errors: list[str] = []
        api_keys = self.api_key_pool.claim_keys_for_request()
        if not api_keys and self.name not in {"openai", "gemini", "groq"}:
            api_keys = [self.api_key or ""]
        with httpx.Client(timeout=self.timeout_seconds) as client:
            for api_key in api_keys:
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "X-Client-Request-Id": _request_id(),
                }
                try:
                    response = client.post(url, headers=headers, json=body)
                    response.raise_for_status()
                    self.api_key_pool.record_success(api_key)
                    return response.json()
                except httpx.HTTPStatusError as exc:
                    detail = exc.response.text[:500]
                    if self.name == "gemini" and looks_like_key_exhaustion(
                        exc.response.status_code, detail
                    ):
                        self.api_key_pool.mark_exhausted(api_key)
                        key_errors.append(f"HTTP {exc.response.status_code}: {detail}")
                        continue
                    raise LLMProviderError(
                        self.name, f"HTTP {exc.response.status_code}: {detail}"
                    ) from exc
                except httpx.HTTPError as exc:
                    raise LLMProviderError(self.name, str(exc)) from exc
        if key_errors:
            raise LLMProviderUnavailable(
                f"{self.name} API keys are quota exhausted: " + "; ".join(key_errors)
            )
        raise LLMProviderUnavailable(f"{self.name} API key is not configured")


def _request_id() -> str:
    context = get_request_context()
    return context.trace_id if context else str(uuid4())
