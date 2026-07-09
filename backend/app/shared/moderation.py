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


def _ensure_utc(value: datetime) -> datetime:
    """UTC-aware normalisation for a value that is always present."""

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
    now = _ensure_utc(now)

    age_hours: float | None = None
    if submitted_at is not None:
        age_hours = round((now - submitted_at).total_seconds() / 3600.0, 1)
    return {
        "due_by": due_by.isoformat() if due_by else None,
        "age_hours": age_hours,
        "is_overdue": bool(due_by is not None and now >= due_by),
    }


# --------------------------------------------------------------------------- #
# Cross-queue SLA policy (BUSINESS_LOGIC.md §11)                               #
# --------------------------------------------------------------------------- #
#
# One code-level policy table shared by every university operational queue so
# the SLA hours, "due soon"/"overdue" health, and breach roll-ups presented on
# the ops command center are computed identically everywhere (never re-derived
# per surface). Codes are stable identifiers; the ops read-model and each
# queue presenter pair them with a localized label.

QUEUE_PARTNER_REGISTRATION = "partner_registration"
QUEUE_JOB_POSTING = "job_posting"
QUEUE_EVENT = "event"
QUEUE_AD_CREATIVE = "ad_creative"
QUEUE_COMPANY_REVIEW = "company_review"
QUEUE_CONTENT_REPORT = "content_report"
QUEUE_AI_FLAGGED = "ai_flagged"
QUEUE_SUPPORT_CASE = "support_case"
QUEUE_PRIVACY_REQUEST = "privacy_request"
QUEUE_CV_REVIEW = "cv_review"
QUEUE_AT_RISK = "at_risk"

# SLA windows in hours. The moderation rows track BUSINESS_LOGIC.md §11 exactly;
# the trust/career rows use operationally sensible defaults (privacy honours a
# 30-day legal window; support/CV-review/at-risk use business-day outreach
# windows) until a per-queue config surface exists.
QUEUE_SLA_HOURS: dict[str, int] = {
    QUEUE_PARTNER_REGISTRATION: 48,
    QUEUE_JOB_POSTING: 24,
    QUEUE_EVENT: 24,
    QUEUE_AD_CREATIVE: 24,
    QUEUE_COMPANY_REVIEW: 24,
    QUEUE_CONTENT_REPORT: 6,
    QUEUE_AI_FLAGGED: 4,
    QUEUE_SUPPORT_CASE: 48,
    QUEUE_PRIVACY_REQUEST: 720,
    QUEUE_CV_REVIEW: 72,
    QUEUE_AT_RISK: 120,
}

SLA_OK = "ok"
SLA_DUE_SOON = "due_soon"
SLA_OVERDUE = "overdue"


def sla_hours_for(kind: str) -> int | None:
    """SLA window (hours) for a queue kind, or ``None`` if the kind is unknown."""

    return QUEUE_SLA_HOURS.get(kind)


def sla_health(
    *,
    submitted_at: datetime | None,
    due_by: datetime | None,
    now: datetime,
) -> str:
    """Traffic-light SLA state for a queue row.

    ``overdue`` once the deadline has passed; ``due_soon`` (amber) within the
    final ``max(2h, 25% of the SLA window)`` before it; ``ok`` otherwise. With
    no deadline the row is treated as ``ok`` (nothing to breach).
    """

    submitted_at = _as_utc(submitted_at)
    due_by = _as_utc(due_by)
    now = _ensure_utc(now)

    if due_by is None:
        return SLA_OK
    if now >= due_by:
        return SLA_OVERDUE
    remaining = (due_by - now).total_seconds()
    amber = 2 * 3600.0
    if submitted_at is not None:
        window = (due_by - submitted_at).total_seconds()
        if window > 0:
            amber = max(amber, 0.25 * window)
    return SLA_DUE_SOON if remaining <= amber else SLA_OK


def sla_fields(
    *,
    submitted_at: datetime | None,
    kind: str,
    now: datetime,
) -> dict:
    """Full SLA presentation block for a queue row: due-by, age, overdue, health.

    Computes ``due_by`` from ``submitted_at + QUEUE_SLA_HOURS[kind]`` (no stored
    column required) and folds in :func:`queue_age_fields` plus the traffic-light
    :func:`sla_health` state and the policy window used.
    """

    hours = QUEUE_SLA_HOURS.get(kind)
    due_by = (
        compute_due_by(submitted_at, sla_hours=hours)
        if submitted_at is not None and hours is not None
        else None
    )
    fields = queue_age_fields(submitted_at=submitted_at, due_by=due_by, now=now)
    fields["sla_hours"] = hours
    fields["sla_health"] = sla_health(submitted_at=submitted_at, due_by=due_by, now=now)
    return fields
