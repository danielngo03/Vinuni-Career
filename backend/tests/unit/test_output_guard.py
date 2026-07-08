"""Output guard scrubs provider/model/token/key internals."""

from __future__ import annotations

from app.ai.gateway.base import AICompletion
from app.ai.gateway.output_guard import guard_completion, scrub_text


def test_scrubs_provider_and_model_names() -> None:
    text = "Generated via OpenRouter using deepseek/deepseek-chat (gpt-4 fallback)."
    cleaned = scrub_text(text).lower()
    assert "openrouter" not in cleaned
    assert "deepseek" not in cleaned
    assert "gpt-4" not in cleaned


def test_scrubs_api_keys_and_tokens() -> None:
    text = "key sk-abc123def456ghi used 1234 tokens; Authorization: Bearer abc.def.ghi"
    cleaned = scrub_text(text)
    assert "sk-abc123def456ghi" not in cleaned
    assert "Bearer abc.def.ghi" not in cleaned
    assert "1234 tokens" not in cleaned


def test_guard_completion_returns_only_safe_text() -> None:
    completion = AICompletion(
        text="Answer from anthropic claude model.",
        model_alias="chat_cheap",
        usage={"prompt_tokens": 10, "completion_tokens": 5},
    )
    out = guard_completion(completion)
    assert "anthropic" not in out.lower()
    assert "claude" not in out.lower()
    # The function returns a string only — no usage/alias metadata.
    assert isinstance(out, str)
