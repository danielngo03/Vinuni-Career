"""Real application timeline vocabulary + labels (``docs/DATA_MODEL.md`` §32).

A small, honest, append-only narrative of an application's lifecycle — the
backend contract the student-facing timeline reads from (previously faked
client-side from ``status`` alone). Every event type is paired with a short,
neutral ``label_en``/``label_vi`` (never a raw enum code); some event types also
carry PARTNER-INTERNAL ``metadata`` (the coded rejection reason, the target stage
name) that is recorded for audit but must NEVER reach the student projection —
that redaction is enforced by ``PARTNER_INTERNAL_EVENT_TYPES`` + the presenter/
service that build the student's own timeline (never here).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.recruitment.domain.models import ApplicationTimelineEvent

# --------------------------------------------------------------------------- #
# Event vocabulary                                                             #
# --------------------------------------------------------------------------- #

SUBMITTED = "submitted"
UNDER_REVIEW = "under_review"
REJECTED = "rejected"
WITHDRAWN = "withdrawn"
HIRED = "hired"
STAGE_ADVANCED = "stage_advanced"
STAGE_ROLLED_BACK = "stage_rolled_back"
INTERVIEW_SCHEDULED = "interview_scheduled"
INTERVIEW_RESCHEDULED = "interview_rescheduled"
INTERVIEW_CANCELLED = "interview_cancelled"
INTERVIEW_COMPLETED = "interview_completed"
OFFER_SENT = "offer_sent"
OFFER_ACCEPTED = "offer_accepted"
OFFER_DECLINED = "offer_declined"
OFFER_EXPIRED = "offer_expired"
OFFER_RESCINDED = "offer_rescinded"

EVENT_TYPES: frozenset[str] = frozenset(
    {
        SUBMITTED,
        UNDER_REVIEW,
        REJECTED,
        WITHDRAWN,
        HIRED,
        STAGE_ADVANCED,
        STAGE_ROLLED_BACK,
        INTERVIEW_SCHEDULED,
        INTERVIEW_RESCHEDULED,
        INTERVIEW_CANCELLED,
        INTERVIEW_COMPLETED,
        OFFER_SENT,
        OFFER_ACCEPTED,
        OFFER_DECLINED,
        OFFER_EXPIRED,
        OFFER_RESCINDED,
    }
)

# Event types whose ``event_metadata`` may carry partner-internal detail (coded
# rejection reason, target stage name/id). The student timeline projection MUST
# expose only ``{event_type, label, occurred_at}`` for these — never ``metadata``.
PARTNER_INTERNAL_EVENT_TYPES: frozenset[str] = frozenset(
    {REJECTED, STAGE_ADVANCED, STAGE_ROLLED_BACK}
)

_LABELS: dict[str, dict[str, str]] = {
    SUBMITTED: {
        "en": "Application submitted",
        "vi": "Đã nộp hồ sơ ứng tuyển",
    },
    UNDER_REVIEW: {
        "en": "Application under review",
        "vi": "Hồ sơ đang được xem xét",
    },
    REJECTED: {
        "en": "Application not selected",
        "vi": "Hồ sơ không được chọn",
    },
    WITHDRAWN: {
        "en": "Application withdrawn",
        "vi": "Đã rút hồ sơ ứng tuyển",
    },
    HIRED: {
        "en": "Offer accepted — hired",
        "vi": "Đã chấp nhận thư mời — trúng tuyển",
    },
    STAGE_ADVANCED: {
        "en": "Moved to the next stage",
        "vi": "Đã chuyển sang vòng tiếp theo",
    },
    STAGE_ROLLED_BACK: {
        "en": "Moved back for re-review",
        "vi": "Được chuyển lại để xem xét thêm",
    },
    INTERVIEW_SCHEDULED: {
        "en": "Interview scheduled",
        "vi": "Đã lên lịch phỏng vấn",
    },
    INTERVIEW_RESCHEDULED: {
        "en": "Interview rescheduled",
        "vi": "Đã dời lịch phỏng vấn",
    },
    INTERVIEW_CANCELLED: {
        "en": "Interview cancelled",
        "vi": "Đã hủy lịch phỏng vấn",
    },
    INTERVIEW_COMPLETED: {
        "en": "Interview completed",
        "vi": "Đã hoàn thành phỏng vấn",
    },
    OFFER_SENT: {
        "en": "Offer sent",
        "vi": "Đã gửi thư mời",
    },
    OFFER_ACCEPTED: {
        "en": "Offer accepted",
        "vi": "Đã chấp nhận thư mời",
    },
    OFFER_DECLINED: {
        "en": "Offer declined",
        "vi": "Đã từ chối thư mời",
    },
    OFFER_EXPIRED: {
        "en": "Offer expired",
        "vi": "Thư mời đã hết hạn",
    },
    OFFER_RESCINDED: {
        "en": "Offer withdrawn by the company",
        "vi": "Công ty đã thu hồi thư mời",
    },
}


def label_en(event_type: str) -> str:
    return _LABELS.get(event_type, {}).get("en", event_type)


def label_vi(event_type: str) -> str:
    return _LABELS.get(event_type, {}).get("vi", event_type)


def label_for(event_type: str, *, locale: str = "vi") -> str:
    return label_en(event_type) if locale == "en" else label_vi(event_type)


# --------------------------------------------------------------------------- #
# Write                                                                       #
# --------------------------------------------------------------------------- #


async def record_timeline_event(
    session: AsyncSession,
    *,
    application_id: uuid.UUID,
    event_type: str,
    actor_id: uuid.UUID | None = None,
    metadata: dict | None = None,
    occurred_at: datetime | None = None,
) -> ApplicationTimelineEvent:
    """Append one timeline row in the CALLER's transaction (flush only — no commit).

    The caller (apply_service / decision_service / stage_service /
    interview_service / offer_service) is already inside a transaction that will
    commit the state change + audit row atomically; this call must never open or
    commit its own transaction.
    """

    row = ApplicationTimelineEvent(
        application_id=application_id,
        event_type=event_type,
        label_en=label_en(event_type),
        label_vi=label_vi(event_type),
        actor_id=actor_id,
        event_metadata=dict(metadata or {}),
    )
    if occurred_at is not None:
        row.occurred_at = occurred_at
    session.add(row)
    await session.flush()
    return row


# --------------------------------------------------------------------------- #
# Read                                                                        #
# --------------------------------------------------------------------------- #


async def list_timeline_for_student(
    session: AsyncSession, *, application_id: uuid.UUID, locale: str = "vi"
) -> list[dict]:
    """The student-facing timeline: ``{event_type, label, occurred_at}`` only.

    Ordered oldest -> newest. ``metadata`` is NEVER included here regardless of
    event type — the student timeline is a narrative, not an audit log.
    """

    rows = (
        (
            await session.execute(
                select(ApplicationTimelineEvent)
                .where(ApplicationTimelineEvent.application_id == application_id)
                .order_by(ApplicationTimelineEvent.occurred_at.asc())
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "event_type": row.event_type,
            "label": label_for(row.event_type, locale=locale),
            "occurred_at": row.occurred_at.isoformat() if row.occurred_at else None,
        }
        for row in rows
    ]


# --------------------------------------------------------------------------- #
# next_action derivation (pure)                                               #
# --------------------------------------------------------------------------- #

NEXT_AWAIT_REVIEW = "await_review"
NEXT_PREPARE_FOR_INTERVIEW = "prepare_for_interview"
NEXT_RESPOND_TO_OFFER = "respond_to_offer"
NEXT_NO_ACTION_WITHDRAWN = "no_action_withdrawn"
NEXT_NO_ACTION_REJECTED = "no_action_rejected"
NEXT_NO_ACTION_HIRED = "no_action_hired"
NEXT_IN_PROGRESS = "in_progress"


def derive_next_action(
    *,
    status: str,
    has_upcoming_interview: bool,
    has_actionable_offer: bool,
) -> str:
    """A short, machine-readable "what happens next" key for the student.

    Pure function — no I/O. Precedence: a terminal status always wins; an
    actionable (``sent``, non-expired) offer beats an upcoming interview beats
    the generic "still in the pipeline" state.
    """

    if status == "withdrawn":
        return NEXT_NO_ACTION_WITHDRAWN
    if status == "rejected":
        return NEXT_NO_ACTION_REJECTED
    if status == "hired":
        return NEXT_NO_ACTION_HIRED
    if has_actionable_offer:
        return NEXT_RESPOND_TO_OFFER
    if has_upcoming_interview:
        return NEXT_PREPARE_FOR_INTERVIEW
    if status == "submitted":
        return NEXT_AWAIT_REVIEW
    # under_review with no interview/offer yet — still "in the pipeline".
    return NEXT_IN_PROGRESS
