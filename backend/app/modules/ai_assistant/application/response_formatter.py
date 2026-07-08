"""AI assistant response formatting helpers.

Pure/deterministic text-shaping used by ``chat_service``: fast-path replies for
trivial conversational turns (no model call), the user-safe AI-unavailable
message, leaked tool-call JSON stripping, and the local word-by-word SSE
"typing" chunker. Extracted from the former monolithic ``chat_service.py``.
"""

from __future__ import annotations

import re

from app.modules.ai_assistant.application.messages import assistant_message

_GREETING_RE = re.compile(
    r"^\s*(xin\s+chào|chào|chào\s+bạn|hello|hi|hey|alo|hi\s+there)[!.?\s]*$",
    re.IGNORECASE,
)


def ai_unavailable_reply(locale: str = "vi") -> str:
    return assistant_message("formatter.ai_unavailable", locale)


def fast_path_reply(text: str, locale: str = "vi") -> str | None:
    """Return deterministic replies for tiny conversational turns.

    These turns do not need a model call. Keeping them local reduces latency,
    cost, and the chance of over-answering a simple greeting.
    """
    if _GREETING_RE.match(text):
        return assistant_message("formatter.greeting", locale)
    return None


def local_stream_chunks(text: str):
    """Yield ``text`` word-by-word for a live-typing feel without extra LLM calls.

    Called after the tool loop has already called the provider via
    ``_llm_complete()``. Re-calling ``provider.stream()`` here would double
    token cost and risk returning different text than the persisted message.
    Simple word splitting is sufficient for SSE token delivery.
    """
    words = text.split(" ")
    for i, word in enumerate(words):
        yield word if i == len(words) - 1 else word + " "


def strip_tool_call_json(text: str, locale: str = "vi") -> str:
    """Remove leaked tool-call JSON from a final assistant response."""
    if "tool_call" not in text:
        return text.strip()
    stripped = re.sub(r"\{[^{}]*\"tool_call\"[\s\S]*\}\s*", "", text).strip()
    if stripped:
        return stripped
    return assistant_message("formatter.stripped_tool_call_fallback", locale)
