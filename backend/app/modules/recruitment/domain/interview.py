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
