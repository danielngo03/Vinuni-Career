"""Output guard — scrubs provider/model/token/key internals from AI output.

Applied to every gateway response before it leaves the AI layer
(``docs/SECURITY_PRIVACY.md`` AI Safety, ``.claude/rules/ai.md`` §9). End users
must never see provider names, model names, API keys, token counts, latency, raw
confidence, or internal status codes.
"""

from __future__ import annotations

import re

from app.ai.gateway.base import AICompletion

# Provider / vendor names that must not appear in user-facing text.
_FORBIDDEN_TERMS = [
    "openrouter",
    "openai",
    "anthropic",
    "claude",
    "gpt-4",
    "gpt-3",
    "gpt4",
    "gemini",
    "deepseek",
    "ollama",
    "mistral",
    "llama",
]

_API_KEY_RE = re.compile(r"sk-[A-Za-z0-9_\-]{8,}")
_BEARER_RE = re.compile(r"Bearer\s+[A-Za-z0-9._\-]+", re.IGNORECASE)
_MODEL_PATH_RE = re.compile(
    r"\b(?:deepseek|openai|anthropic|claude|gpt|gemini|mistral|llama|"
    r"meta-llama|qwen|google|azure)[\w.:\-]*/[\w.:\-]+\b",
    re.IGNORECASE,
)
_TOKEN_COUNT_RE = re.compile(r"\b\d+\s*tokens?\b", re.IGNORECASE)
# Internal JSON field names from provider response objects (must never reach user)
_TOKEN_FIELD_RE = re.compile(
    r"\b(prompt_tokens|completion_tokens|total_tokens|model_alias|finish_reason"
    r"|cache_write_tokens|cached_tokens|reasoning_tokens)\b",
    re.IGNORECASE,
)


def scrub_text(text: str) -> str:
    """Remove provider/model/key/token signals from a user-facing string."""

    cleaned = _API_KEY_RE.sub("[redacted]", text)
    cleaned = _BEARER_RE.sub("[redacted]", cleaned)
    cleaned = _TOKEN_COUNT_RE.sub("[redacted]", cleaned)
    cleaned = _TOKEN_FIELD_RE.sub("[redacted]", cleaned)
    cleaned = _MODEL_PATH_RE.sub("[hệ thống AI]", cleaned)

    for term in _FORBIDDEN_TERMS:
        cleaned = re.sub(re.escape(term), "[hệ thống AI]", cleaned, flags=re.IGNORECASE)

    return cleaned


def guard_completion(completion: AICompletion) -> str:
    """Return only the scrubbed, user-safe text from a completion.

    Drops ``usage``/``model_alias`` metadata entirely — these are internal-only.
    """

    return scrub_text(completion.text)
