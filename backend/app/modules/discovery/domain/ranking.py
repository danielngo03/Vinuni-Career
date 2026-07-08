"""Pure organic-relevance math + source/reason vocabularies + slot composition.

This is the load-bearing *policy* of the recommendation layer, kept pure (no I/O,
no ORM) so it is fully deterministic and unit-testable. The service layer feeds it
already-loaded candidate data + signals; this module decides scores, the honest
``source`` label, diversity, and how sponsored inventory fills *defined slots
without ever reordering organic relevance* (spec §5).

Honesty contract enforced here:

- A list is only labelled ``recommended`` when there is a real personalization
  signal (``has_signal``). With no signal the caller uses an explicit fallback
  ``source`` (``recent`` / ``popular``) — never a silent "recommended" mislabel.
- Sponsored items occupy ``SPONSORED_SLOTS`` positions ONLY; the organic
  subsequence keeps its exact relevance order (``inject_sponsored`` never permutes
  organic items relative to each other).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

# --------------------------------------------------------------------------- #
# Source values (the inventory class of a ranked item / list)                 #
# --------------------------------------------------------------------------- #

SOURCE_RECOMMENDED = "recommended"  # genuine session/profile/CV/query signal
SOURCE_RECENT = "recent"            # honest fallback: newest eligible inventory
SOURCE_POPULAR = "popular"          # honest fallback: most-applied/-viewed
SOURCE_SPONSORED = "sponsored"      # paid inventory filling a defined slot
SOURCE_CURATED = "curated"          # university-curated inventory

SOURCES: frozenset[str] = frozenset(
    {
        SOURCE_RECOMMENDED,
        SOURCE_RECENT,
        SOURCE_POPULAR,
        SOURCE_SPONSORED,
        SOURCE_CURATED,
    }
)

# --------------------------------------------------------------------------- #
# Reason codes (user-safe coded reasons; the frontend localizes them)         #
# --------------------------------------------------------------------------- #

REASON_CV_FIT = "cv_fit"                    # {score, cv_id, cv_title}
REASON_PREFERRED_JOB_TYPE = "preferred_job_type"   # {value}
REASON_PREFERRED_LOCATION = "preferred_location"   # {value}
REASON_PREFERRED_FIELD = "preferred_field"         # {value}
REASON_MATCHES_SEARCH = "matches_search"    # {term}
REASON_SIMILAR_ROLE = "similar_role"        # {} viewed similar role family
REASON_SIMILAR_INDUSTRY = "similar_industry"  # {value}
REASON_SKILL_MATCH = "skill_match"          # {skills: [...]}
REASON_SAVED_AFFINITY = "saved_affinity"    # {} similar to a job you saved
REASON_VERIFIED_EMPLOYER = "verified_employer"  # {}
REASON_DEADLINE_SOON = "deadline_soon"      # {days}
REASON_POPULAR = "popular"                  # {}
REASON_RECENT = "recent"                    # {}

REASON_CODES: frozenset[str] = frozenset(
    {
        REASON_CV_FIT,
        REASON_PREFERRED_JOB_TYPE,
        REASON_PREFERRED_LOCATION,
        REASON_PREFERRED_FIELD,
        REASON_MATCHES_SEARCH,
        REASON_SIMILAR_ROLE,
        REASON_SIMILAR_INDUSTRY,
        REASON_SKILL_MATCH,
        REASON_SAVED_AFFINITY,
        REASON_VERIFIED_EMPLOYER,
        REASON_DEADLINE_SOON,
        REASON_POPULAR,
        REASON_RECENT,
    }
)

# How many reason codes to surface per item (most-important first).
MAX_REASONS = 3
# Sponsored slot positions in the composed list (0-indexed). Sponsored items fill
# THESE positions only; organic items keep their relative order around them.
SPONSORED_SLOTS: tuple[int, ...] = (0, 4)
# Thresholds.
CV_FIT_REASON_MIN = 55       # only claim cv_fit above this product score
POPULAR_REASON_MIN = 5       # application_count at/above this earns a popular reason
DEADLINE_SOON_DAYS = 7       # apply window closing within N days
RECENCY_WINDOW_DAYS = 30.0   # recency decays to 0 over this many days
POPULARITY_NORM = 10.0       # application_count that saturates the popularity term

# --------------------------------------------------------------------------- #
# Component weights (renormalized over the components actually present)        #
# --------------------------------------------------------------------------- #

_W_QUERY = 0.30
_W_CV = 0.28
_W_PREFERENCE = 0.14
_W_SESSION = 0.16
_W_SAVED = 0.12
_W_RECENCY = 0.10
_W_EMPLOYER = 0.05
_W_POPULARITY = 0.08


@dataclass(frozen=True, slots=True)
class Components:
    """Sub-scores in [0,1]. ``None`` = signal not available for this request."""

    recency: float
    employer: float
    popularity: float
    query: float | None = None
    cv: float | None = None
    preference: float | None = None
    session: float | None = None
    saved: float | None = None


# Guest-session taxonomy-signal weighting (frequency + recency), applied to the
# per-value ``{count, last_seen}`` coarse tags before they enter the ranker's
# session component. A value viewed many times out-weighs a one-off; a stale value
# time-decays so a month-old glance no longer counts as a fresh, live interest.
SESSION_SIGNAL_HALF_LIFE_DAYS = 7.0   # weight halves every 7 idle days
_SESSION_FREQ_LOG_NORM = math.log1p(20.0)  # ~20 views saturate the frequency term


def session_signal_weight(count: int, age_days: float | None) -> float:
    """Frequency- and recency-weighted strength of a coarse session signal, in [0,1].

    ``count`` uses diminishing (log) returns so a value viewed 20× clearly out-weighs
    one viewed once without letting a single burst dominate unbounded; ``age_days``
    applies an exponential half-life decay so a stale value fades. ``age_days=None``
    (legacy presence-only rows with no ``last_seen``) applies NO decay, preserving
    prior behaviour for pre-migration sessions.
    """

    c = max(1, count)
    freq = min(1.0, math.log1p(c) / _SESSION_FREQ_LOG_NORM)
    if age_days is None or age_days <= 0:
        return freq
    decay = 0.5 ** (age_days / SESSION_SIGNAL_HALF_LIFE_DAYS)
    return freq * decay


def recency_score(days_since_published: float | None) -> float:
    """Linear decay to 0 over :data:`RECENCY_WINDOW_DAYS`."""

    if days_since_published is None:
        return 0.0
    return max(0.0, 1.0 - (days_since_published / RECENCY_WINDOW_DAYS))


def popularity_score(application_count: int) -> float:
    return min(1.0, max(0, application_count) / POPULARITY_NORM)


def employer_score(is_verified: bool) -> float:
    return 1.0 if is_verified else 0.5


def product_score(c: Components) -> int:
    """Weighted blend of the present components, renormalized to a 0-100 int."""

    pairs = [
        (_W_RECENCY, c.recency),
        (_W_EMPLOYER, c.employer),
        (_W_POPULARITY, c.popularity),
        (_W_QUERY, c.query),
        (_W_CV, c.cv),
        (_W_PREFERENCE, c.preference),
        (_W_SESSION, c.session),
        (_W_SAVED, c.saved),
    ]
    present = [(w, s) for (w, s) in pairs if s is not None]
    total_w = sum(w for w, _ in present)
    if total_w <= 0:
        return 0
    blended = sum(w * s for w, s in present) / total_w
    return max(0, min(100, round(blended * 100)))


def has_signal(
    *,
    query: float | None,
    cv: float | None,
    preference: float | None,
    session: float | None,
    saved: float | None = None,
) -> bool:
    """True when ANY genuine personalization signal is present for the request.

    Drives the honest ``recommended`` vs ``recent``/``popular`` label: with no
    signal the list must NOT call itself "recommended".
    """

    return any(s is not None for s in (query, cv, preference, session, saved))


# --------------------------------------------------------------------------- #
# Diversity + sponsored slot composition (generic over the item type)         #
# --------------------------------------------------------------------------- #


def diversify[T](items: list[T], *, group_of: Callable[[T], object]) -> list[T]:
    """Reorder a score-sorted list to avoid the same group back-to-back.

    Greedy + deterministic: walks the score-sorted list and, when the next item
    shares the previous item's group, pulls forward the earliest item of a
    different group (if one exists). Overall relevance order is otherwise
    preserved — only adjacent same-group repeats are broken up (spec §5.4).
    """

    remaining = list(items)
    out: list[T] = []
    while remaining:
        idx = 0
        if out:
            last = group_of(out[-1])
            for i, candidate in enumerate(remaining):
                if group_of(candidate) != last:
                    idx = i
                    break
        out.append(remaining.pop(idx))
    return out


def inject_sponsored[T](
    organic: list[T], sponsored: list[T], *, slots: tuple[int, ...] = SPONSORED_SLOTS
) -> list[T]:
    """Compose the final list: sponsored items at ``slots``, organic order intact.

    The organic subsequence of the result is EXACTLY ``organic`` (same items, same
    order) — sponsored items are interleaved at the defined slot positions and
    never displace organic relevance ordering. Extra sponsored items beyond the
    available slots are dropped (only paid slots are filled).
    """

    if not sponsored:
        return list(organic)
    slot_set = set(slots)
    out: list[T] = []
    org_idx = 0
    sp_idx = 0
    pos = 0
    while org_idx < len(organic) or sp_idx < len(sponsored):
        if pos in slot_set and sp_idx < len(sponsored):
            out.append(sponsored[sp_idx])
            sp_idx += 1
        elif org_idx < len(organic):
            out.append(organic[org_idx])
            org_idx += 1
        elif sp_idx < len(sponsored):
            out.append(sponsored[sp_idx])
            sp_idx += 1
        pos += 1
    return out
