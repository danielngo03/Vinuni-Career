"""AI safety policy orchestration (AI_PRODUCT_SPEC §9, SECURITY_PRIVACY.md §AI).

Pipeline per request:
  1. Fast regex sanitisation (existing input_guard) — PII redaction, injection strip
  2. Intent classification — categorise the cleaned message using rule-based signals
  3. Policy decision — allow / allow_with_note / rewrite / refuse
  4. Tool permission gate — check whether the detected intent is allowed for the
     requested tool class
  5. Audit record — structured flags written to log (never raw content)

This module sits between the request handler and the LLM call. It replaces the
direct call to ``sanitize_instruction()`` in ``AiTaskRunner`` and tool-specific
callers. Domain code calls ``check_policy(text, tool_class)`` and receives a
``PolicyDecision``; if ``action == "refuse"``, the caller returns a user-safe
refusal without calling the LLM.

All classification is deterministic rule-based — no LLM call inside the guard
(that would be recursive, expensive, and create a guard-bypass surface).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger("ai.safety")


# ---------------------------------------------------------------------------
# Tool permission classes (ai.md §7)
# ---------------------------------------------------------------------------

READ_ONLY = "read_only"
WRITE_WITH_CONFIRM = "write_with_confirm"
ADMIN_ONLY = "admin_only"


# ---------------------------------------------------------------------------
# Intent categories
# ---------------------------------------------------------------------------

INTENT_BENIGN = "benign"
INTENT_OFF_TOPIC = "off_topic"  # clearly outside VinUni career domain
INTENT_BOUNDARY_PROBE = "boundary_probe"  # testing limits / jailbreak attempt
INTENT_HARMFUL = "harmful"  # explicit harmful content request
INTENT_EXTERNAL_SOURCE = "external_source"  # asking the assistant to use non-platform sources
INTENT_PERSONAL_DATA = "personal_data"  # PII was present (already redacted by input_guard)

# Policy actions
ACTION_ALLOW = "allow"
ACTION_ALLOW_WITH_NOTE = "allow_with_note"  # proceed but add a system note to logs
ACTION_REWRITE = "rewrite"  # sanitised text replaces original
ACTION_REFUSE = "refuse"  # do not call LLM; return safe refusal


@dataclass
class PolicyDecision:
    """Result of the policy orchestrator for a single user message."""

    action: str  # one of the ACTION_* constants
    clean_text: str | None  # sanitised text to pass to LLM (None if refuse)
    intent: str = INTENT_BENIGN  # detected intent category
    flags: list[str] = field(default_factory=list)
    refusal_message: str | None = None  # user-safe refusal (if action == refuse)


# ---------------------------------------------------------------------------
# Intent classification rules
# ---------------------------------------------------------------------------

_OFF_TOPIC_SIGNALS = [
    re.compile(r"\b(bitcoin|crypto|forex|trading|gambling|casino|bet)\b", re.I),
    re.compile(
        r"\b(synthesise|synthesize|manufacture)\b.{0,30}"
        r"\b(drug|chemical|explosive|weapon)\b",
        re.I,
    ),
    re.compile(
        r"\b(hack|exploit|ddos|sql injection|xss|phishing)\b"
        r"[^.]{0,60}\b(me|please|want)\b",
        re.I,
    ),
]

_BOUNDARY_PROBE_SIGNALS = [
    re.compile(
        r"(reveal|show me your|what are your)\s+"
        r"(instructions?|rules?|system\s*prompt|training)",
        re.I,
    ),
    re.compile(
        r"(reveal|show|print|repeat)\s+(your|the)\s+"
        r"(system\s*)?(prompt|instructions?)",
        re.I,
    ),
    re.compile(r"(reveal|show|print|repeat|leak).{0,40}(system\s+)?(prompt|instructions?)", re.I),
    re.compile(
        r"(pretend|imagine|roleplay)\s+(you|you're|you are)\s+"
        r"(not|no longer|a different)",
        re.I,
    ),
    re.compile(r"dan\s+mode|developer\s+mode|jailbreak\s+mode", re.I),
    re.compile(r"bypass\s+(safety|filter|guard|policy|rule|restriction)", re.I),
    re.compile(
        r"what\s+(model|llm|ai|gpt|claude|provider)\s+"
        r"(are you|is this|am i using|powering)",
        re.I,
    ),
    re.compile(r"(your|the)\s+(api\s+key|key\s+is|token\s+is|secret)", re.I),
    re.compile(r"ignore\s+(all\s+|the\s+)?(previous|prior|above|earlier)\s+instructions?", re.I),
    re.compile(r"how much does it cost\s+(to|per|each)", re.I),
]

_HARMFUL_SIGNALS = [
    re.compile(r"\b(self.?harm|suicide|kill\s+(myself|yourself|someone))\b", re.I),
    re.compile(
        r"(how to|how do i)\s+(make|build|create).{0,20}"
        r"(bomb|explosive|weapon|malware|ransomware|virus)",
        re.I,
    ),
    re.compile(
        r"\b(make|build|create|synthesize).{0,15}"
        r"(bomb|explosive|weapon|virus|malware)\b",
        re.I,
    ),
    re.compile(r"\b(child|minor).{0,20}\b(sexual|nude|naked|exploit)\b", re.I),
]

_EXTERNAL_SOURCE_SIGNALS = [
    re.compile(
        r"\b(search|find|browse|crawl|scrape|tra\s*cứu|tìm|kiếm|xem|review|đánh\s*giá)\b"
        r".{0,50}\b(linked\s*in|linkedin|linkedln|linkdn|glassdoor|topcv|"
        r"vieclam24h|careerbuilder|indeed|"
        r"google|internet|web|website)\b",
        re.I,
    ),
    re.compile(
        r"\b(linked\s*in|linkedin|linkedln|linkdn|glassdoor|topcv|"
        r"vieclam24h|careerbuilder|indeed|"
        r"google|internet|web|website)\b.{0,50}"
        r"\b(job|post|recommend|search|review|đánh\s*giá|gợi\s*ý|việc|công\s*ty)\b",
        re.I,
    ),
]

_PLATFORM_COMPANY_LOOKUP_ALLOWLIST = [
    re.compile(
        r"\bgoogle\b.{0,30}\b(là\s*công\s*ty|company|employer|nhà\s*tuyển\s*dụng)\b"
        r"|\b(là\s*công\s*ty|company|employer|nhà\s*tuyển\s*dụng)\b.{0,30}\bgoogle\b",
        re.I,
    ),
]


def _classify_intent(text: str) -> tuple[str, list[str]]:
    """Return (intent_category, flags). Fast rule-based, no LLM."""
    flags: list[str] = []

    for pattern in _HARMFUL_SIGNALS:
        if pattern.search(text):
            flags.append("harmful_signal")
            return INTENT_HARMFUL, flags

    for pattern in _BOUNDARY_PROBE_SIGNALS:
        if pattern.search(text):
            flags.append("boundary_probe")
            return INTENT_BOUNDARY_PROBE, flags

    for pattern in _OFF_TOPIC_SIGNALS:
        if pattern.search(text):
            flags.append("off_topic")
            return INTENT_OFF_TOPIC, flags

    for pattern in _PLATFORM_COMPANY_LOOKUP_ALLOWLIST:
        if pattern.search(text):
            return INTENT_BENIGN, flags

    for pattern in _EXTERNAL_SOURCE_SIGNALS:
        if pattern.search(text):
            flags.append("external_source_request")
            return INTENT_EXTERNAL_SOURCE, flags

    return INTENT_BENIGN, flags


# ---------------------------------------------------------------------------
# Tool permission policy
# ---------------------------------------------------------------------------

_INTENT_TOOL_POLICY: dict[str, dict[str, str]] = {
    INTENT_HARMFUL: {
        READ_ONLY: ACTION_REFUSE,
        WRITE_WITH_CONFIRM: ACTION_REFUSE,
        ADMIN_ONLY: ACTION_REFUSE,
    },
    INTENT_BOUNDARY_PROBE: {
        READ_ONLY: ACTION_REFUSE,
        WRITE_WITH_CONFIRM: ACTION_REFUSE,
        ADMIN_ONLY: ACTION_REFUSE,
    },
    INTENT_OFF_TOPIC: {
        READ_ONLY: ACTION_ALLOW_WITH_NOTE,
        WRITE_WITH_CONFIRM: ACTION_ALLOW_WITH_NOTE,
        ADMIN_ONLY: ACTION_ALLOW,
    },
    INTENT_EXTERNAL_SOURCE: {
        READ_ONLY: ACTION_REFUSE,
        WRITE_WITH_CONFIRM: ACTION_REFUSE,
        ADMIN_ONLY: ACTION_REFUSE,
    },
    INTENT_BENIGN: {
        READ_ONLY: ACTION_ALLOW,
        WRITE_WITH_CONFIRM: ACTION_ALLOW,
        ADMIN_ONLY: ACTION_ALLOW,
    },
    INTENT_PERSONAL_DATA: {
        READ_ONLY: ACTION_REWRITE,
        WRITE_WITH_CONFIRM: ACTION_REWRITE,
        ADMIN_ONLY: ACTION_REWRITE,
    },
}

# Maps a refused intent to its localized user-facing refusal catalog key. The
# actual vi/en copy lives in the ai_assistant message catalog so all user-facing
# assistant text is localized in one place; this module only owns intent -> key.
_REFUSAL_MESSAGE_KEYS: dict[str, str] = {
    INTENT_HARMFUL: "safety.refuse.harmful",
    INTENT_BOUNDARY_PROBE: "safety.refuse.boundary_probe",
    INTENT_EXTERNAL_SOURCE: "safety.refuse.external_source",
}


def _refusal_message(intent: str, locale: str) -> str:
    """User-safe refusal text for ``intent`` in ``locale`` (defaults to vi).

    Imported lazily so ``app.ai.safety`` keeps no import-time dependency on
    ``app.modules.*`` (layering); the catalog is a plain data lookup.
    """
    from app.modules.ai_assistant.application.messages import assistant_message

    key = _REFUSAL_MESSAGE_KEYS.get(intent, "safety.refuse.generic")
    return assistant_message(key, locale)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def check_policy(
    text: str | None,
    tool_class: str = READ_ONLY,
    *,
    locale: str = "vi",
) -> PolicyDecision:
    """Run the full safety pipeline and return a PolicyDecision.

    Args:
        text: Raw user message. None → allow with None clean_text.
        tool_class: Permission class of the tool being invoked.
        locale: User-facing language for the refusal message ("vi"/"en");
            unknown values fall back to "vi" so callers can pass a raw locale
            hint. Only the ``refusal_message`` is localized — classification,
            flags, and audit are language independent.

    Returns:
        PolicyDecision with action, clean_text, intent, and flags.
    """
    if text is None:
        return PolicyDecision(action=ACTION_ALLOW, clean_text=None)

    # Step 1: classify intent on the RAW text first so injection/harmful patterns
    # are detected before sanitise_instruction strips the trigger phrases.
    intent, intent_flags = _classify_intent(text)
    all_flags = list(intent_flags)

    # Step 2: sanitise (PII redaction + injection strip) — reuse input_guard
    from app.ai.safety.input_guard import sanitize_instruction

    clean, sanitize_flags = sanitize_instruction(text)
    all_flags.extend(f for f in sanitize_flags if f not in all_flags)

    # Upgrade benign intent to personal_data when PII was found (so rewrite action fires).
    # Do not override a higher-severity intent (harmful/boundary_probe stay as-is).
    if intent == INTENT_BENIGN and "pii_redacted" in all_flags:
        intent = INTENT_PERSONAL_DATA

    # Step 3: look up policy action
    tool_policy = _INTENT_TOOL_POLICY.get(intent, {})
    action = tool_policy.get(tool_class, ACTION_ALLOW_WITH_NOTE)

    if not clean and action != ACTION_REFUSE:
        return PolicyDecision(action=ACTION_ALLOW, clean_text=None, flags=all_flags)

    # Step 4: audit (metadata only — no raw text in logs)
    if all_flags:
        logger.warning(
            "ai_safety_guard",
            extra={
                "intent": intent,
                "action": action,
                "flags": all_flags,
                "tool_class": tool_class,
                "text_len": len(clean or ""),
            },
        )

    # Step 5: build decision
    if action == ACTION_REFUSE:
        return PolicyDecision(
            action=ACTION_REFUSE,
            clean_text=None,
            intent=intent,
            flags=all_flags,
            refusal_message=_refusal_message(intent, locale),
        )

    return PolicyDecision(
        action=action,
        clean_text=clean,
        intent=intent,
        flags=all_flags,
    )
