"""Offer domain vocabulary + pure transition predicates (ADR-0007 §1).

PURE (no I/O): owns the 8-state offer machine, the transition map (event ->
allowed-from -> to), the LIVE / TERMINAL / EDITABLE status sets, the candidate
``respond`` decision tokens, and the localized status labels. The service composes
:func:`can_transition` with the DB read-modify-write.

The offer is the terminal POSITIVE outcome of the pipeline — the only path to
``applications.status='hired'`` (``lifecycle.HIRED``). At most one LIVE offer exists
per application at a time (LIVE = ``draft | pending_approval | approved | sent``); a
Postgres partial-unique index plus the service guard enforce that invariant.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# offers.status — the 8-state machine                                          #
# --------------------------------------------------------------------------- #

STATUS_DRAFT = "draft"
STATUS_PENDING_APPROVAL = "pending_approval"
STATUS_APPROVED = "approved"
STATUS_SENT = "sent"
STATUS_ACCEPTED = "accepted"
STATUS_DECLINED = "declined"
STATUS_EXPIRED = "expired"
STATUS_RESCINDED = "rescinded"

OFFER_STATUSES: frozenset[str] = frozenset(
    {
        STATUS_DRAFT,
        STATUS_PENDING_APPROVAL,
        STATUS_APPROVED,
        STATUS_SENT,
        STATUS_ACCEPTED,
        STATUS_DECLINED,
        STATUS_EXPIRED,
        STATUS_RESCINDED,
    }
)

# Non-terminal / LIVE — at most one per application (partial-unique + service guard).
LIVE_STATUSES: frozenset[str] = frozenset(
    {STATUS_DRAFT, STATUS_PENDING_APPROVAL, STATUS_APPROVED, STATUS_SENT}
)

# Terminal — the offer is closed; no further transition is legal.
TERMINAL_STATUSES: frozenset[str] = frozenset(
    {STATUS_ACCEPTED, STATUS_DECLINED, STATUS_EXPIRED, STATUS_RESCINDED}
)

# Content is mutable in place ONLY while ``draft`` (content frozen at submit, §1).
EDITABLE_STATUSES: frozenset[str] = frozenset({STATUS_DRAFT})

# States visible to the student (draft / pending_approval / approved are
# partner-internal and never listed to or surfaced for the candidate).
STUDENT_VISIBLE_STATUSES: frozenset[str] = frozenset(
    {STATUS_SENT, STATUS_ACCEPTED, STATUS_DECLINED, STATUS_EXPIRED, STATUS_RESCINDED}
)

# --------------------------------------------------------------------------- #
# Transition map: event -> (allowed from-states, to-state)                     #
# --------------------------------------------------------------------------- #

EVENT_SUBMIT = "submit"
EVENT_APPROVE = "approve"
EVENT_REJECT = "reject"
EVENT_SEND = "send"
EVENT_ACCEPT = "accept"
EVENT_DECLINE = "decline"
EVENT_EXPIRE = "expire"
EVENT_RESCIND = "rescind"

TRANSITIONS: dict[str, tuple[frozenset[str], str]] = {
    EVENT_SUBMIT: (frozenset({STATUS_DRAFT}), STATUS_PENDING_APPROVAL),
    EVENT_APPROVE: (frozenset({STATUS_PENDING_APPROVAL}), STATUS_APPROVED),
    EVENT_REJECT: (frozenset({STATUS_PENDING_APPROVAL}), STATUS_DRAFT),
    EVENT_SEND: (frozenset({STATUS_APPROVED}), STATUS_SENT),
    EVENT_ACCEPT: (frozenset({STATUS_SENT}), STATUS_ACCEPTED),
    EVENT_DECLINE: (frozenset({STATUS_SENT}), STATUS_DECLINED),
    EVENT_EXPIRE: (frozenset({STATUS_SENT}), STATUS_EXPIRED),
    EVENT_RESCIND: (
        frozenset(
            {STATUS_DRAFT, STATUS_PENDING_APPROVAL, STATUS_APPROVED, STATUS_SENT}
        ),
        STATUS_RESCINDED,
    ),
}


def can_transition(event: str, current: str) -> bool:
    """True if the offer ``event`` is legal from the ``current`` status."""

    spec = TRANSITIONS.get(event)
    return spec is not None and current in spec[0]


def transition_target(event: str) -> str:
    """Destination status for ``event`` (raises ``KeyError`` if unknown)."""

    return TRANSITIONS[event][1]


# --------------------------------------------------------------------------- #
# Candidate respond decision tokens                                            #
# --------------------------------------------------------------------------- #

RESPOND_ACCEPTED = "accepted"
RESPOND_DECLINED = "declined"
RESPOND_DECISIONS: frozenset[str] = frozenset({RESPOND_ACCEPTED, RESPOND_DECLINED})

# Approval decision tokens (partner approve gate).
APPROVE_DECISION = "approve"
REJECT_DECISION = "reject"
APPROVE_DECISIONS: frozenset[str] = frozenset({APPROVE_DECISION, REJECT_DECISION})

# Comp defaults.
DEFAULT_CURRENCY = "VND"
DEFAULT_PERIOD = "monthly"

# --------------------------------------------------------------------------- #
# Localized labels (raw codes never reach end users)                           #
# --------------------------------------------------------------------------- #

_STATUS_LABELS: dict[str, dict[str, str]] = {
    "vi": {
        STATUS_DRAFT: "Bản nháp",
        STATUS_PENDING_APPROVAL: "Chờ phê duyệt",
        STATUS_APPROVED: "Đã phê duyệt",
        STATUS_SENT: "Đã gửi",
        STATUS_ACCEPTED: "Đã chấp nhận",
        STATUS_DECLINED: "Đã từ chối",
        STATUS_EXPIRED: "Đã hết hạn",
        STATUS_RESCINDED: "Đã thu hồi",
    },
    "en": {
        STATUS_DRAFT: "Draft",
        STATUS_PENDING_APPROVAL: "Pending approval",
        STATUS_APPROVED: "Approved",
        STATUS_SENT: "Sent",
        STATUS_ACCEPTED: "Accepted",
        STATUS_DECLINED: "Declined",
        STATUS_EXPIRED: "Expired",
        STATUS_RESCINDED: "Rescinded",
    },
}

_PERIOD_LABELS: dict[str, dict[str, str]] = {
    "vi": {"monthly": "tháng", "yearly": "năm", "hourly": "giờ"},
    "en": {"monthly": "month", "yearly": "year", "hourly": "hour"},
}


def status_label(code: str, *, locale: str = "vi") -> str:
    table = _STATUS_LABELS.get(locale, _STATUS_LABELS["vi"])
    return table.get(code, code)


def period_label(code: str, *, locale: str = "vi") -> str:
    table = _PERIOD_LABELS.get(locale, _PERIOD_LABELS["vi"])
    return table.get(code, code)
