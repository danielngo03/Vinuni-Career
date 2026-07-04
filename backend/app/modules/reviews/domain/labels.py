"""User-facing bilingual labels for review enums (no raw codes to end users)."""

from __future__ import annotations

from app.modules.reviews.domain import entities

_STATUS: dict[str, dict[str, str]] = {
    entities.STATUS_PENDING: {"vi": "Chờ duyệt", "en": "Pending review"},
    entities.STATUS_PUBLISHED: {"vi": "Đã đăng", "en": "Published"},
    entities.STATUS_FLAGGED: {"vi": "Bị báo cáo", "en": "Flagged"},
    entities.STATUS_REMOVED: {"vi": "Đã gỡ", "en": "Removed"},
}

# Trust badge shown next to a review author (derived from eligibility_type).
_TRUST: dict[str, dict[str, str]] = {
    entities.ELIG_OFFER: {"vi": "Đã nhận lời mời", "en": "Offer received"},
    entities.ELIG_INTERVIEW: {"vi": "Đã phỏng vấn", "en": "Interviewed"},
    entities.ELIG_SELF: {"vi": "Tự xác nhận", "en": "Self-declared"},
    entities.ELIG_PARTNER: {"vi": "Đối tác xác nhận", "en": "Partner-verified"},
}
_FALLBACK = {"vi": "Không xác định", "en": "Unknown"}


def status_label(status: str, *, locale: str = "vi") -> str:
    entry = _STATUS.get(status, _FALLBACK)
    return entry.get(locale, entry["en"])


def trust_label(eligibility_type: str, *, locale: str = "vi") -> str:
    entry = _TRUST.get(eligibility_type, _FALLBACK)
    return entry.get(locale, entry["en"])
