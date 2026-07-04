"""Output guard — post-generation safety scrub of AI completions.

Catches accidental leakage of provider names, model identifiers, API keys,
internal system prompt content, and structured injection attempts in model
output before it reaches callers (``docs/AI_PRODUCT_SPEC.md`` §9.2).

Returns a cleaned string plus a list of internal ``flags`` (metadata-only —
never surfaced to users or logs that preserve raw content).
"""

from __future__ import annotations

import re
from collections.abc import Iterable

# Patterns that indicate leaked internal content. Each pattern is stripped or
# replaced with a generic safe string. The goal is defence-in-depth alongside
# prompt-level suppression instructions.
_LEAK_PATTERNS: list[tuple[re.Pattern, str]] = [
    # Provider brand names (update when aliases change in factory.py)
    (re.compile(r"\bdeepseek\b", re.I), "[AI]"),
    (re.compile(r"\bopenrouter\b", re.I), "[AI]"),
    (re.compile(r"\bopenai\b", re.I), "[AI]"),
    (re.compile(r"\banthropics?\b", re.I), "[AI]"),
    (re.compile(r"\bgemini\b", re.I), "[AI]"),
    (re.compile(r"\bgpt[-\d]", re.I), "[AI]"),
    (re.compile(r"\bclaude[-\w]", re.I), "[AI]"),
    # Possible key leakage (sk-or- prefix, bearer patterns)
    (re.compile(r"sk-or-v\d+[-\w]{10,}", re.I), "[REDACTED]"),
    (re.compile(r"bearer\s+sk-\w{10,}", re.I), "[REDACTED]"),
    # Internal prompt artefacts
    (re.compile(r"<\|im_start\|>|<\|im_end\|>", re.I), ""),
    (re.compile(r"\[INST\]|\[/INST\]", re.I), ""),
    # Token / latency internals
    (re.compile(r"\b\d+\s+(?:input|output|prompt|completion)\s+tokens?\b", re.I), ""),
]

# Absolute max length to allow through (prevent accidental large dumps)
_MAX_OUTPUT_CHARS = 20_000


def guard_completion(text: str | None) -> str:
    """Scrub a raw model completion and return a safe string.

    Args:
        text: Raw text from the AI provider.

    Returns:
        Cleaned string safe to pass to the next pipeline stage or return to
        users. Never raises. Empty or ``None`` input returns ``""``.
    """
    if not text:
        return ""

    cleaned = text[:_MAX_OUTPUT_CHARS]
    for pattern, replacement in _LEAK_PATTERNS:
        cleaned = pattern.sub(replacement, cleaned)

    return cleaned.strip()


def enforce_keyword_scope(
    text: str,
    *,
    domain_keywords: Iterable[str],
    refusal_text: str,
    skip: bool = False,
) -> str:
    """Post-generation topical-scope fallback for the ReAct chat loop (§9.2).

    Design note (documented deviation/choice — AI rule item 1): the pre-LLM
    planner (``app.modules.ai_assistant.application.agentic.planner``) already
    hard-blocks the HEAD of off-topic phrasing via a keyword allowlist before
    the model is even called. That still leaves a long tail: any message that
    happens to contain one allowlisted keyword (the list is intentionally
    broad — "error", "role", "admin", etc.) reaches the LLM, and the system
    prompt's scope instruction is the only thing keeping the *answer* on
    topic. This function is the requested fallback: apply the SAME keyword
    check to the model's OWN final answer and short-circuit to the SAME
    refusal copy the planner uses when the answer references none of the
    domain keywords. It intentionally does NOT import the planner module
    directly — ``app.ai`` is a shared library and must not depend on
    ``app.modules.*`` (layering) — so the caller (``ai_assistant.chat_service``)
    passes its own keyword list and refusal copy in.

    ``skip`` must be ``True`` whenever a tool was actually dispatched this
    turn — a tool-grounded answer is trusted by construction even if its
    prose happens not to repeat a keyword (e.g. a bare company name).
    """
    if skip or not text:
        return text
    lowered = text.lower()
    if any(keyword.lower() in lowered for keyword in domain_keywords):
        return text
    return refusal_text


def guard_completion_with_flags(text: str | None) -> tuple[str, list[str]]:
    """Like :func:`guard_completion` but also returns a list of detected flags.

    Flags are internal metadata (e.g. ``["provider_leaked"]``) and must only
    be written to internal logs — never exposed to API callers.
    """
    if not text:
        return "", []

    flags: list[str] = []
    cleaned = text[:_MAX_OUTPUT_CHARS]

    for pattern, replacement in _LEAK_PATTERNS:
        if pattern.search(cleaned):
            flags.append("output_leak")
        cleaned = pattern.sub(replacement, cleaned)

    return cleaned.strip(), list(dict.fromkeys(flags))
