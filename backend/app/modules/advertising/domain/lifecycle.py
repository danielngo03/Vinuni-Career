"""Placement lifecycle state machine, vocabularies, labels, and pure predicates.

The sponsored-placement lifecycle (ADR-0009 §3) is a small explicit state machine.
Only the transitions in :data:`TRANSITIONS` are legal; everything else raises an
illegal-transition error at the service layer. University approval (disclosure +
spend oversight) and admin manual payment are both preconditions to ``active``.

States (``sponsored_placements.status``):
    draft            -> partner editing the request; never public
    pending_approval -> submitted; university reviews disclosure + spend
    approved         -> approved; awaiting payment + window
    active           -> paid AND inside [start_at, end_at]; target flag(s) ON
    completed        -> end_at passed; target flag(s) OFF                 [terminal]
    rejected         -> university rejected; editable + resubmittable    [terminal-ish]
    cancelled        -> partner/university stopped it; flag(s) OFF        [terminal]

Raw enum codes never reach end users — every code is paired with a localized label.
No I/O lives here.
"""

from __future__ import annotations

from datetime import datetime

# --------------------------------------------------------------------------- #
# Status vocabulary                                                           #
# --------------------------------------------------------------------------- #

DRAFT = "draft"
PENDING_APPROVAL = "pending_approval"
APPROVED = "approved"
ACTIVE = "active"
COMPLETED = "completed"
REJECTED = "rejected"
CANCELLED = "cancelled"

STATUSES: frozenset[str] = frozenset(
    {DRAFT, PENDING_APPROVAL, APPROVED, ACTIVE, COMPLETED, REJECTED, CANCELLED}
)

# Partner may PATCH a request only in these states.
EDITABLE_STATES: frozenset[str] = frozenset({DRAFT, REJECTED})
# Soft-deletable states (an approved/active placement must be cancelled, not deleted).
DELETABLE_STATES: frozenset[str] = frozenset({DRAFT, REJECTED})
# Fully terminal states (no further transitions).
TERMINAL_STATES: frozenset[str] = frozenset({COMPLETED, CANCELLED})
# "In flight": occupies the per-target uniqueness + per-org concurrency cap.
IN_FLIGHT_STATES: frozenset[str] = frozenset({PENDING_APPROVAL, APPROVED, ACTIVE})
# Partner may cancel from any pre-completed, non-terminal state.
CANCELLABLE_STATES: frozenset[str] = frozenset({DRAFT, PENDING_APPROVAL, APPROVED, ACTIVE})

# --------------------------------------------------------------------------- #
# Transition map: event -> (allowed from-states, to-state)                    #
# --------------------------------------------------------------------------- #

TRANSITIONS: dict[str, tuple[frozenset[str], str]] = {
    "submit": (frozenset({DRAFT, REJECTED}), PENDING_APPROVAL),
    "approve": (frozenset({PENDING_APPROVAL}), APPROVED),
    "reject": (frozenset({PENDING_APPROVAL}), REJECTED),
    "activate": (frozenset({APPROVED}), ACTIVE),
    "complete": (frozenset({ACTIVE, APPROVED}), COMPLETED),
    "cancel": (CANCELLABLE_STATES, CANCELLED),
}


def can_transition(event: str, current: str) -> bool:
    """True if ``event`` is legal from the ``current`` status."""

    spec = TRANSITIONS.get(event)
    return spec is not None and current in spec[0]


def target_state(event: str) -> str:
    """The destination status for ``event`` (raises ``KeyError`` if unknown)."""

    return TRANSITIONS[event][1]


# --------------------------------------------------------------------------- #
# Enumerated field vocabularies                                               #
# --------------------------------------------------------------------------- #

TARGET_JOB = "job"
TARGET_EVENT = "event"
TARGET_TYPES: frozenset[str] = frozenset({TARGET_JOB, TARGET_EVENT})

PLACEMENT_SPONSORED = "sponsored"
PLACEMENT_FEATURED = "featured"
PLACEMENT_BOTH = "both"
PLACEMENT_TYPES: frozenset[str] = frozenset(
    {PLACEMENT_SPONSORED, PLACEMENT_FEATURED, PLACEMENT_BOTH}
)


