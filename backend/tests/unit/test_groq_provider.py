from __future__ import annotations

import pytest

from app.ai.gateway.errors import LLMProviderUnavailable
from app.ai.gateway.factory import _direct_gateway
from app.ai.gateway.providers.openai_compatible import OpenAICompatibleProvider
from app.ai.gateway.schemas import ChatMessage, ChatRequest


def test_groq_provider_is_registered_in_direct_gateway():
    gateway = _direct_gateway()

    assert "groq" in gateway.providers


def test_groq_requires_api_key_before_chat_request():
    provider = OpenAICompatibleProvider(
        name="groq",
        base_url="https://api.groq.com/openai/v1",
        api_key=None,
        chat_model="llama-3.3-70b-versatile",
        embedding_model=None,
        timeout_seconds=1,
    )

    with pytest.raises(LLMProviderUnavailable, match="groq API key is not configured"):
        provider.chat(ChatRequest(messages=[ChatMessage(role="user", content="hello")]))


def test_chat_only_provider_requires_embedding_model_before_embed_request():
    provider = OpenAICompatibleProvider(
        name="groq",
        base_url="https://api.groq.com/openai/v1",
        api_key="test-key",
        chat_model="llama-3.3-70b-versatile",
        embedding_model=None,
        timeout_seconds=1,
    )

    with pytest.raises(LLMProviderUnavailable, match="embedding model is not configured"):
        provider.embed("hello")
