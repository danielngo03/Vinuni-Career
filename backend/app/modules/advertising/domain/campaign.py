"""Ad-campaign lifecycle state machine, objective/pacing vocabularies, and labels.

This is the CAMPAIGN-GRADE advertising layer (``docs/DISCOVERY_RECOMMENDATION_ADS_SPEC``
§7.0 "Allocation & Distribution Engine", owner decision 2026-07-10) that sits
ALONGSIDE the older target-based ``sponsored_placements`` system — it never
replaces it. A campaign carries a budget + pacing + coarse targeting and competes
for a surface's finite sponsored slots through the allocation engine.

The lifecycle is a small explicit state machine; only transitions in
:data:`TRANSITIONS` are legal. University approval (disclosure + spend oversight)
is a precondition to ``active``. Raw enum codes never reach end users — every code
is paired with a localized label. No I/O lives here.

States (``ad_campaigns.status``):
    draft          -> partner editing; never serves
    pending_review -> submitted; university reviews disclosure + targeting + spend
    approved       -> approved; awaiting go-live window
    active         -> serving; competes for sponsored slots while in-budget/window
    paused         -> partner/university paused; not serving, resumable
    ended          -> window passed OR budget exhausted; terminal
    rejected       -> university rejected; editable + resubmittable
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Status vocabulary                                                           #
# --------------------------------------------------------------------------- #

DRAFT = "draft"
PENDING_REVIEW = "pending_review"
APPROVED = "approved"
ACTIVE = "active"
PAUSED = "paused"
ENDED = "ended"
REJECTED = "rejected"

STATUSES: frozenset[str] = frozenset(
    {DRAFT, PENDING_REVIEW, APPROVED, ACTIVE, PAUSED, ENDED, REJECTED}
)

# Partner may PATCH a campaign only in these states.
EDITABLE_STATES: frozenset[str] = frozenset({DRAFT, REJECTED})
# Soft-deletable states (an approved/active campaign must be ended, not deleted).
DELETABLE_STATES: frozenset[str] = frozenset({DRAFT, REJECTED})
# Fully terminal states (no further transitions).
TERMINAL_STATES: frozenset[str] = frozenset({ENDED})
# Statuses that the allocation engine may consider for serving.
SERVABLE_STATES: frozenset[str] = frozenset({ACTIVE})
# "In flight": occupies the per-org concurrency cap.
IN_FLIGHT_STATES: frozenset[str] = frozenset({PENDING_REVIEW, APPROVED, ACTIVE, PAUSED})

# --------------------------------------------------------------------------- #
# Transition map: event -> (allowed from-states, to-state)                    #
# --------------------------------------------------------------------------- #

TRANSITIONS: dict[str, tuple[frozenset[str], str]] = {
    "submit": (frozenset({DRAFT, REJECTED}), PENDING_REVIEW),
    "approve": (frozenset({PENDING_REVIEW}), APPROVED),
    "reject": (frozenset({PENDING_REVIEW}), REJECTED),
    "activate": (frozenset({APPROVED, PAUSED}), ACTIVE),
    "pause": (frozenset({ACTIVE}), PAUSED),
    "resume": (frozenset({PAUSED}), ACTIVE),
    "end": (frozenset({APPROVED, ACTIVE, PAUSED}), ENDED),
}


def can_transition(event: str, current: str) -> bool:
    """True if ``event`` is legal from the ``current`` status."""

    spec = TRANSITIONS.get(event)
    return spec is not None and current in spec[0]


def target_state(event: str) -> str:
    """The destination status for ``event`` (raises ``KeyError`` if unknown)."""

    return TRANSITIONS[event][1]


# --------------------------------------------------------------------------- #
# Objective vocabulary                                                        #
# --------------------------------------------------------------------------- #

OBJ_AWARENESS = "awareness"
OBJ_TRAFFIC = "traffic"
OBJ_APPLICATIONS = "applications"
OBJ_EVENT_REGISTRATION = "event_registration"

OBJECTIVES: frozenset[str] = frozenset(
    {OBJ_AWARENESS, OBJ_TRAFFIC, OBJ_APPLICATIONS, OBJ_EVENT_REGISTRATION}
)


# --------------------------------------------------------------------------- #
# Pacing vocabulary                                                           #
# --------------------------------------------------------------------------- #

PACING_EVEN = "even"
PACING_ASAP = "asap"

PACINGS: frozenset[str] = frozenset({PACING_EVEN, PACING_ASAP})


def is_valid_objective(code: str) -> bool:
    return code in OBJECTIVES


def is_valid_pacing(code: str) -> bool:
    return code in PACINGS


# --------------------------------------------------------------------------- #
# Localized labels (never expose raw enum codes)                              #
# --------------------------------------------------------------------------- #

_STATUS_LABELS: dict[str, dict[str, str]] = {
    "vi": {
        DRAFT: "Bản nháp",
        PENDING_REVIEW: "Chờ duyệt",
        APPROVED: "Đã duyệt",
        ACTIVE: "Đang chạy",
        PAUSED: "Tạm dừng",
        ENDED: "Đã kết thúc",
        REJECTED: "Bị từ chối",
    },
    "en": {
        DRAFT: "Draft",
        PENDING_REVIEW: "Pending review",
        APPROVED: "Approved",
        ACTIVE: "Active",
        PAUSED: "Paused",
        ENDED: "Ended",
        REJECTED: "Rejected",
    },
}

_OBJECTIVE_LABELS: dict[str, dict[str, str]] = {
    "vi": {
        OBJ_AWARENESS: "Nhận diện",
        OBJ_TRAFFIC: "Lượt truy cập",
        OBJ_APPLICATIONS: "Ứng tuyển",
        OBJ_EVENT_REGISTRATION: "Đăng ký sự kiện",
    },
    "en": {
        OBJ_AWARENESS: "Awareness",
        OBJ_TRAFFIC: "Traffic",
        OBJ_APPLICATIONS: "Applications",
        OBJ_EVENT_REGISTRATION: "Event registration",
    },
}

_PACING_LABELS: dict[str, dict[str, str]] = {
    "vi": {
        PACING_EVEN: "Phân bổ đều",
        PACING_ASAP: "Nhanh nhất có thể",
    },
    "en": {
        PACING_EVEN: "Even pacing",
        PACING_ASAP: "As fast as possible",
    },
}


def _label(table: dict[str, dict[str, str]], code: str, locale: str) -> str:
    return table.get(locale, table["vi"]).get(code, code)


def status_label(code: str, *, locale: str = "vi") -> str:
    return _label(_STATUS_LABELS, code, locale)


def objective_label(code: str, *, locale: str = "vi") -> str:
    return _label(_OBJECTIVE_LABELS, code, locale)


def pacing_label(code: str, *, locale: str = "vi") -> str:
    return _label(_PACING_LABELS, code, locale)
