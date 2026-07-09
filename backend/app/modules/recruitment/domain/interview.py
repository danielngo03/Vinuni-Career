"""Interview domain vocabulary + pure predicates (ADR-0006 §1/§2).

PURE (no I/O): owns the delivery ``mode`` set, the interview ``status`` set, the
``score_threshold`` advance-action token, and the average-vs-threshold predicate the
upgraded ``scorecard_service.evaluate_advance_gate`` composes with the DB read.

The "round/type" of an interview IS the pipeline stage (``stage_type``); the engine
never adds a second interview-type taxonomy (mirrors ADR-0004). The interview
carries only a delivery ``mode``.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Delivery mode — channel only (the round descriptor is pipeline_stages.stage_type)
# --------------------------------------------------------------------------- #

MODE_ONSITE = "onsite"
MODE_ONLINE = "online"
MODE_PHONE = "phone"
MODES: frozenset[str] = frozenset({MODE_ONSITE, MODE_ONLINE, MODE_PHONE})

MODE_LABELS: dict[str, dict[str, str]] = {
    MODE_ONSITE: {"vi": "Trực tiếp", "en": "On-site"},
    MODE_ONLINE: {"vi": "Trực tuyến", "en": "Online"},
    MODE_PHONE: {"vi": "Qua điện thoại", "en": "Phone"},
}

# --------------------------------------------------------------------------- #
# status — editable in place; V1 actively uses scheduled/completed/cancelled/no_show
# --------------------------------------------------------------------------- #

STATUS_SCHEDULED = "scheduled"
STATUS_COMPLETED = "completed"
STATUS_CANCELLED = "cancelled"
STATUS_NO_SHOW = "no_show"
# Reserved for the future cancel-and-replace model (reschedule edits in place today).
STATUS_RESCHEDULED = "rescheduled"

INTERVIEW_STATUSES: frozenset[str] = frozenset(
    {
        STATUS_SCHEDULED,
        STATUS_COMPLETED,
        STATUS_CANCELLED,
        STATUS_NO_SHOW,
        STATUS_RESCHEDULED,
    }
)

# The outcomes a partner may set via /complete.
COMPLETE_OUTCOMES: frozenset[str] = frozenset({STATUS_COMPLETED, STATUS_NO_SHOW})

# --------------------------------------------------------------------------- #
# Candidate self-response (the student confirms / declines / asks to reschedule
# their OWN interview). This is distinct from the partner-owned interview
# ``status`` — it records what the CANDIDATE said, never mutates the partner
# lifecycle. Only meaningful while the interview is still ``scheduled`` + future.
# --------------------------------------------------------------------------- #

CANDIDATE_RESPONSE_CONFIRMED = "confirmed"
CANDIDATE_RESPONSE_DECLINED = "declined"
CANDIDATE_RESPONSE_RESCHEDULE = "reschedule_requested"

CANDIDATE_RESPONSES: frozenset[str] = frozenset(
    {
        CANDIDATE_RESPONSE_CONFIRMED,
        CANDIDATE_RESPONSE_DECLINED,
        CANDIDATE_RESPONSE_RESCHEDULE,
    }
)

# The action tokens the student endpoint accepts -> the persisted response state.
CANDIDATE_ACTION_CONFIRM = "confirm"
CANDIDATE_ACTION_DECLINE = "decline"
CANDIDATE_ACTION_RESCHEDULE = "request_reschedule"

CANDIDATE_ACTIONS: frozenset[str] = frozenset(
    {CANDIDATE_ACTION_CONFIRM, CANDIDATE_ACTION_DECLINE, CANDIDATE_ACTION_RESCHEDULE}
)

CANDIDATE_ACTION_TO_RESPONSE: dict[str, str] = {
    CANDIDATE_ACTION_CONFIRM: CANDIDATE_RESPONSE_CONFIRMED,
    CANDIDATE_ACTION_DECLINE: CANDIDATE_RESPONSE_DECLINED,
    CANDIDATE_ACTION_RESCHEDULE: CANDIDATE_RESPONSE_RESCHEDULE,
}

# Student-facing STATE label for the candidate's own card (never a raw code).
CANDIDATE_RESPONSE_LABELS: dict[str, dict[str, str]] = {
    CANDIDATE_RESPONSE_CONFIRMED: {"vi": "Đã xác nhận tham gia", "en": "Confirmed"},
    CANDIDATE_RESPONSE_DECLINED: {"vi": "Đã từ chối", "en": "Declined"},
    CANDIDATE_RESPONSE_RESCHEDULE: {
        "vi": "Đã yêu cầu đổi lịch",
        "en": "Reschedule requested",
    },
}

# Partner-facing VERB used inside a notification sentence ("The candidate {verb}
# the interview"). Never carries the student's identity.
CANDIDATE_RESPONSE_VERBS: dict[str, dict[str, str]] = {
    CANDIDATE_RESPONSE_CONFIRMED: {"vi": "đã xác nhận tham gia", "en": "confirmed"},
    CANDIDATE_RESPONSE_DECLINED: {"vi": "đã từ chối tham gia", "en": "declined"},
    CANDIDATE_RESPONSE_RESCHEDULE: {
        "vi": "đã yêu cầu đổi lịch",
        "en": "requested to reschedule",
    },
}


def candidate_response_label(code: str | None, *, locale: str = "vi") -> str | None:
    """Localized student-facing state label for a candidate response (or ``None``)."""

    if not code:
        return None
    labels = CANDIDATE_RESPONSE_LABELS.get(code)
    if labels is None:
        return None
    return labels.get(locale, labels["vi"])


def candidate_response_verb(code: str, *, locale: str = "vi") -> str:
    """Localized partner-facing verb for a candidate response (notification copy)."""

    verbs = CANDIDATE_RESPONSE_VERBS.get(code)
    if verbs is None:
        return code
    return verbs.get(locale, verbs["vi"])

# --------------------------------------------------------------------------- #
# Advance-action token (the average-score gate; ADR-0006 §2 / BUSINESS_LOGIC §3.1)
# --------------------------------------------------------------------------- #

ACTION_SCORE_THRESHOLD = "score_threshold"


def avg_threshold_met(avg_overall: float | None, threshold: float | None) -> bool:
    """True if the average evaluator score reaches the stage's threshold.

    A missing average (no scorecards yet) never clears the gate. A missing threshold
    means no average gate is configured -> the count gate alone governs (returns
    ``True`` so the caller falls back to the assignee-count decision).
    """

    if threshold is None:
        return True
    if avg_overall is None:
        return False
    return avg_overall >= threshold
