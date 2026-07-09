"""Shared moderation-queue vocabulary and helpers.

Used by the university moderation surfaces of jobs and events
(``app.modules.opportunities``) and sponsored placements/creatives
(``app.modules.advertising``) so the reason-code vocabulary, SLA/due-by math,
and queue-age presentation are not triplicated per domain module.

Raw enum codes are still safe to show admins/moderators (unlike end-user public
APIs) but every code here is paired with a localized label per the platform
convention of never exposing a bare code as the only representation.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

# --------------------------------------------------------------------------- #
# Structured rejection / escalation reason codes                              #
# --------------------------------------------------------------------------- #

REASON_DUPLICATE_LISTING = "duplicate_listing"
REASON_MISLEADING_CONTENT = "misleading_content"
REASON_POLICY_VIOLATION = "policy_violation"
REASON_INCOMPLETE_INFO = "incomplete_info"
REASON_SPAM = "spam"
REASON_OTHER = "other"

REASON_CODES: frozenset[str] = frozenset(
    {
        REASON_DUPLICATE_LISTING,
        REASON_MISLEADING_CONTENT,
        REASON_POLICY_VIOLATION,
        REASON_INCOMPLETE_INFO,
        REASON_SPAM,
        REASON_OTHER,
    }
)

# ``other`` is the only code that requires a supplementary free-text note; every
# other code is self-explanatory but MAY still carry an optional free-text note
# for extra context (kept for backward compatibility with the legacy free-text
# ``reason``/``moderation_note`` field).
REASON_REQUIRES_NOTE: frozenset[str] = frozenset({REASON_OTHER})

_REASON_LABELS: dict[str, dict[str, str]] = {
    "vi": {
        REASON_DUPLICATE_LISTING: "Trùng lặp với tin/nội dung khác",
        REASON_MISLEADING_CONTENT: "Nội dung gây hiểu lầm",
        REASON_POLICY_VIOLATION: "Vi phạm chính sách nền tảng",
        REASON_INCOMPLETE_INFO: "Thông tin chưa đầy đủ",
        REASON_SPAM: "Spam / nội dung rác",
        REASON_OTHER: "Lý do khác",
    },
    "en": {
        REASON_DUPLICATE_LISTING: "Duplicate listing",
        REASON_MISLEADING_CONTENT: "Misleading content",
        REASON_POLICY_VIOLATION: "Policy violation",
        REASON_INCOMPLETE_INFO: "Incomplete information",
        REASON_SPAM: "Spam",
        REASON_OTHER: "Other",
    },
}


def is_valid_reason_code(code: str | None) -> bool:
    """``None`` is allowed (caller applies its own default, e.g. ``other``)."""

    return code is None or code in REASON_CODES


def reason_code_label(code: str | None, *, locale: str = "vi") -> str | None:
    if code is None:
        return None
    return _REASON_LABELS.get(locale, _REASON_LABELS["vi"]).get(code, code)


# --------------------------------------------------------------------------- #
# SLA / due-by + queue-age presentation                                       #
# --------------------------------------------------------------------------- #


def compute_due_by(submitted_at: datetime, *, sla_hours: int) -> datetime:
    """The SLA deadline computed at submission time (config-driven hours)."""

    return submitted_at + timedelta(hours=sla_hours)


def _as_utc(value: datetime | None) -> datetime | None:
    """Normalise to UTC-aware (SQLite round-trips ``DateTime`` columns as naive)."""

    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def queue_age_fields(
    *,
    submitted_at: datetime | None,
    due_by: datetime | None,
    now: datetime,
) -> dict:
    """Age/overdue presentation fields for a moderation-queue list/detail row."""

    submitted_at = _as_utc(submitted_at)
    due_by = _as_utc(due_by)
    now_utc = _as_utc(now) or now

    age_hours: float | None = None
    if submitted_at is not None:
        age_hours = round((now_utc - submitted_at).total_seconds() / 3600.0, 1)
    return {
        "due_by": due_by.isoformat() if due_by else None,
        "age_hours": age_hours,
        "is_overdue": bool(due_by is not None and now_utc >= due_by),
    }
