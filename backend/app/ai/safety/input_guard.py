"""Input guard — pre-generation sanitisation of free-text user input.

CV AI tools take optional free-text ``instruction`` / ``raw_notes``. This guard
(``docs/AI_PRODUCT_SPEC.md`` §9.1) neutralises prompt-injection markers and caps
length BEFORE any text reaches the LLM. Returns a sanitised string plus a list of
internal flags (logged metadata-only — never surfaced to the user, never the
matched content).

Design note (deviation, documented): rather than hard-rejecting a CV
``instruction`` with ``400 UNSAFE_INPUT`` (a poor UX for a free-text field), the
guard *strips* injection phrases and proceeds. This is safe because the CV task
layer grounds all generated FACTS in structured sources only — the instruction
can never introduce a fact (see ``app.ai.cv.grounding`` / ``app.ai.cv.fabrication``).
"""

from __future__ import annotations

import re

# Default cap (~ docs §9.1 MAX_USER_MESSAGE_TOKENS budget, char-approximated).
MAX_INSTRUCTION_CHARS = 4000

# PII patterns — redacted BEFORE text reaches the LLM (§9.1 / SECURITY_PRIVACY.md).
# We replace matches with a safe placeholder so the model never sees raw PII.
_PII_PATTERNS: list[tuple[re.Pattern, str]] = [
    # API keys — scrub before the LLM sees them (e.g. sk-or-v1-... OpenRouter/OpenAI patterns)
    (re.compile(r"\bsk-[A-Za-z0-9_\-]{8,}\b"), "[api_key]"),
    # Email addresses
    (re.compile(r"[\w.+\-]+@[\w\-]+\.[\w.\-]+", re.I), "[email]"),
    # Vietnamese mobile numbers: 10 digits starting with 0 (03x, 05x, 07x, 08x, 09x)
    (re.compile(r"\b0[35789]\d{8}\b"), "[phone]"),
    # Vietnamese CCCD / CMND: 9 or 12 digits
    (re.compile(r"\b\d{9}\b|\b\d{12}\b"), "[id_number]"),
    # Generic long digit strings that could be account/card numbers (13+ digits)
    (re.compile(r"\b\d{13,}\b"), "[number]"),
]

# Prompt-injection / jailbreak signals. Matched case-insensitively; on match the
# span is removed from the text and an "injection" flag is recorded.
_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+|the\s+)?(previous|prior|above|earlier)\s+instructions?", re.I),
    re.compile(r"disregard\s+(all\s+|the\s+)?(previous|prior|above)\b.*", re.I),
    re.compile(r"\[\s*system\s*\]", re.I),
    re.compile(r"<\s*/?\s*(inst|system|im_start|im_end)\b[^>]*>", re.I),
    re.compile(
        r"(reveal|show|print|repeat|leak)\b[^.\n]{0,40}\b(system\s+)?(prompt|instructions?)",
        re.I,
    ),
    re.compile(r"you\s+are\s+now\b.*", re.I),
    re.compile(r"act\s+as\b[^.\n]{0,40}\b(dan|developer\s+mode|jailbreak)", re.I),
    re.compile(r"begin\s+(reply|answer)\s+with", re.I),
]


def redact_pii(text: str) -> tuple[str, bool]:
    """Redact PII patterns from ``text``. Returns ``(redacted_text, pii_found)``."""
    found = False
    for pattern, placeholder in _PII_PATTERNS:
        replaced, n = re.subn(pattern, placeholder, text)
        if n:
            text = replaced
            found = True
    return text, found


def sanitize_instruction(text: str | None) -> tuple[str | None, list[str]]:
    """Return ``(clean_text, flags)``. ``None`` in -> ``(None, [])``."""

    if text is None:
        return None, []

    flags: list[str] = []
    cleaned = text

    # Redact PII before injection check (prevents PII-carrying injection strings)
    cleaned, had_pii = redact_pii(cleaned)
    if had_pii:
        flags.append("pii_redacted")

    for pattern in _INJECTION_PATTERNS:
        if pattern.search(cleaned):
            flags.append("injection")
            cleaned = pattern.sub(" ", cleaned)

    if len(cleaned) > MAX_INSTRUCTION_CHARS:
        flags.append("truncated")
        cleaned = cleaned[:MAX_INSTRUCTION_CHARS]

    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return (cleaned or None), _dedupe(flags)


def sanitize_notes(text: str | None) -> tuple[str | None, list[str]]:
    """Like :func:`sanitize_instruction` but PRESERVES line breaks.

    ``raw_notes`` is split into bullet points downstream, so newlines must
    survive (only intra-line whitespace is collapsed).
    """

    if text is None:
        return None, []

    flags: list[str] = []
    cleaned = text

    cleaned, had_pii = redact_pii(cleaned)
    if had_pii:
        flags.append("pii_redacted")

    for pattern in _INJECTION_PATTERNS:
        if pattern.search(cleaned):
            flags.append("injection")
            cleaned = pattern.sub(" ", cleaned)

    if len(cleaned) > MAX_INSTRUCTION_CHARS:
        flags.append("truncated")
        cleaned = cleaned[:MAX_INSTRUCTION_CHARS]

    cleaned = "\n".join(
        re.sub(r"[ \t]+", " ", line).strip() for line in cleaned.splitlines()
    ).strip()
    return (cleaned or None), _dedupe(flags)


def _dedupe(flags: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for flag in flags:
        if flag not in seen:
            seen.add(flag)
            out.append(flag)
    return out
