"""Subscription lifecycle state machine, vocabularies, labels, pure predicates.

The subscription lifecycle (ADR-0010 §2) is a small explicit state machine. Only
the transitions in :data:`TRANSITIONS` are legal; everything else raises an
illegal-transition error at the service layer. Manual/bank-transfer payment
(``mark_paid``) is the **single** activation gate — there is no separate approval
state (the simplification vs the ADR-0009 advertising machine).

States (``subscriptions.status``):
    pending   -> requester chose a paid plan; awaiting manual bank-transfer confirm
    active    -> admin recorded payment; inside [start_at, end_at]; plan limits apply
    expired   -> end_at passed (scheduler); reverts to default-plan limits   [terminal]
    cancelled -> requester/admin stopped it (pre/active); reverts to default  [terminal]

Raw enum codes never reach end users — every code is paired with a localized
label. No I/O lives here.
"""

from __future__ import annotations

from datetime import datetime

# --------------------------------------------------------------------------- #
# Status vocabulary                                                           #
# --------------------------------------------------------------------------- #

PENDING = "pending"
ACTIVE = "active"
EXPIRED = "expired"
CANCELLED = "cancelled"

STATUSES: frozenset[str] = frozenset({PENDING, ACTIVE, EXPIRED, CANCELLED})

# A requester may change the chosen plan only while pending (V1 keeps it simpler:
# cancel + re-request instead of edit).
EDITABLE_STATES: frozenset[str] = frozenset({PENDING})
# Soft-deletable states (a never-paid request); an active sub is cancelled.
DELETABLE_STATES: frozenset[str] = frozenset({PENDING})
# Fully terminal states (no further transitions).
TERMINAL_STATES: frozenset[str] = frozenset({EXPIRED, CANCELLED})
# "In flight": occupies the one-in-flight-per-principal uniqueness invariant.
IN_FLIGHT_STATES: frozenset[str] = frozenset({PENDING, ACTIVE})
# Requester/admin may cancel from any non-terminal state.
CANCELLABLE_STATES: frozenset[str] = frozenset({PENDING, ACTIVE})

# --------------------------------------------------------------------------- #
# Transition map: event -> (allowed from-states, to-state)                    #
# --------------------------------------------------------------------------- #

TRANSITIONS: dict[str, tuple[frozenset[str], str]] = {
    "mark_paid": (frozenset({PENDING}), ACTIVE),
    "cancel": (CANCELLABLE_STATES, CANCELLED),
    "expire": (frozenset({ACTIVE}), EXPIRED),
}


def can_transition(event: str, current: str) -> bool:
    """True if ``event`` is legal from the ``current`` status."""

    spec = TRANSITIONS.get(event)
    return spec is not None and current in spec[0]


def target_state(event: str) -> str:
    """The destination status for ``event`` (raises ``KeyError`` if unknown)."""

    return TRANSITIONS[event][1]


def is_active_now(status: str, end_at: datetime | None, now: datetime) -> bool:
    """True iff a subscription is ``active`` and still inside its window.

    ``status == active AND (end_at IS NULL OR end_at > now)``. A NULL ``end_at``
    on an ``active`` row should not happen (the window is set at ``mark_paid``),
    but is treated defensively as "open".
    """

    if status != ACTIVE:
        return False
    return end_at is None or end_at > now


# --------------------------------------------------------------------------- #
# Enumerated field vocabularies                                               #
# --------------------------------------------------------------------------- #

AUDIENCE_STUDENT = "student"
AUDIENCE_PARTNER = "partner"
AUDIENCES: frozenset[str] = frozenset({AUDIENCE_STUDENT, AUDIENCE_PARTNER})

PRINCIPAL_USER = "user"
PRINCIPAL_ORG = "org"
PRINCIPAL_TYPES: frozenset[str] = frozenset({PRINCIPAL_USER, PRINCIPAL_ORG})

PERIOD_MONTHLY = "monthly"
PERIOD_ANNUAL = "annual"
BILLING_PERIODS: frozenset[str] = frozenset({PERIOD_MONTHLY, PERIOD_ANNUAL})

# Which principal kind an audience subscribes as (org for partners, user else).
_AUDIENCE_PRINCIPAL: dict[str, str] = {
    AUDIENCE_STUDENT: PRINCIPAL_USER,
    AUDIENCE_PARTNER: PRINCIPAL_ORG,
}


def principal_kind_for_audience(audience: str) -> str:
    """The principal type (``user``/``org``) that may subscribe to ``audience``."""

    return _AUDIENCE_PRINCIPAL[audience]


def audience_matches_principal(audience: str, *, principal_type: str) -> bool:
    """True if a plan's ``audience`` is subscribable by ``principal_type``."""

    return _AUDIENCE_PRINCIPAL.get(audience) == principal_type


# --------------------------------------------------------------------------- #
# Localized labels (never expose raw enum codes)                              #
# --------------------------------------------------------------------------- #

_STATUS_LABELS: dict[str, dict[str, str]] = {
    "vi": {
        PENDING: "Chờ thanh toán",
        ACTIVE: "Đang hiệu lực",
        EXPIRED: "Đã hết hạn",
        CANCELLED: "Đã hủy",
    },
    "en": {
        PENDING: "Awaiting payment",
        ACTIVE: "Active",
        EXPIRED: "Expired",
        CANCELLED: "Cancelled",
    },
}

_AUDIENCE_LABELS: dict[str, dict[str, str]] = {
    "vi": {AUDIENCE_STUDENT: "Sinh viên", AUDIENCE_PARTNER: "Đối tác"},
    "en": {AUDIENCE_STUDENT: "Student", AUDIENCE_PARTNER: "Partner"},
}

_PERIOD_LABELS: dict[str, dict[str, str]] = {
    "vi": {PERIOD_MONTHLY: "Hàng tháng", PERIOD_ANNUAL: "Hàng năm"},
    "en": {PERIOD_MONTHLY: "Monthly", PERIOD_ANNUAL: "Annual"},
}


def _label(table: dict[str, dict[str, str]], code: str, locale: str) -> str:
    return table.get(locale, table["vi"]).get(code, code)


def status_label(code: str, *, locale: str = "vi") -> str:
    return _label(_STATUS_LABELS, code, locale)


def audience_label(code: str, *, locale: str = "vi") -> str:
    return _label(_AUDIENCE_LABELS, code, locale)


def billing_period_label(code: str, *, locale: str = "vi") -> str:
    return _label(_PERIOD_LABELS, code, locale)
