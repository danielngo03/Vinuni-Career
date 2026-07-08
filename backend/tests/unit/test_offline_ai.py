"""Offline AI provider determinism + factory default selection."""

from __future__ import annotations

from app.ai.gateway.base import AIMessage
from app.ai.gateway.factory import get_provider
from app.ai.gateway.offline import OfflineProvider


async def test_offline_provider_is_deterministic() -> None:
    provider = OfflineProvider()
    messages = [
        AIMessage(role="system", content="You are helpful."),
        AIMessage(role="user", content="Tóm tắt CV của tôi."),
    ]
    first = await provider.complete(messages, alias="chat_cheap")
    second = await provider.complete(messages, alias="chat_cheap")
    assert first.text == second.text
    assert first.model_alias == "chat_cheap"


async def test_offline_provider_varies_with_input() -> None:
    provider = OfflineProvider()
    a = await provider.complete([AIMessage(role="user", content="A")], alias="chat_cheap")
    b = await provider.complete([AIMessage(role="user", content="B")], alias="chat_cheap")
    assert a.text != b.text


def test_factory_defaults_to_offline_without_real_calls() -> None:
    # AI_REAL_CALLS_ENABLED=false in the test env -> offline provider.
    assert isinstance(get_provider(), OfflineProvider)
