from __future__ import annotations

import httpx
import pytest

from app.ai.gateway.errors import LLMProviderUnavailable
from app.ai.gateway.providers.gemini_native import GeminiNativeProvider
from app.ai.gateway.schemas import ChatMessage, ChatRequest


def test_chat_body_uses_json_schema_field_for_structured_output():
    provider = GeminiNativeProvider(
        base_url="https://example.test",
        api_key="test-key",
        chat_model="test-model",
        embedding_model="test-embedding",
        timeout_seconds=1,
    )
    schema = {
        "$defs": {
            "Nested": {
                "properties": {"value": {"type": "string"}},
                "required": ["value"],
                "type": "object",
            }
        },
        "properties": {"nested": {"$ref": "#/$defs/Nested"}},
        "required": ["nested"],
        "type": "object",
    }

    body = provider._chat_body(
        ChatRequest(
            messages=[ChatMessage(role="user", content="Return structured data")],
            response_format={"type": "json_schema"},
            response_schema=schema,
        )
    )

    generation_config = body["generationConfig"]
    assert generation_config["responseMimeType"] == "application/json"
    assert generation_config["responseJsonSchema"] == schema
    assert "responseSchema" not in generation_config


def test_gemini_native_provider_rotates_to_next_key_after_quota(monkeypatch):
    requests = []

    class StubClient:
        def __init__(self, timeout: float) -> None:
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def post(self, url: str, *, params: dict, headers: dict, json: dict):
            requests.append(params["key"])
            request = httpx.Request("POST", url)
            if params["key"] == "key-1":
                return httpx.Response(
                    429,
                    request=request,
                    text='{"error":{"status":"RESOURCE_EXHAUSTED","message":"quota exceeded"}}',
                )
            return httpx.Response(
                200,
                request=request,
                json={
                    "candidates": [{"content": {"parts": [{"text": "ok"}]}}],
                    "usageMetadata": {"promptTokenCount": 1, "candidatesTokenCount": 1},
                },
            )

    monkeypatch.setattr(httpx, "Client", StubClient)
    provider = GeminiNativeProvider(
        base_url="https://example.test",
        api_key="key-1",
        api_keys=["key-2"],
        chat_model="test-model",
        embedding_model="test-embedding",
        timeout_seconds=1,
    )

    response = provider.chat(ChatRequest(messages=[ChatMessage(role="user", content="hello")]))

    assert response.content == "ok"
    assert requests == ["key-1", "key-2"]


def test_gemini_native_provider_rotates_to_next_key_after_auth_4xx(monkeypatch):
    requests = []

    class StubClient:
        def __init__(self, timeout: float) -> None:
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def post(self, url: str, *, params: dict, headers: dict, json: dict):
            requests.append(params["key"])
            request = httpx.Request("POST", url)
            if params["key"] == "key-1":
                return httpx.Response(
                    403,
                    request=request,
                    text='{"error":{"status":"PERMISSION_DENIED","message":"denied"}}',
                )
            return httpx.Response(
                200,
                request=request,
                json={
                    "candidates": [{"content": {"parts": [{"text": "ok"}]}}],
                    "usageMetadata": {"promptTokenCount": 1, "candidatesTokenCount": 1},
                },
            )

    monkeypatch.setattr(httpx, "Client", StubClient)
    provider = GeminiNativeProvider(
        base_url="https://example.test",
        api_key="key-1",
        api_keys=["key-2"],
        chat_model="test-model",
        embedding_model="test-embedding",
        timeout_seconds=1,
    )

    response = provider.chat(ChatRequest(messages=[ChatMessage(role="user", content="hello")]))

    assert response.content == "ok"
    assert requests == ["key-1", "key-2"]


def test_gemini_native_provider_retries_5xx_before_failing_or_rotating(monkeypatch):
    requests = []
    sleeps = []

    class StubClient:
        def __init__(self, timeout: float) -> None:
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def post(self, url: str, *, params: dict, headers: dict, json: dict):
            requests.append(params["key"])
            request = httpx.Request("POST", url)
            if len(requests) == 1:
                return httpx.Response(
                    503,
                    request=request,
                    text='{"error":{"status":"UNAVAILABLE","message":"high demand"}}',
                )
            return httpx.Response(
                200,
                request=request,
                json={
                    "candidates": [{"content": {"parts": [{"text": "ok"}]}}],
                    "usageMetadata": {"promptTokenCount": 1, "candidatesTokenCount": 1},
                },
            )

    monkeypatch.setattr(httpx, "Client", StubClient)
    monkeypatch.setattr("app.ai.gateway.providers.gemini_native.time.sleep", sleeps.append)
    provider = GeminiNativeProvider(
        base_url="https://example.test",
        api_key="key-1",
        api_keys=["key-2"],
        chat_model="test-model",
        embedding_model="test-embedding",
        timeout_seconds=1,
    )

    response = provider.chat(ChatRequest(messages=[ChatMessage(role="user", content="hello")]))

    assert response.content == "ok"
    assert requests == ["key-1", "key-1"]
    assert sleeps == [1.0]


def test_gemini_native_provider_skips_exhausted_key_on_next_call(monkeypatch):
    requests = []

    class StubClient:
        def __init__(self, timeout: float) -> None:
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def post(self, url: str, *, params: dict, headers: dict, json: dict):
            requests.append(params["key"])
            request = httpx.Request("POST", url)
            if params["key"] == "key-1":
                return httpx.Response(429, request=request, text="quota exceeded")
            return httpx.Response(
                200,
                request=request,
                json={"embedding": {"values": [0.1, 0.2]}},
            )

    monkeypatch.setattr(httpx, "Client", StubClient)
    provider = GeminiNativeProvider(
        base_url="https://example.test",
        api_key="key-1",
        api_keys=["key-2"],
        chat_model="test-model",
        embedding_model="test-embedding",
        timeout_seconds=1,
    )

    first = provider.embed("hello")
    second = provider.embed("hello again")

    assert first.embedding == [0.1, 0.2]
    assert second.embedding == [0.1, 0.2]
    assert requests == ["key-1", "key-2", "key-2"]


def test_gemini_native_provider_reports_when_all_keys_are_exhausted(monkeypatch):
    class StubClient:
        def __init__(self, timeout: float) -> None:
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def post(self, url: str, *, params: dict, headers: dict, json: dict):
            request = httpx.Request("POST", url)
            return httpx.Response(429, request=request, text="quota exceeded")

    monkeypatch.setattr(httpx, "Client", StubClient)
    provider = GeminiNativeProvider(
        base_url="https://example.test",
        api_key="key-1",
        api_keys=["key-2"],
        chat_model="test-model",
        embedding_model="test-embedding",
        timeout_seconds=1,
    )

    with pytest.raises(LLMProviderUnavailable, match="quota exhausted"):
        provider.chat(ChatRequest(messages=[ChatMessage(role="user", content="hello")]))
