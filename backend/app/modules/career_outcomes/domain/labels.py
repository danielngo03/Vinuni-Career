"""User-facing bilingual labels for career-outcome enums.

Backend rule (`.claude/rules/backend.md`): no raw enum codes in end-user
responses. The university reporting surface shows these friendly labels; the raw
``trust_level`` int / ``outcome_type`` / ``source`` codes stay internal.
"""

from __future__ import annotations

# Trust levels (DATA_MODEL §27 / BUSINESS_LOGIC §13).
_TRUST_LABELS: dict[int, dict[str, str]] = {
    1: {"vi": "Đối tác xác nhận", "en": "Partner-confirmed"},
    2: {"vi": "Xác minh LinkedIn", "en": "LinkedIn-verified"},
    3: {"vi": "Sinh viên tự khai", "en": "Self-reported"},
    4: {"vi": "Ước tính từ hệ thống", "en": "System-estimated"},
}
_TRUST_FALLBACK = {"vi": "Không xác định", "en": "Unknown"}

_OUTCOME_LABELS: dict[str, dict[str, str]] = {
    "hired": {"vi": "Đã tuyển dụng", "en": "Hired"},
}
_OUTCOME_FALLBACK = {"vi": "Kết quả khác", "en": "Other outcome"}


def trust_label(trust_level: int, *, locale: str = "vi") -> str:
    entry = _TRUST_LABELS.get(trust_level, _TRUST_FALLBACK)
    return entry.get(locale, entry["en"])


def outcome_label(outcome_type: str, *, locale: str = "vi") -> str:
    entry = _OUTCOME_LABELS.get(outcome_type, _OUTCOME_FALLBACK)
    return entry.get(locale, entry["en"])
