"""The six *_default function slots resolve and bind to config models (P1.2)."""

from __future__ import annotations

from app.ai.gateway import runtime_config
from app.ai.gateway.openai_compatible import known_aliases

_SLOTS = (
    "chat_default",
    "reasoning_default",
    "embedding_default",
    "rerank_default",
    "eval_default",
    "vision_default",
)


def test_default_slots_resolvable() -> None:
    resolvable = known_aliases()
    for slot in _SLOTS:
        assert slot in resolvable, f"{slot} not resolvable"


def test_bootstrap_binds_chat_default_to_config_model() -> None:
    cfg = runtime_config._bootstrap_from_env()
    provider, _base_url, model_id = cfg.provider_routes["chat_default"]
    assert provider == "openrouter"
    assert model_id == "deepseek/deepseek-v4-flash"


def test_bootstrap_binds_vision_default_to_config_model() -> None:
    cfg = runtime_config._bootstrap_from_env()
    _provider, _base_url, model_id = cfg.provider_routes["vision_default"]
    assert model_id == "google/gemini-2.5-flash"


def test_legacy_alias_still_resolvable() -> None:
    assert "chat_cheap" in known_aliases()
    assert "vision_cheap" in known_aliases()
