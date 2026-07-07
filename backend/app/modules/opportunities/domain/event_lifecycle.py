"""Event lifecycle state machine, vocabularies, and friendly labels (ADR-0008).

Events live alongside jobs in ``opportunities`` and mirror the jobs *machinery*
(explicit transition map, university-only moderation gate, optimistic ``version``,
audit) while diverging on the *vocabulary*: an event is *published* (not "active")
and ends by *completing* (time passes) or being *cancelled*, never "closed".

States (``events.status``):
    draft            -> creator editing; never publicly visible
    pending_review   -> partner submitted; awaiting university moderation; edit-locked
    published        -> approved + live; publicly discoverable (subject to dates/visibility)
    cancelled        -> creator/university called the event off; registrants notified
    completed        -> ``ends_at`` passed (scheduler auto-set); read-only/archival
    rejected         -> university rejected; editable again, resubmittable

``events.moderation_status``: pending | approved | rejected | flagged.

``event_registrations.status``: confirmed | waitlisted | cancelled | attended | no_show.

Raw enum codes never reach end users — every code is paired with a localized
label. This module is pure (no I/O); visibility tiers reuse the shared
``lifecycle.visible_levels_for``.
"""

from __future__ import annotations

from datetime import datetime

# --------------------------------------------------------------------------- #
# Event status vocabulary                                                     #
# --------------------------------------------------------------------------- #

DRAFT = "draft"
PENDING_REVIEW = "pending_review"
PUBLISHED = "published"
CANCELLED = "cancelled"
COMPLETED = "completed"
REJECTED = "rejected"

STATUSES: frozenset[str] = frozenset(
    {DRAFT, PENDING_REVIEW, PUBLISHED, CANCELLED, COMPLETED, REJECTED}
)

# States in which the organizer may PATCH event content.
EDITABLE_STATES: frozenset[str] = frozenset({DRAFT, REJECTED})

# States that may be soft-deleted/archived (a published event must be cancelled
# before it can be deleted).
DELETABLE_STATES: frozenset[str] = frozenset(
    {DRAFT, REJECTED, CANCELLED, COMPLETED}
)

# Moderation vocabulary (shared shape with jobs).
MOD_PENDING = "pending"
MOD_APPROVED = "approved"
MOD_REJECTED = "rejected"
MOD_FLAGGED = "flagged"
# Moderator sent the event back to the organizer to revise and resubmit.
MOD_CHANGES_REQUESTED = "changes_requested"

# --------------------------------------------------------------------------- #
# Transition map: event-name -> (allowed from-states, to-state)               #
# --------------------------------------------------------------------------- #
# ``submit`` resolves to ``pending_review`` for partner orgs and ``published``
# for university orgs (auto-approve, §5); the service picks the target, but both
# legal from-states are the same so :func:`can_transition` guards either path.

TRANSITIONS: dict[str, tuple[frozenset[str], str]] = {
    "submit": (frozenset({DRAFT, REJECTED}), PENDING_REVIEW),
    "approve": (frozenset({PENDING_REVIEW}), PUBLISHED),
    "reject": (frozenset({PENDING_REVIEW}), REJECTED),
    # Return a submitted event to the organizer's drafts to revise and resubmit.
    "request_changes": (frozenset({PENDING_REVIEW}), DRAFT),
    "cancel": (frozenset({PUBLISHED}), CANCELLED),
    "complete": (frozenset({PUBLISHED}), COMPLETED),
}


def can_transition(event: str, current: str) -> bool:
    """True if ``event`` is legal from the ``current`` status."""

    spec = TRANSITIONS.get(event)
    return spec is not None and current in spec[0]


def target_state(event: str) -> str:
    """The destination status for ``event`` (raises ``KeyError`` if unknown)."""

    return TRANSITIONS[event][1]


# --------------------------------------------------------------------------- #
# Registration state vocabulary                                               #
# --------------------------------------------------------------------------- #

REG_CONFIRMED = "confirmed"
REG_WAITLISTED = "waitlisted"
REG_CANCELLED = "cancelled"
REG_ATTENDED = "attended"
REG_NO_SHOW = "no_show"

REGISTRATION_STATES: frozenset[str] = frozenset(
    {REG_CONFIRMED, REG_WAITLISTED, REG_CANCELLED, REG_ATTENDED, REG_NO_SHOW}
)

# A registration that holds (or once held) a seat.
ACTIVE_REGISTRATION_STATES: frozenset[str] = frozenset(
    {REG_CONFIRMED, REG_WAITLISTED, REG_ATTENDED, REG_NO_SHOW}
)


# --------------------------------------------------------------------------- #
# Enumerated field vocabularies                                               #
# --------------------------------------------------------------------------- #

EVENT_TYPES: frozenset[str] = frozenset(
    {"career_fair", "workshop", "info_session", "networking", "webinar"}
)
FORMATS: frozenset[str] = frozenset({"onsite", "online", "hybrid"})

