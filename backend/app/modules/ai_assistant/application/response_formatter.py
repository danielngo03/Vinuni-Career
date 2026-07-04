"""AI assistant response formatting helpers.

Pure/deterministic text-shaping used by ``chat_service``: fast-path replies for
trivial conversational turns (no model call), the user-safe AI-unavailable
message, leaked tool-call JSON stripping, and the local word-by-word SSE
"typing" chunker. Extracted from the former monolithic ``chat_service.py``.
"""

from __future__ import annotations

import re

_GREETING_RE = re.compile(
    r"^\s*(xin\s+chào|chào|chào\s+bạn|hello|hi|hey|alo|hi\s+there)[!.?\s]*$",
    re.IGNORECASE,
)


def ai_unavailable_reply() -> str:
    return (
        "Xin lỗi, trợ lý AI tạm thời không khả dụng. "
        "Vui lòng thử lại sau hoặc dùng thanh tìm kiếm để khám phá cơ hội việc làm."
    )


def fast_path_reply(text: str) -> str | None:
    """Return deterministic replies for tiny conversational turns.

    These turns do not need a model call. Keeping them local reduces latency,
    cost, and the chance of over-answering a simple greeting.
    """
    if _GREETING_RE.match(text):
        return (
            "Xin chào! Mình là trợ lý hướng nghiệp của VinUni. "
            "Bạn có thể hỏi mình về việc làm phù hợp, CV, đơn ứng tuyển, "
            "sự kiện tuyển dụng, mức lương hoặc định hướng nghề nghiệp."
        )
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


def strip_tool_call_json(text: str) -> str:
    """Remove leaked tool-call JSON from a final assistant response."""
    if "tool_call" not in text:
        return text.strip()
    stripped = re.sub(r"\{[^{}]*\"tool_call\"[\s\S]*\}\s*", "", text).strip()
    if stripped:
        return stripped
    return "Mình đang tra cứu dữ liệu hệ thống. Vui lòng thử lại với câu hỏi cụ thể hơn."
