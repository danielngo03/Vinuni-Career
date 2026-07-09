"""Scorecard domain vocabulary + pure predicates (ADR-0005 §1/§2/§3).

A scorecard is ONE reviewer's evaluation of ONE candidate at ONE pipeline stage:
a fixed V1 criteria set (each scored 1..5), a derived ``overall_score`` (mean), a
required 4-value ``recommendation``, and an optional partner-internal comment.

This module is PURE (no I/O): it owns the criteria/recommendation/status
vocabulary and the advance-gate predicate the service composes with the DB
read-modify-write. Per ADR-0005 §1 the per-job criteria EDITOR is deferred —
``DEFAULT_CRITERIA`` is a domain constant (like ``pipeline.DEFAULT_STAGES``), not
seeded rows, so the future editor maps ``criterion_key -> criterion_id`` with no
data rewrite.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

# --------------------------------------------------------------------------- #
# required_action token this ADR plugs into the stage engine                    #
# --------------------------------------------------------------------------- #

# pipeline.ACTION_MANUAL is the trivial-allow path; ``scorecard`` is the gated
# action ADR-0005 implements. ``score_threshold`` (ADR-0006,
# ``interview.ACTION_SCORE_THRESHOLD``) adds the average-score gate on top of the
# same assignee-count requirement.
ACTION_SCORECARD = "scorecard"

# --------------------------------------------------------------------------- #
# Fixed V1 criteria set (ADR-0005 §1) — the criteria editor is deferred         #
# --------------------------------------------------------------------------- #

DEFAULT_CRITERIA: tuple[dict[str, str], ...] = (
    {"key": "technical", "label_vi": "Năng lực chuyên môn", "label_en": "Technical ability"},
    {"key": "communication", "label_vi": "Giao tiếp", "label_en": "Communication"},
    {"key": "culture_fit", "label_vi": "Phù hợp văn hóa", "label_en": "Culture fit"},
    {"key": "motivation", "label_vi": "Động lực & sự phù hợp", "label_en": "Motivation & fit"},
)

DEFAULT_CRITERION_KEYS: frozenset[str] = frozenset(c["key"] for c in DEFAULT_CRITERIA)

CRITERION_LABELS: dict[str, dict[str, str]] = {
    c["key"]: {"vi": c["label_vi"], "en": c["label_en"]} for c in DEFAULT_CRITERIA
}

SCORE_MIN = 1
SCORE_MAX = 5

# --------------------------------------------------------------------------- #
# recommendation — 4-value enum (PRD §7.3; DATA_MODEL §9 ``neutral`` superseded) #
# --------------------------------------------------------------------------- #

# Ordered worst -> best (stable summary key order; the advance signal).
RECOMMENDATION_ORDER: tuple[str, ...] = ("strong_no", "no", "yes", "strong_yes")
RECOMMENDATIONS: frozenset[str] = frozenset(RECOMMENDATION_ORDER)

RECOMMENDATION_LABELS: dict[str, dict[str, str]] = {
    "strong_no": {"vi": "Hoàn toàn không phù hợp", "en": "Strongly do not recommend"},
    "no": {"vi": "Không phù hợp", "en": "Do not recommend"},
    "yes": {"vi": "Phù hợp", "en": "Recommend"},
    "strong_yes": {"vi": "Rất phù hợp", "en": "Strongly recommend"},
}

# --------------------------------------------------------------------------- #
# status — editable-in-place by author; withdraw is a soft transition           #
# --------------------------------------------------------------------------- #

SCORECARD_SUBMITTED = "submitted"
SCORECARD_WITHDRAWN = "withdrawn"
SCORECARD_STATUSES: frozenset[str] = frozenset({SCORECARD_SUBMITTED, SCORECARD_WITHDRAWN})

# --------------------------------------------------------------------------- #
# Advance gate — V1 fixes ``required = 1`` (assignee/threshold model deferred)   #
# --------------------------------------------------------------------------- #

# ADR-0005 §3: until the assignee model lands (ADR-0006) a scorecard-gated stage
# advances on AT LEAST ONE submitted (non-withdrawn) scorecard.
GATE_REQUIRED_DEFAULT = 1


# Actions whose advance gate is governed by submitted scorecards. ADR-0006 makes
# ``required`` assignee-derived (all assigned interviewers must submit) and adds the
# ``score_threshold`` average gate on top of the same count requirement. Both share
# the ADR-0005 fallback ``required = 1`` when a stage has no interview/assignees.
_SCORECARD_GATED_ACTIONS: frozenset[str] = frozenset({ACTION_SCORECARD, "score_threshold"})


@dataclass(frozen=True, slots=True)
class AdvanceGate:
    """Whether a stage's scorecard gate is met (pure value object).

    ADR-0006 adds the optional ``avg_overall`` / ``threshold`` / ``reason`` fields so
    one value object carries BOTH failure modes: a count failure
    (``reason='scorecard_required'``) and an average failure
    (``reason='score_below_threshold'``).
    """

    allowed: bool
    submitted: int
    required: int
    avg_overall: float | None = None
    threshold: float | None = None
    reason: str | None = None


def required_for_action(required_action: str) -> int:
    """Fallback scorecards required to advance OUT of a stage with this action.

    ``scorecard`` / ``score_threshold`` require at least one submitted scorecard
    (``required = 1``) when the stage has no interview/assignees; the assignee-aware
    service overrides this with ``len(assignees)`` when an open interview exists.
    Every other action contributes no scorecard requirement (``0``).
    """

    return GATE_REQUIRED_DEFAULT if required_action in _SCORECARD_GATED_ACTIONS else 0


def gate_met(submitted_count: int, required: int) -> bool:
    """True if enough submitted scorecards exist to clear the advance gate."""

    return submitted_count >= required


def is_valid_score(value: object) -> bool:
    """A criterion score is an int in ``[1, 5]`` (``bool`` is rejected)."""

    return (
        isinstance(value, int) and not isinstance(value, bool) and SCORE_MIN <= value <= SCORE_MAX
    )


def overall_of(scores: dict[str, int]) -> Decimal | None:
    """Derived overall = mean of the criterion scores, quantized to 1 decimal.

    Returns ``None`` for an empty score set (defensive; the service requires the
    full ``DEFAULT_CRITERIA`` set so this is never ``None`` in practice).
    """

    if not scores:
        return None
    total = sum(scores.values())
    mean = Decimal(total) / Decimal(len(scores))
    return mean.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
