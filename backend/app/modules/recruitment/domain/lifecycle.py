"""Application lifecycle vocabulary + localized labels (Phase 1.5 decision subset).

The full configurable pipeline (``screening`` -> ``interview`` -> ``offer`` -> ...)
of ``docs/DATA_MODEL.md`` §9 and ``docs/BUSINESS_LOGIC.md`` §3 (stages, scorecards,
auto-advance, ``/advance`` / ``/rollback``) stays Phase 2. This module ships the
minimal decision loop a recruiter actually needs now:

    submitted     -> just submitted, awaiting partner triage
    under_review  -> partner has started reviewing (active; partner-driven)
    rejected      -> partner rejected the application (terminal/inactive)
    withdrawn     -> applicant withdrew (terminal/inactive)

Decision graph (events): ``review`` (``submitted -> under_review``) and ``reject``
(``{submitted, under_review} -> rejected``). ``under_review`` is still an ACTIVE
status (occupies the single active slot); ``rejected``/``withdrawn`` are inactive,
so rejecting frees the slot and the student may re-apply.

Raw enum codes never reach end users — every status is paired with a localized
label, and the anonymous-reveal status is likewise localized. The internal
``rejection_reason`` code is partner/owner-only and never surfaced to the student.
"""

from __future__ import annotations

SUBMITTED = "submitted"
UNDER_REVIEW = "under_review"
WITHDRAWN = "withdrawn"
REJECTED = "rejected"
# Terminal POSITIVE outcome — set when a sent offer is accepted (ADR-0007 §4). A
# pure domain widening: ``applications.status`` is already VARCHAR(30) so no DDL is
# needed. ``hired`` is the positive sibling of ``rejected`` (terminal + inactive).
HIRED = "hired"

STATUSES: frozenset[str] = frozenset(
    {SUBMITTED, UNDER_REVIEW, WITHDRAWN, REJECTED, HIRED}
)

# Statuses that occupy the single "active application per (job, applicant)" slot.
# ``hired`` is terminal/inactive (NOT here) — it frees the slot like rejected/withdrawn.
ACTIVE_STATUSES: frozenset[str] = frozenset({SUBMITTED, UNDER_REVIEW})

# Statuses a student may withdraw from.
WITHDRAWABLE_STATES: frozenset[str] = frozenset({SUBMITTED, UNDER_REVIEW})

# --------------------------------------------------------------------------- #
# Partner decision transition map: event -> (allowed from-states, to-state)    #
# --------------------------------------------------------------------------- #

REVIEW = "review"
REJECT = "reject"

DECISION_TRANSITIONS: dict[str, tuple[frozenset[str], str]] = {
    REVIEW: (frozenset({SUBMITTED}), UNDER_REVIEW),
    REJECT: (frozenset({SUBMITTED, UNDER_REVIEW}), REJECTED),
}


def can_decision_transition(event: str, current: str) -> bool:
    """True if the partner decision ``event`` is legal from the ``current`` status."""

    spec = DECISION_TRANSITIONS.get(event)
    return spec is not None and current in spec[0]


def decision_target(event: str) -> str:
    """Destination status for a decision ``event`` (raises ``KeyError`` if unknown)."""

    return DECISION_TRANSITIONS[event][1]


# Coded rejection reasons (partner-only; never sent to the student). The Pydantic
# request schema enforces this set so an invalid/missing code is a ``422``.
REJECTION_REASONS: frozenset[str] = frozenset(
    {"not_qualified", "experience_mismatch", "position_filled", "incomplete", "other"}
)

# Reveal-request vocabulary.
REVEAL_PENDING = "pending"
REVEAL_ACCEPTED = "accepted"
REVEAL_DECLINED = "declined"
REVEAL_EXPIRED = "expired"

REVEAL_TTL_HOURS = 72

_STATUS_LABELS: dict[str, dict[str, str]] = {
    "vi": {
        SUBMITTED: "Đã nộp",
        UNDER_REVIEW: "Đang xem xét",
        WITHDRAWN: "Đã rút",
        REJECTED: "Không phù hợp",
        HIRED: "Đã được tuyển",
    },
    "en": {
        SUBMITTED: "Submitted",
        UNDER_REVIEW: "Under review",
        WITHDRAWN: "Withdrawn",
        REJECTED: "Not selected",
        HIRED: "Hired",
    },
}

_REVEAL_LABELS: dict[str, dict[str, str]] = {
    "vi": {
        REVEAL_PENDING: "Đang chờ phản hồi",
        REVEAL_ACCEPTED: "Đã chấp nhận",
        REVEAL_DECLINED: "Đã từ chối",
        REVEAL_EXPIRED: "Đã hết hạn",
    },
    "en": {
        REVEAL_PENDING: "Awaiting response",
        REVEAL_ACCEPTED: "Accepted",
        REVEAL_DECLINED: "Declined",
        REVEAL_EXPIRED: "Expired",
    },
}


def _label(table: dict[str, dict[str, str]], code: str, locale: str) -> str:
    return table.get(locale, table["vi"]).get(code, code)


def status_label(code: str, *, locale: str = "vi") -> str:
    return _label(_STATUS_LABELS, code, locale)


def reveal_label(code: str, *, locale: str = "vi") -> str:
    return _label(_REVEAL_LABELS, code, locale)