def grants_sponsored(placement_type: str) -> bool:
    return placement_type in (PLACEMENT_SPONSORED, PLACEMENT_BOTH)


def grants_featured(placement_type: str) -> bool:
    return placement_type in (PLACEMENT_FEATURED, PLACEMENT_BOTH)


def package_allows(
    placement_type: str, *, pkg_grants_sponsored: bool, pkg_grants_featured: bool
) -> bool:
    """True if a package granting the given flags can back ``placement_type``.

    A ``featured``-only package cannot back a ``sponsored`` (or ``both``) request,
    and vice-versa (ADR-0009 §5).
    """

    if grants_sponsored(placement_type) and not pkg_grants_sponsored:
        return False
    if grants_featured(placement_type) and not pkg_grants_featured:  # noqa: SIM103
        return False
    return True


# --------------------------------------------------------------------------- #
# Activation / flag predicates (pure)                                         #
# --------------------------------------------------------------------------- #


def can_activate(
    *,
    status: str,
    paid_at: datetime | None,
    start_at: datetime,
    end_at: datetime,
    now: datetime,
) -> bool:
    """True iff an ``approved`` placement is paid and inside its window.

    ``status == approved AND paid_at IS NOT NULL AND start_at <= now < end_at``.
    """

    return status == APPROVED and paid_at is not None and start_at <= now < end_at


def compute_target_flags(active_placement_types: list[str]) -> tuple[bool, bool]:
    """Desired ``(is_sponsored, is_featured)`` for a target from its ACTIVE placements.

    ``is_sponsored`` = any active placement grants sponsored; ``is_featured`` = any
    active placement grants featured. With no active placement both are ``False``
    (recompute on completion/cancel turns the flag off only when nothing else
    covers the target).
    """

    is_sponsored = any(grants_sponsored(p) for p in active_placement_types)
    is_featured = any(grants_featured(p) for p in active_placement_types)
    return is_sponsored, is_featured


# --------------------------------------------------------------------------- #
# Localized labels (never expose raw enum codes)                              #
# --------------------------------------------------------------------------- #

_STATUS_LABELS: dict[str, dict[str, str]] = {
    "vi": {
        DRAFT: "Bản nháp",
        PENDING_APPROVAL: "Chờ duyệt",
        APPROVED: "Đã duyệt",
        ACTIVE: "Đang chạy",
        COMPLETED: "Đã hoàn tất",
        REJECTED: "Bị từ chối",
        CANCELLED: "Đã hủy",
    },
    "en": {
        DRAFT: "Draft",
        PENDING_APPROVAL: "Pending approval",
        APPROVED: "Approved",
        ACTIVE: "Active",
        COMPLETED: "Completed",
        REJECTED: "Rejected",
        CANCELLED: "Cancelled",
    },
}

_PLACEMENT_LABELS: dict[str, dict[str, str]] = {
    "vi": {
        PLACEMENT_SPONSORED: "Được tài trợ",
        PLACEMENT_FEATURED: "Nổi bật",
        PLACEMENT_BOTH: "Tài trợ + Nổi bật",
    },
    "en": {
        PLACEMENT_SPONSORED: "Sponsored",
        PLACEMENT_FEATURED: "Featured",
        PLACEMENT_BOTH: "Sponsored + Featured",
    },
}

_TARGET_LABELS: dict[str, dict[str, str]] = {
    "vi": {TARGET_JOB: "Tin tuyển dụng", TARGET_EVENT: "Sự kiện"},
    "en": {TARGET_JOB: "Job", TARGET_EVENT: "Event"},
}


def _label(table: dict[str, dict[str, str]], code: str, locale: str) -> str:
    return table.get(locale, table["vi"]).get(code, code)


def status_label(code: str, *, locale: str = "vi") -> str:
    return _label(_STATUS_LABELS, code, locale)


def placement_type_label(code: str, *, locale: str = "vi") -> str:
    return _label(_PLACEMENT_LABELS, code, locale)


def target_type_label(code: str, *, locale: str = "vi") -> str:
    return _label(_TARGET_LABELS, code, locale)
