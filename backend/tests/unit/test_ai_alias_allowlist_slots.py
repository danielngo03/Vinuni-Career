"""Allowlist exposes *_default slots; legacy aliases are retired from the UI (P1.4)."""

from __future__ import annotations

from app.modules.ai_settings.domain import aliases


def test_default_slots_allowlisted() -> None:
    assert "chat_default" in aliases.allowed_aliases("chat_model_alias")
    assert "reasoning_default" in aliases.allowed_aliases("reasoning_model_alias")
    assert "embedding_default" in aliases.allowed_aliases("embedding_model_alias")
    assert "rerank_default" in aliases.allowed_aliases("rerank_model_alias")
    assert "eval_default" in aliases.allowed_aliases("eval_model_alias")


def test_legacy_aliases_not_allowlisted() -> None:
    assert "chat_cheap" not in aliases.allowed_aliases("chat_model_alias")
    assert "reasoning_cheap" not in aliases.allowed_aliases("reasoning_model_alias")


def test_allowlist_is_gateway_resolvable() -> None:
    aliases.assert_allowlist_resolvable()  # must not raise
