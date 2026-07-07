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

    submitted = _as_utc(submitted_at)
    due = _as_utc(due_by)
    now_utc = _as_utc(now)
    assert now_utc is not None  # ``now`` is always a concrete datetime

    age_hours: float | None = None
    if submitted is not None:
        age_hours = round((now_utc - submitted).total_seconds() / 3600.0, 1)
    return {
        "due_by": due.isoformat() if due else None,
        "age_hours": age_hours,
        "is_overdue": bool(due is not None and now_utc >= due),
    }


# --------------------------------------------------------------------------- #
# Per-queue SLA policy + traffic-light health (BUSINESS_LOGIC.md §11)          #
# --------------------------------------------------------------------------- #
#
# Canonical operations-queue keys. Kept stringly-stable because they are the
# contract the University Operations read model + frontend share.

QUEUE_JOBS = "jobs"
QUEUE_EVENTS = "events"
QUEUE_ADS = "ads"
QUEUE_PARTNER_REGISTRATIONS = "partner_registrations"
QUEUE_AI_REVIEW = "ai_review"

QUEUE_KEYS: tuple[str, ...] = (
    QUEUE_JOBS,
    QUEUE_EVENTS,
    QUEUE_ADS,
    QUEUE_PARTNER_REGISTRATIONS,
    QUEUE_AI_REVIEW,
)

# Documented per-type SLA hours (BUSINESS_LOGIC.md §11: partner reg 48h, job 24h,
# partner event 24h, ad creative 24h; AI-flagged 4h). The AI human-review queue
# carries mixed sources; 4h is the tightest documented value so it is the queue
# default (content-report/HIGH-severity items are the urgent members).
QUEUE_SLA_HOURS: dict[str, int] = {
    QUEUE_JOBS: 24,
    QUEUE_EVENTS: 24,
    QUEUE_ADS: 24,
    QUEUE_PARTNER_REGISTRATIONS: 48,
    QUEUE_AI_REVIEW: 4,
}

# Health traffic light shared by every queue card.
HEALTH_ON_TRACK = "on_track"
HEALTH_DUE_SOON = "due_soon"  # amber
HEALTH_BREACHED = "breached"  # red


def queue_sla_hours(queue_key: str) -> int:
    """SLA window (hours) for a queue key; falls back to the 24h job default."""

    return QUEUE_SLA_HOURS.get(queue_key, 24)


def sla_health(due_by: datetime | None, now: datetime, *, sla_hours: int = 24) -> str:
    """Traffic-light state for one item given its SLA deadline.

    - ``breached`` once ``now`` reaches ``due_by`` (red).
    - ``due_soon`` inside the amber window before the deadline. The window is
      ``max(2h, 25% of the SLA)`` — the ">2h before breach" pre-warn threshold
      of BUSINESS_LOGIC.md §11, widened for longer (48h) SLAs so partner-reg
      items still amber a shift ahead of breach.
    - ``on_track`` otherwise. ``due_by is None`` (no deadline yet) is on_track.
    """

    due = _as_utc(due_by)
    now_utc = _as_utc(now)
    assert now_utc is not None  # ``now`` is always a concrete datetime
    if due is None:
        return HEALTH_ON_TRACK
    if now_utc >= due:
        return HEALTH_BREACHED
    amber_hours = max(2.0, sla_hours * 0.25)
    remaining_hours = (due - now_utc).total_seconds() / 3600.0
    if remaining_hours <= amber_hours:
        return HEALTH_DUE_SOON
    return HEALTH_ON_TRACK


def queue_health(
    *,
    pending: int,
    overdue: int,
    due_soon: int = 0,
) -> str:
    """Roll a queue's item counts up to a single traffic-light for its card.

    Any breached item makes the whole queue red; else any amber item makes it
    amber; else green. An empty queue is on_track (nothing to do is healthy).
    """

    if overdue > 0:
        return HEALTH_BREACHED
    if due_soon > 0:
        return HEALTH_DUE_SOON
    return HEALTH_ON_TRACK


def summarize_queue(
    rows: list[tuple[datetime | None, datetime | None]],
    *,
    now: datetime,
    sla_hours: int,
) -> dict:
    """Aggregate the ``(submitted_at, due_by)`` pairs of a queue's PENDING items.

    Returns the queue-card contract shared by the University Operations read
    model and its frontend: ``pending`` / ``overdue`` (SLA-breached) / ``due_soon``
    (amber) counts, the ``oldest_age_hours`` waiting item, the ``next_due_at``
    deadline, the ``sla_hours`` window, and a rolled-up ``health`` traffic light.

    A ``due_by`` of ``None`` (queues that store no explicit deadline, e.g. the AI
    review queue and partner registrations) is derived as ``submitted_at +
    sla_hours`` so every queue reports SLA state on the same basis.
    """

    now_utc = _as_utc(now)
    assert now_utc is not None  # narrow for type-checkers; callers always pass a value
    pending = len(rows)
    overdue = 0
    due_soon = 0
    oldest_submitted: datetime | None = None
    next_due: datetime | None = None

    for raw_submitted, raw_due in rows:
        submitted_at = _as_utc(raw_submitted)
        due_by = _as_utc(raw_due)
        if due_by is None and submitted_at is not None:
            due_by = submitted_at + timedelta(hours=sla_hours)

        health = sla_health(due_by, now_utc, sla_hours=sla_hours)
        if health == HEALTH_BREACHED:
            overdue += 1
        elif health == HEALTH_DUE_SOON:
            due_soon += 1

        if submitted_at is not None and (
            oldest_submitted is None or submitted_at < oldest_submitted
        ):
            oldest_submitted = submitted_at
        if due_by is not None and (next_due is None or due_by < next_due):
            next_due = due_by

    oldest_age_hours: float | None = None
    if oldest_submitted is not None:
        oldest_age_hours = round((now_utc - oldest_submitted).total_seconds() / 3600.0, 1)

    return {
        "pending": pending,
        "overdue": overdue,
        "due_soon": due_soon,
        "oldest_age_hours": oldest_age_hours,
        "sla_hours": sla_hours,
        "next_due_at": next_due.isoformat() if next_due else None,
        "health": queue_health(pending=pending, overdue=overdue, due_soon=due_soon),
    }
