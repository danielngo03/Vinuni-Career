"""Messaging permission predicates — PURE functions, no I/O (ADR-0012 §1).

These encode the institutional permission matrix. The service layer resolves the
I/O-bound facts (personas, the recruitment relationship, org scope, participant
rows) and feeds them here; the rules never touch the database. They are evaluated
at THREE checkpoints — open / send / read — and the **student↔student hard block
is always the first check** (no condition can override it).

Reason codes returned here are STABLE internal tokens (mapped to coded, friendly
errors at the service boundary), never user-facing copy.
"""

from __future__ import annotations

from datetime import datetime, timedelta

# Personas (mirror of ``auth/domain/personas.py`` — kept as local constants so the
# pure rule module has no cross-module dependency).
STUDENT = "student"
ALUMNI = "alumni"
PARTNER_MEMBER = "partner_member"
UNIVERSITY_STAFF = "university_staff"

_STUDENT_SIDE = frozenset({STUDENT, ALUMNI})

# Thread vocabularies.
KIND_DIRECT = "direct"
KIND_ANNOUNCEMENT = "announcement"
KINDS = frozenset({KIND_DIRECT, KIND_ANNOUNCEMENT})

CONTEXT_APPLICATION = "application"
CONTEXT_SUPPORT = "support"
CONTEXT_TEAM = "team"
CONTEXT_TYPES = frozenset({CONTEXT_APPLICATION, CONTEXT_SUPPORT, CONTEXT_TEAM})

STATUS_ACTIVE = "active"
STATUS_ARCHIVED = "archived"
STATUS_CLOSED = "closed"
THREAD_STATUSES = frozenset({STATUS_ACTIVE, STATUS_ARCHIVED, STATUS_CLOSED})

# Application statuses that count as ACTIVE for the inactive-application taper
# (ADR-0012 §1). Mirrors ``recruitment.lifecycle.ACTIVE_STATUSES`` intentionally as a
# local constant so messaging never imports recruitment implementation.
ACTIVE_APPLICATION_STATUSES = frozenset({"submitted", "under_review"})

# Reason codes (internal).
REASON_STUDENT_TO_STUDENT = "student_to_student"
REASON_PARTNER_NEEDS_APPLICATION = "partner_needs_application"
REASON_PARTNER_CROSS_ORG = "partner_cross_org"
REASON_STUDENT_CANNOT_INITIATE_PARTNER = "student_cannot_initiate_partner"
REASON_NOT_ALLOWED = "not_allowed"
REASON_INVALID_KIND = "invalid_kind"
REASON_ANNOUNCEMENT_UNIVERSITY_ONLY = "announcement_university_only"

# Send-time reason codes.
REASON_NOT_PARTICIPANT = "not_participant"
REASON_REPLY_NOT_ALLOWED = "reply_not_allowed"
REASON_THREAD_NOT_ACTIVE = "thread_not_active"
REASON_RELATIONSHIP_REVOKED = "relationship_revoked"


def student_to_student_blocked(
    sender_persona: str, recipient_personas: list[str]
) -> bool:
    """The hard first check: a student/alumni may NEVER message another student/alumni."""

    return sender_persona in _STUDENT_SIDE and any(
        p in _STUDENT_SIDE for p in recipient_personas
    )


def evaluate_open(
    *,
    sender_persona: str,
    recipient_personas: list[str],
    kind: str,
    context_type: str | None,
    relationship_ok: bool,
    same_org: bool,
) -> str | None:
    """Return ``None`` if opening the thread is allowed, else a stable reason code.

    ``relationship_ok`` (partner↔student): a bound application exists where
    ``application.org_id == sender.org_id`` AND ``application.applicant_id ==
    recipient``. ``same_org``: every recipient shares the sender's org (team threads).
    """

    # 1) STUDENT↔STUDENT HARD BLOCK — first, unconditional.
    if student_to_student_blocked(sender_persona, recipient_personas):
        return REASON_STUDENT_TO_STUDENT

    if kind not in KINDS:
        return REASON_INVALID_KIND

    # Announcements: university_staff authors a one-way broadcast.
    if kind == KIND_ANNOUNCEMENT:
        if sender_persona != UNIVERSITY_STAFF:
            return REASON_ANNOUNCEMENT_UNIVERSITY_ONLY
        return None

    # 2) University staff may initiate a direct thread to anyone.
    if sender_persona == UNIVERSITY_STAFF:
        return None

    # 3) Partner sender.
    if sender_persona == PARTNER_MEMBER:
        # Partner ↔ partner (team) must be same org.
        if all(p == PARTNER_MEMBER for p in recipient_personas):
            return None if same_org else REASON_PARTNER_CROSS_ORG
        # Partner ↔ student/alumni: requires an application-bound relationship.
        if any(p in _STUDENT_SIDE for p in recipient_personas):
            if context_type != CONTEXT_APPLICATION or not relationship_ok:
                return REASON_PARTNER_NEEDS_APPLICATION
            return None
        return REASON_NOT_ALLOWED

    # 4) Student/alumni sender.
    if sender_persona in _STUDENT_SIDE:
        # May initiate support to university only.
        if all(p == UNIVERSITY_STAFF for p in recipient_personas):
            return None
        # May NOT initiate a partner thread (reply-only into an existing one).
        if any(p == PARTNER_MEMBER for p in recipient_personas):
            return REASON_STUDENT_CANNOT_INITIATE_PARTNER
        return REASON_NOT_ALLOWED

    return REASON_NOT_ALLOWED


def evaluate_send(
    *,
    is_participant: bool,
    can_reply: bool,
    is_author: bool,
    thread_status: str,
    thread_deleted: bool,
    relationship_ok: bool,
) -> str | None:
    """Return ``None`` if the caller may post into the thread now, else a reason code.

    Re-evaluated on EVERY send (ADR-0012 §1.2) — never cached at create. The author
    may always post (within an active thread); other participants need ``can_reply``;
    an application thread additionally requires the relationship to still authorize
    it (e.g. the application was not purged).
    """

    if thread_deleted or thread_status != STATUS_ACTIVE:
        return REASON_THREAD_NOT_ACTIVE
    if not is_participant:
        return REASON_NOT_PARTICIPANT
    if not relationship_ok:
        return REASON_RELATIONSHIP_REVOKED
    if not (is_author or can_reply):
        return REASON_REPLY_NOT_ALLOWED
    return None


def can_delete_message(
    *,
    now: datetime,
    created_at: datetime,
    is_system: bool,
    is_owner: bool,
    is_university_moderator: bool,
    owner_is_partner_to_student: bool,
    window_minutes: int,
) -> bool:
    """Message-delete rules (ADR-0012 §5).

    - System messages can NEVER be deleted (by anyone).
    - University moderators may delete any non-system message.
    - The sender may soft-delete their OWN message within ``window_minutes`` —
      EXCEPT a partner deleting a message it sent into a student thread (audit
      integrity).
    """

    if is_system:
        return False
    if is_university_moderator:
        return True
    if not is_owner:
        return False
    if owner_is_partner_to_student:
        return False
    return (now - created_at) <= timedelta(minutes=window_minutes)


def application_relationship_active(status: str | None) -> bool:
    """True when the bound application is in an ACTIVE status (no inactive taper)."""

    return status in ACTIVE_APPLICATION_STATUSES
