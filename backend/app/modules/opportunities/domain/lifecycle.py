"""Job lifecycle state machine, vocabularies, and friendly labels.

The job lifecycle (``docs/BUSINESS_LOGIC.md`` §2, ``docs/DATA_MODEL.md`` §8) is a
small, explicit state machine. Only the transitions enumerated in
:data:`TRANSITIONS` are legal; everything else raises an illegal-transition error
at the service layer. Moderation (university approval) is required before a job
becomes publicly visible.

States (``jobs.status``):
    draft            -> author is editing; never publicly visible
    pending_review   -> submitted; awaiting university moderation; edit-locked
    active           -> approved + published; publicly visible (subject to deadline)
    rejected         -> university rejected; editable again, can be resubmitted
    closed           -> partner OR deadline auto-close; removed from public listings
    expired          -> reserved/unused in V1. Deadline auto-close uses
                        active -> closed (docs/BUSINESS_LOGIC.md §2.2, ADR-0003 §2),
                        NOT this state; sweep_deadline_closures sets ``closed``.

``jobs.moderation_status``: pending | approved | rejected | flagged.

Raw enum codes never reach end users — every code is paired with a localized
label (``status_label`` / ``moderation_label`` / ``employment_type_label`` / ...).
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Status vocabulary                                                           #
# --------------------------------------------------------------------------- #

DRAFT = "draft"
PENDING_REVIEW = "pending_review"
ACTIVE = "active"
REJECTED = "rejected"
CLOSED = "closed"
EXPIRED = "expired"

STATUSES: frozenset[str] = frozenset(
    {DRAFT, PENDING_REVIEW, ACTIVE, REJECTED, CLOSED, EXPIRED}
)

# States in which the partner may PATCH job content. ``ACTIVE`` is included for
# the post-publication amendment policy (B-552): once published, only a subset
# of fields may be changed freely (``FREE_AMEND_FIELDS``) while content-quality
# fields (``REMODERATION_FIELDS``) pull the job back into moderation. See
# ``update_job`` in ``application/job_service.py`` for enforcement.
EDITABLE_STATES: frozenset[str] = frozenset({DRAFT, REJECTED, ACTIVE})

# --------------------------------------------------------------------------- #
# Post-publication amendment policy (B-552)                                   #
# --------------------------------------------------------------------------- #
#
# Once a job is ``active`` (published + approved), edits are split into three
# buckets:
#
# - ``FREE_AMEND_FIELDS``: operational fields a partner may change at any time
#   without re-triggering moderation (e.g. extending the deadline, adjusting
#   headcount, toggling visibility, tweaking benefits copy). These do not
#   change the JD's substantive content or the compliance surface a moderator
#   reviewed.
# - ``REMODERATION_FIELDS``: content fields the university actually reviewed
#   (title, description, requirements, compensation, location, candidate
#   requirements, etc). Changing any of these while ``active`` unpublishes the
#   job and resets it to ``pending_review`` (re-moderation), exactly like a
#   fresh submission, because the previously-approved content no longer
#   matches what is live.
# - Screening questions are **locked** once a job is ``active`` — existing
#   ``applications.screening_answers`` reference the current question set by
#   id/order, so mutating them post-publish would silently corrupt or
#   orphan already-submitted answers. Screening questions may only be edited
#   in ``draft``/``rejected``.
FREE_AMEND_FIELDS: frozenset[str] = frozenset(
    {"application_deadline", "headcount", "visibility", "benefits"}
)

REMODERATION_FIELDS: frozenset[str] = frozenset(
    {
        "title", "description", "requirements", "employment_type",
        "location_type", "location_city", "location_country", "locations",
        "required_skills", "preferred_skills", "experience_min_years",
        "experience_max_years", "experience_mode", "industry_id",
        "degree_required", "seniority_level", "candidate_requirements",
        "salary_min", "salary_max", "salary_currency", "salary_is_disclosed",
        "salary_mode", "salary_period", "salary_gross_net",
    }
)

# States that may be soft-deleted/archived (an active job must be closed first).
DELETABLE_STATES: frozenset[str] = frozenset({DRAFT, REJECTED, CLOSED, EXPIRED})

# Moderation vocabulary.
MOD_PENDING = "pending"
MOD_APPROVED = "approved"
MOD_REJECTED = "rejected"
MOD_FLAGGED = "flagged"

# --------------------------------------------------------------------------- #
# Transition map: event -> (allowed from-states, to-state)                    #
# --------------------------------------------------------------------------- #

TRANSITIONS: dict[str, tuple[frozenset[str], str]] = {
    "submit": (frozenset({DRAFT, REJECTED}), PENDING_REVIEW),
    "approve": (frozenset({PENDING_REVIEW}), ACTIVE),
    "reject": (frozenset({PENDING_REVIEW}), REJECTED),
    "close": (frozenset({ACTIVE}), CLOSED),
    "reopen": (frozenset({CLOSED}), ACTIVE),
    # A content amendment to a live job re-enters moderation (B-552). Driven
    # directly by ``job_service.update_job``, not the generic ``_transition``
    # helper, because it is a side-effect of a PATCH rather than a dedicated
    # lifecycle endpoint.
    "amend": (frozenset({ACTIVE}), PENDING_REVIEW),
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

EMPLOYMENT_TYPES: frozenset[str] = frozenset(
    {"full_time", "part_time", "internship", "contract"}
)
LOCATION_TYPES: frozenset[str] = frozenset({"onsite", "remote", "hybrid"})

# Visibility levels (``docs/BUSINESS_LOGIC.md`` §5 enforcement matrix).
PUBLIC = "public"
AUTHENTICATED = "authenticated"
STUDENTS_ONLY = "students_only"
VINUNI_ONLY = "vinuni_only"
INVITATION_ONLY = "invitation_only"
VISIBILITY_LEVELS: frozenset[str] = frozenset(
    {PUBLIC, AUTHENTICATED, STUDENTS_ONLY, VINUNI_ONLY, INVITATION_ONLY}
)

SCREENING_Q_TYPES: frozenset[str] = frozenset(
    {"text", "single_choice", "multiple_choice", "yes_no"}
)

# Seniority/career level vocabulary for structured JD requirements. Partners may
# still describe nuance in candidate_requirements.note, but this stable code is
# useful for filtering, analytics, and AI parsing.
SENIORITY_LEVELS: frozenset[str] = frozenset(
    {
        "not_required",
        "intern",
        "fresher",
        "junior",
        "middle",
        "senior",
        "lead",
        "manager",
        "director",
        "executive",
    }
)


# --------------------------------------------------------------------------- #
# Localized labels (never expose raw enum codes)                              #
# --------------------------------------------------------------------------- #

_STATUS_LABELS: dict[str, dict[str, str]] = {
    "vi": {
        DRAFT: "Bản nháp",
        PENDING_REVIEW: "Chờ duyệt",
        ACTIVE: "Đang tuyển",
        REJECTED: "Bị từ chối",
        CLOSED: "Đã đóng",
        EXPIRED: "Hết hạn",
    },
    "en": {
        DRAFT: "Draft",
        PENDING_REVIEW: "Pending review",
        ACTIVE: "Active",
        REJECTED: "Rejected",
        CLOSED: "Closed",
        EXPIRED: "Expired",
    },
}

_MOD_LABELS: dict[str, dict[str, str]] = {
    "vi": {
        MOD_PENDING: "Đang chờ",
        MOD_APPROVED: "Đã duyệt",
        MOD_REJECTED: "Đã từ chối",
        MOD_FLAGGED: "Bị gắn cờ",
    },
    "en": {
        MOD_PENDING: "Pending",
        MOD_APPROVED: "Approved",
        MOD_REJECTED: "Rejected",
        MOD_FLAGGED: "Flagged",
    },
}

_EMPLOYMENT_LABELS: dict[str, dict[str, str]] = {
    "vi": {
        "full_time": "Toàn thời gian",
        "part_time": "Bán thời gian",
        "internship": "Thực tập",
        "contract": "Hợp đồng",
    },
    "en": {
        "full_time": "Full-time",
        "part_time": "Part-time",
        "internship": "Internship",
        "contract": "Contract",
    },
}

_LOCATION_LABELS: dict[str, dict[str, str]] = {
    "vi": {"onsite": "Tại văn phòng", "remote": "Từ xa", "hybrid": "Linh hoạt"},
    "en": {"onsite": "On-site", "remote": "Remote", "hybrid": "Hybrid"},
}


def _label(table: dict[str, dict[str, str]], code: str, locale: str) -> str:
    return table.get(locale, table["vi"]).get(code, code)


def status_label(code: str, *, locale: str = "vi") -> str:
    return _label(_STATUS_LABELS, code, locale)


def moderation_label(code: str, *, locale: str = "vi") -> str:
    return _label(_MOD_LABELS, code, locale)


def employment_type_label(code: str, *, locale: str = "vi") -> str:
    return _label(_EMPLOYMENT_LABELS, code, locale)


def location_type_label(code: str, *, locale: str = "vi") -> str:
    return _label(_LOCATION_LABELS, code, locale)


# --------------------------------------------------------------------------- #
# Visibility tiers a principal may discover                                   #
# --------------------------------------------------------------------------- #

# Persona -> visibility levels that persona is allowed to see in public lists.
# ``invitation_only`` requires a per-job allow-list (later phase) and is never
# returned by the generic public filter; only the owning org sees those jobs.
_PERSONA_VISIBILITY: dict[str, frozenset[str]] = {
    "guest": frozenset({PUBLIC}),
    "student": frozenset({PUBLIC, AUTHENTICATED, STUDENTS_ONLY, VINUNI_ONLY}),
    "alumni": frozenset({PUBLIC, AUTHENTICATED, STUDENTS_ONLY}),
    "partner_member": frozenset({PUBLIC, AUTHENTICATED}),
    "university_staff": frozenset(
        {PUBLIC, AUTHENTICATED, STUDENTS_ONLY, VINUNI_ONLY}
    ),
}


def visible_levels_for(persona: str, *, is_authenticated: bool) -> frozenset[str]:
    """Visibility levels a principal of ``persona`` may discover publicly."""

    if not is_authenticated:
        return frozenset({PUBLIC})
    return _PERSONA_VISIBILITY.get(persona, frozenset({PUBLIC, AUTHENTICATED}))
