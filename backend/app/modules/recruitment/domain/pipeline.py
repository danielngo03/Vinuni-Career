"""Pipeline stage-engine vocabulary + pure transition predicates (ADR-0004 §6.2).

The fine pipeline position of an application lives in ``candidate_stages`` (the
append-only stage history); the coarse application outcome stays on
``applications.status`` (``lifecycle.py``) and is unchanged by this engine.

This module is pure (no I/O): it owns the stage/exit vocabulary, the seeded
default ladder, and the legal-transition predicates the service composes with the
DB read-modify-write. The engine branches on ``sort_order`` + ``required_action``
only — never on ``stage_type`` (which is UI/notification metadata).
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# candidate_stages.status — one ACTIVE row per application; exits are terminal  #
# --------------------------------------------------------------------------- #

STAGE_ACTIVE = "ACTIVE"
STAGE_PASSED = "PASSED"
STAGE_ROLLED_BACK = "ROLLED_BACK"
STAGE_REJECTED = "REJECTED"

STAGE_STATUSES: frozenset[str] = frozenset(
    {STAGE_ACTIVE, STAGE_PASSED, STAGE_ROLLED_BACK, STAGE_REJECTED}
)

# candidate_stages.exit_kind — how an ACTIVE row was closed.
EXIT_ADVANCED = "advanced"
EXIT_ROLLED_BACK = "rolled_back"
EXIT_REJECTED = "rejected"
# Offer accepted at the (last) Offer stage -> the open row closes PASSED with this
# exit kind (ADR-0007 §4). No new stage row is appended (Offer is terminal).
EXIT_HIRED = "hired"

# required_action — V1 only ships ``manual`` (always satisfied). ``scorecard`` /
# ``score_threshold`` gating of /advance is ADR-0005.
ACTION_MANUAL = "manual"

# stage_type — coarse DATA_MODEL §9 set; metadata for labeling only.
STAGE_TYPES: frozenset[str] = frozenset(
    {"screening", "interview", "assessment", "offer", "custom"}
)

# A rollback reason is partner-internal (audit + partner projection) and must be
# meaningful (ARCHITECTURE §4.1 / BUSINESS_LOGIC §3.5).
ROLLBACK_REASON_MIN_LEN = 20

# Max rollbacks per application; the 4th needs university-admin approval
# (BUSINESS_LOGIC §3.5 — approval workflow deferred, V1 just blocks the 4th).
MAX_ROLLBACKS = 3


# --------------------------------------------------------------------------- #
# Seeded system-default ladder (ADR-0004 §1)                                   #
# --------------------------------------------------------------------------- #
#
# Canonical 3-stage ladder Screening -> Interview -> Offer, all manual, all
# candidate-visible. Names are the canonical (vi) labels; student notifications
# use neutral generic copy and never surface the raw stage name, so a single
# stored name is sufficient for V1.

DEFAULT_TEMPLATE_NAME = "Quy trình tuyển dụng mặc định"

DEFAULT_STAGES: tuple[dict[str, object], ...] = (
    {
        "name": "Sàng lọc hồ sơ",
        "stage_type": "screening",
        "sort_order": 1,
        "required_action": ACTION_MANUAL,
        "is_terminal": False,
        "candidate_visible": True,
    },
    {
        "name": "Phỏng vấn",
        "stage_type": "interview",
        "sort_order": 2,
        "required_action": ACTION_MANUAL,
        "is_terminal": False,
        "candidate_visible": True,
    },
    {
        "name": "Đề nghị",
        "stage_type": "offer",
        "sort_order": 3,
        "required_action": ACTION_MANUAL,
        "is_terminal": True,
        "candidate_visible": True,
    },
)


# --------------------------------------------------------------------------- #
# Pure transition predicates                                                   #
# --------------------------------------------------------------------------- #


def can_advance(current_order: int, max_order: int) -> bool:
    """True if there is a next stage to advance into (not already at the last)."""

    return current_order < max_order


def can_rollback(target_order: int, current_order: int) -> bool:
    """True if ``target_order`` is a STRICTLY prior stage of the same template."""

    return target_order < current_order


def rollback_limit_reached(rollback_count: int) -> bool:
    """True if this application has already used its allotted rollbacks."""

    return rollback_count >= MAX_ROLLBACKS


def action_satisfied(required_action: str) -> bool:
    """Whether a stage's required action is met for /advance (V1: only manual)."""

    # V1 ships only ``manual`` (always satisfied). scorecard/score_threshold
    # gating is ADR-0005; an unknown future action blocks (fail-closed).
    return required_action == ACTION_MANUAL


def is_terminal_status(status: str) -> bool:
    """A closed (non-ACTIVE) candidate-stage row is terminal/history."""

    return status != STAGE_ACTIVE