# Visibility levels (reuses the shared jobs matrix).
PUBLIC = "public"
AUTHENTICATED = "authenticated"
STUDENTS_ONLY = "students_only"
VINUNI_ONLY = "vinuni_only"
INVITATION_ONLY = "invitation_only"
VISIBILITY_LEVELS: frozenset[str] = frozenset(
    {PUBLIC, AUTHENTICATED, STUDENTS_ONLY, VINUNI_ONLY, INVITATION_ONLY}
)


# --------------------------------------------------------------------------- #
# Localized labels (never expose raw enum codes)                              #
# --------------------------------------------------------------------------- #

_STATUS_LABELS: dict[str, dict[str, str]] = {
    "vi": {
        DRAFT: "Bản nháp",
        PENDING_REVIEW: "Chờ duyệt",
        PUBLISHED: "Đã đăng",
        CANCELLED: "Đã hủy",
        COMPLETED: "Đã kết thúc",
        REJECTED: "Bị từ chối",
    },
    "en": {
        DRAFT: "Draft",
        PENDING_REVIEW: "Pending review",
        PUBLISHED: "Published",
        CANCELLED: "Cancelled",
        COMPLETED: "Completed",
        REJECTED: "Rejected",
    },
}

_MOD_LABELS: dict[str, dict[str, str]] = {
    "vi": {
        MOD_PENDING: "Đang chờ",
        MOD_APPROVED: "Đã duyệt",
        MOD_REJECTED: "Đã từ chối",
        MOD_FLAGGED: "Bị gắn cờ",
        MOD_CHANGES_REQUESTED: "Yêu cầu chỉnh sửa",
    },
    "en": {
        MOD_PENDING: "Pending",
        MOD_APPROVED: "Approved",
        MOD_REJECTED: "Rejected",
        MOD_FLAGGED: "Flagged",
        MOD_CHANGES_REQUESTED: "Changes requested",
    },
}

_TYPE_LABELS: dict[str, dict[str, str]] = {
    "vi": {
        "career_fair": "Ngày hội việc làm",
        "workshop": "Hội thảo thực hành",
        "info_session": "Buổi giới thiệu",
        "networking": "Kết nối",
        "webinar": "Hội thảo trực tuyến",
    },
    "en": {
        "career_fair": "Career fair",
        "workshop": "Workshop",
        "info_session": "Info session",
        "networking": "Networking",
        "webinar": "Webinar",
    },
}

_FORMAT_LABELS: dict[str, dict[str, str]] = {
    "vi": {"onsite": "Trực tiếp", "online": "Trực tuyến", "hybrid": "Kết hợp"},
    "en": {"onsite": "On-site", "online": "Online", "hybrid": "Hybrid"},
}

_REG_STATE_LABELS: dict[str, dict[str, str]] = {
    "vi": {
        REG_CONFIRMED: "Đã đăng ký",
        REG_WAITLISTED: "Danh sách chờ",
        REG_CANCELLED: "Đã hủy",
        REG_ATTENDED: "Đã tham dự",
        REG_NO_SHOW: "Vắng mặt",
    },
    "en": {
        REG_CONFIRMED: "Confirmed",
        REG_WAITLISTED: "Waitlisted",
        REG_CANCELLED: "Cancelled",
        REG_ATTENDED: "Attended",
        REG_NO_SHOW: "No-show",
    },
}


def _label(table: dict[str, dict[str, str]], code: str, locale: str) -> str:
    return table.get(locale, table["vi"]).get(code, code)


def status_label(code: str, *, locale: str = "vi") -> str:
    return _label(_STATUS_LABELS, code, locale)


def moderation_label(code: str, *, locale: str = "vi") -> str:
    return _label(_MOD_LABELS, code, locale)


def event_type_label(code: str, *, locale: str = "vi") -> str:
    return _label(_TYPE_LABELS, code, locale)


def format_label(code: str, *, locale: str = "vi") -> str:
    return _label(_FORMAT_LABELS, code, locale)


def registration_state_label(code: str, *, locale: str = "vi") -> str:
    return _label(_REG_STATE_LABELS, code, locale)


# --------------------------------------------------------------------------- #
# Pure registration predicates                                                #
# --------------------------------------------------------------------------- #


def registration_window_closed(
    *,
    now: datetime,
    registration_closes_at: datetime | None,
    starts_at: datetime,
) -> bool:
    """True when registration is no longer open.

    The effective deadline is ``registration_closes_at`` when set, otherwise the
    event's ``starts_at``. Registration is closed when ``now`` is at or past it.
    """

    deadline = registration_closes_at or starts_at
    return now >= deadline


def registration_not_yet_open(
    *, now: datetime, registration_opens_at: datetime | None
) -> bool:
    """True when registration has an opening time that is still in the future."""

    return registration_opens_at is not None and now < registration_opens_at
