"""Per-alias token cost estimator for ``ai_usage_log.cost_usd``.

Prices are conservative estimates in USD per 1M tokens. When the concrete
provider/model is changed via the admin UI, admins should also update the
price table in ai_settings; these are fallback estimates for known built-in
aliases only and are never surfaced to end users.

Internal use only — never log or return provider names or model IDs.
"""

from __future__ import annotations

# Estimated cost per 1M tokens in USD.
# Keyed by gateway alias, not by model/provider name.
_ALIAS_PRICE_PER_1M: dict[str, float] = {
    # Function slots (concrete model set via admin/.env; these are fallback
    # estimates for the seeded defaults).
    "chat_default": 0.15,  # ~deepseek-v4-flash blended
    "reasoning_default": 0.55,  # ~deepseek-r1 blended
    "embedding_default": 0.02,  # text-embedding-3-small
    "rerank_default": 0.15,
    "eval_default": 0.15,
    "vision_default": 0.30,  # ~gemini-2.5-flash blended
    # Legacy aliases (resolvable synonyms).
    "chat_cheap": 0.14,  # ~deepseek-chat blended input/output
    "chat_free": 0.0,  # free tier — treat as 0
    "chat_mini": 0.10,
    "reasoning_cheap": 0.55,  # ~deepseek-r1 blended
    "reasoning_local": 0.0,
    "eval_cheap": 0.14,
    "eval_local": 0.0,
    "embedding_cheap": 0.02,  # text-embedding-3-small
    "embedding_openai": 0.02,
    "embedding_local": 0.0,
    "rerank_cheap": 0.14,
    "rerank_openai_fast": 0.15,
    "rerank_local": 0.0,
    "chat_openai_fast": 0.15,  # gpt-4o-mini blended
    "chat_openai_best": 2.50,  # gpt-4o blended
    "chat_local": 0.0,  # local Ollama — no cloud cost
    "chat_local_large": 0.0,
}

_DEFAULT_PRICE_PER_1M = 0.20  # conservative fallback for unknown aliases

# Chars-per-token approximation (conservative — real tokeniser varies by model)
_CHARS_PER_TOKEN = 4.0


def estimate_cost_usd(
    alias: str,
    *,
    prompt_chars: int = 0,
    completion_chars: int = 0,
) -> float:
    """Return an estimated cost in USD for one LLM call.

    Uses character counts as a proxy for token counts. The estimate is
    intentionally conservative (rounds up) so the budget guard errs on the
    side of caution. Real per-token counts from provider responses would be
    more accurate but require parsing every provider's response body.
    """
    price_per_1m = _ALIAS_PRICE_PER_1M.get(alias, _DEFAULT_PRICE_PER_1M)
    total_chars = prompt_chars + completion_chars
    tokens_estimate = total_chars / _CHARS_PER_TOKEN
    return (tokens_estimate / 1_000_000) * price_per_1m
