"""Pure domain logic for company reviews (no I/O) — ADR-0013.

Owns the review status vocabulary, eligibility classes, content validators, and
the Bayesian aggregate scorer. All raw codes here are internal; user-facing labels
live in :mod:`.labels`.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal

# --------------------------------------------------------------------------- #
# Status vocabulary (slice-1 = pre-moderation: pending -> human published)     #
# --------------------------------------------------------------------------- #
STATUS_PENDING = "pending"
STATUS_PUBLISHED = "published"
STATUS_FLAGGED = "flagged"
STATUS_REMOVED = "removed"

ALL_STATUSES: frozenset[str] = frozenset(
    {STATUS_PENDING, STATUS_PUBLISHED, STATUS_FLAGGED, STATUS_REMOVED}
)
# Only published reviews are publicly visible and counted in the aggregate.
PUBLIC_STATUSES: frozenset[str] = frozenset({STATUS_PUBLISHED})

# --------------------------------------------------------------------------- #
# Eligibility classes (frozen at submit). Strength order strongest -> weakest. #
# --------------------------------------------------------------------------- #
ELIG_OFFER = "system_verified_offer"
ELIG_INTERVIEW = "system_verified_interview"
ELIG_SELF = "self_declared"
ELIG_PARTNER = "partner_verified"

# Slice-1 accepts only system-verified eligibility (ADR-0013 open-Q #1 resolved
# to verified-only). self_declared / partner_verified are reserved for later.
ACCEPTED_ELIGIBILITY: frozenset[str] = frozenset({ELIG_OFFER, ELIG_INTERVIEW})

# Report reason codes (review_reports.reason_code).
REPORT_REASONS: frozenset[str] = frozenset(
    {"pii", "harassment", "spam", "false_claim", "other"}
)

# Removal reasons a moderator may use — maps to BUSINESS_LOGIC §7.3 allowed
# criteria. A genuinely negative opinion is NOT a valid removal ground, so the
# service rejects any reason outside this set (policy-gated at the service layer).
REMOVAL_REASONS: frozenset[str] = frozenset(
    {"pii", "harassment", "discrimination", "spam", "off_topic", "false_claim"}
)

# Content bounds (service-enforced; CHECK on ratings is in the migration).
BODY_MIN = 50
BODY_MAX = 5000
TITLE_MAX = 300
RATING_CATEGORIES: tuple[str, ...] = (
    "overall",
    "work_life_balance",
    "culture_values",
    "compensation",
    "career_growth",
)

# Bayesian prior (BUSINESS_LOGIC §7.2): pull toward 3.0 with weight 3 reviews.
_PRIOR_MEAN = Decimal("3.0")
_PRIOR_WEIGHT = 3


def is_rating(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 5


def _round2(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def bayesian_average(values: Sequence[int]) -> float | None:
    """Bayesian-smoothed mean of overall scores, or ``None`` for an empty set.

    ``(n·avg + W·prior) / (n + W)`` with prior 3.0 / weight 3, so a single 5-star
    review does not read as a perfect company.
    """

    n = len(values)
    if n == 0:
        return None
    total = Decimal(sum(values))
    score = (total + _PRIOR_MEAN * _PRIOR_WEIGHT) / Decimal(n + _PRIOR_WEIGHT)
    return _round2(score)


def simple_average(values: Sequence[int | None]) -> float | None:
    """Plain mean of the non-null values, or ``None`` if all are null/empty."""

    present = [v for v in values if v is not None]
    if not present:
        return None
    return _round2(Decimal(sum(present)) / Decimal(len(present)))


def distribution(values: Sequence[int]) -> dict[str, int]:
    """``{"5": n, "4": n, ...}`` star histogram for the published reviews."""

    out = {str(star): 0 for star in range(5, 0, -1)}
    for v in values:
        key = str(v)
        if key in out:
            out[key] += 1
    return out
