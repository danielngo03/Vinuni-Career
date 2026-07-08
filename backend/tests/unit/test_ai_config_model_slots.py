"""Config exposes concrete per-slot models and *_default slot aliases (P1.1)."""

from __future__ import annotations

from app.core.config import get_settings


def test_default_slot_models_are_concrete() -> None:
    s = get_settings()
    assert s.ai_default_provider == "openrouter"
    assert s.ai_chat_model == "deepseek/deepseek-v4-flash"
    assert s.ai_reasoning_model == "deepseek/deepseek-r1"
    assert s.ai_embedding_model == "text-embedding-3-small"
    assert s.ai_rerank_model == "deepseek/deepseek-v4-flash"
    assert s.ai_eval_model == "deepseek/deepseek-v4-flash"
    assert s.ai_vision_model == "google/gemini-2.5-flash"


def test_slot_alias_defaults_renamed() -> None:
    s = get_settings()
    assert s.ai_default_model_alias == "chat_default"
    assert s.ai_reasoning_model_alias == "reasoning_default"
    assert s.ai_embedding_model_alias == "embedding_default"
    assert s.ai_rerank_model_alias == "rerank_default"
    assert s.ai_eval_model_alias == "eval_default"
