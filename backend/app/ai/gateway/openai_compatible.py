"""OpenAI-compatible provider adapter (OpenRouter / OpenAI / Ollama / Azure / etc.).

Supports multi-provider routing: the factory creates an ``OpenAICompatibleProvider``
instance pointed at the right base_url for the alias, and passes the model_id
via ``model_override`` so the adapter doesn't need to do its own alias resolution.

Legacy aliases still resolve via ``_BUILTIN_MODEL_MAP`` for backward compat with
tests and code paths that construct the provider directly. All new aliases added
via the admin UI route through the factory's ``provider_routes`` mechanism instead.

SECRECY: provider names, model ids, API keys, base URLs, and token counts are NEVER
exposed to end users (``docs/SECURITY_PRIVACY.md`` AI Safety). Output guard scrubs
any accidental leakage.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator

import httpx

from app.ai.gateway.base import AICompletion, AIEmbedding, AIMessage, AIProvider
from app.core.config import get_settings
from app.shared.exceptions import AIUnavailableError

# Internal legacy alias → model id map.
# Used as fallback when no model_override is supplied to the provider instance.
# New aliases are added via the DB-backed provider registry and do NOT need to
# appear here.
_BUILTIN_MODEL_MAP: dict[str, str] = {
    "chat_cheap": "deepseek/deepseek-chat",
    "reasoning_cheap": "deepseek/deepseek-r1",
    "reasoning_local": "llama3.2",
    "eval_cheap": "deepseek/deepseek-chat",
    "eval_local": "llama3.2",
    "chat_free": "deepseek/deepseek-chat",
    "chat_mini": "meta-llama/llama-3.1-8b-instruct",
    "embedding_cheap": "text-embedding-3-small",
    "rerank_cheap": "deepseek/deepseek-chat",
    # OpenAI-direct built-ins (used when OPENAI_API_KEY is set)
    "chat_openai_fast": "gpt-4o-mini",
    "chat_openai_best": "gpt-4o",
    "embedding_openai": "text-embedding-3-small",
    "rerank_openai_fast": "gpt-4o-mini",
    # Local Ollama built-ins (used when Ollama is running)
    "chat_local": "llama3.2",
    "chat_local_large": "llama3.1:70b",
    "embedding_local": "nomic-embed-text",
    "rerank_local": "llama3.2",
}

# Keep _ALIAS_MODEL_MAP as an alias for backward compat with tests.
_ALIAS_MODEL_MAP = _BUILTIN_MODEL_MAP


def resolve_model(alias: str) -> str:
    """Resolve an alias to a concrete model id (internal use only).

    For aliases added via the admin UI, the factory passes ``model_override``
    directly and this function is NOT called. This is the fallback for the
    built-in map.
    """

    if alias not in _BUILTIN_MODEL_MAP:
        raise AIUnavailableError()
    return _BUILTIN_MODEL_MAP[alias]


def known_aliases() -> frozenset[str]:
    """Return all resolvable alias names (built-in + published routes).

    The ``ai_settings`` allowlist validates admin selections against this set.
    Never exposes concrete model ids.
    """
    # Include aliases from the published runtime snapshot (DB-backed custom aliases)
    try:
        from app.ai.gateway import runtime_config
        route_aliases = frozenset(runtime_config.current().provider_routes.keys())
    except Exception:
        route_aliases = frozenset()
    return frozenset(_BUILTIN_MODEL_MAP) | route_aliases


class OpenAICompatibleProvider(AIProvider):
    """Calls an OpenAI-compatible ``/chat/completions`` endpoint.

    When ``model_override`` is supplied (set by the multi-provider factory),
    it takes precedence over alias resolution — enabling admin-configured
    aliases that are not in the built-in map.
    """

    name = "openai_compatible"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout: float = 30.0,
        model_override: str | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        self._model_override = model_override

    async def complete(
        self,
        messages: list[AIMessage],
        *,
        alias: str,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> AICompletion:
        settings = get_settings()
        if not settings.ai_real_calls_enabled:
            raise AIUnavailableError()

        model = self._model_override or resolve_model(alias)
        payload = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "HTTP-Referer": "https://career.vinuni.edu.vn",
            "X-Title": "VinUni Career Platform",
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self._base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise AIUnavailableError() from exc

        choice = (data.get("choices") or [{}])[0]
        text = (choice.get("message") or {}).get("content", "")
        usage = data.get("usage", {})
        return AICompletion(
            text=text,
            model_alias=alias,
            usage={
                "prompt_tokens": int(usage.get("prompt_tokens", 0)),
                "completion_tokens": int(usage.get("completion_tokens", 0)),
            },
            finish_reason=choice.get("finish_reason", "stop"),
        )

    async def stream(
        self,
        messages: list[AIMessage],
        *,
        alias: str,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> AsyncGenerator[str, None]:
        """Stream completion tokens via the OpenAI SSE protocol (stream=true).

        Yields partial text chunks as they arrive. Falls back to a single-chunk
        yield if the provider doesn't send proper delta events.
        """
        settings = get_settings()
        if not settings.ai_real_calls_enabled:
            raise AIUnavailableError()

        model = self._model_override or resolve_model(alias)
        payload = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "HTTP-Referer": "https://career.vinuni.edu.vn",
            "X-Title": "VinUni Career Platform",
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                async with client.stream(
                    "POST",
                    f"{self._base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        line = line.strip()
                        if not line or not line.startswith("data:"):
                            continue
                        data_part = line[5:].strip()
                        if data_part == "[DONE]":
                            break
                        try:
                            obj = json.loads(data_part)
                            delta = (obj.get("choices") or [{}])[0].get("delta", {})
                            chunk = delta.get("content")
                            if chunk:
                                yield chunk
                        except (json.JSONDecodeError, IndexError, KeyError):
                            continue
        except (httpx.HTTPError, ValueError) as exc:
            raise AIUnavailableError() from exc

    async def embed(
        self,
        texts: list[str],
        *,
        alias: str,
    ) -> list[AIEmbedding]:
        """Batch-embed ``texts`` using the OpenAI-compatible embeddings endpoint."""

        settings = get_settings()
        if not settings.ai_real_calls_enabled:
            raise AIUnavailableError()

        model = self._model_override or resolve_model(alias)
        payload: dict = {"model": model, "input": texts}
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "HTTP-Referer": "https://career.vinuni.edu.vn",
            "X-Title": "VinUni Career Platform",
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self._base_url}/embeddings",
                    json=payload,
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise AIUnavailableError() from exc

        raw_data: list[dict] = sorted(
            data.get("data", []), key=lambda d: d.get("index", 0)
        )
        usage = data.get("usage", {})
        return [
            AIEmbedding(
                vector=item.get("embedding", []),
                model_alias=alias,
                usage={
                    "prompt_tokens": int(usage.get("prompt_tokens", 0)),
                    "total_tokens": int(usage.get("total_tokens", 0)),
                },
            )
            for item in raw_data
        ]
