"""Pydantic request schemas for the applications API.

HTTP validation only; ownership, RBAC, vocabulary, and business rules (duplicate
prevention, reveal reason length, reveal state) live in the services.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class CvSelectionInput(BaseModel):
    """``docs/API_CONTRACTS.md`` Application CV Selection."""

    type: str = Field(max_length=30)  # builder_cv | uploaded_document
    cv_profile_id: str | None = None
    cv_version_id: str | None = None
    uploaded_document_id: str | None = None


class ApplyRequest(BaseModel):
    job_id: uuid.UUID
    cv_selection: CvSelectionInput
    cover_letter: str | None = Field(default=None, max_length=20000)
    screening_answers: dict = Field(default_factory=dict)
    is_anonymous: bool = False
    idempotency_key: str = Field(min_length=1, max_length=200)


class WithdrawRequest(BaseModel):
    """``POST /applications/{id}/withdraw``.

    Both fields optional: a bare call still withdraws. ``version`` is the
    optimistic-lock guard (stale -> ``409 version_conflict``); ``reason`` is the
    student's OWN free-text note (no enum — this is not the partner rejection
    reason), surfaced back only on the student's own timeline.
    """

    version: int | None = None
    reason: str | None = Field(default=None, max_length=500)


class ReviewRequestBody(BaseModel):
    """``POST /applications/{id}/review`` — optimistic ``version`` only."""

    version: int | None = None


class RejectRequestBody(BaseModel):
    """``POST /applications/{id}/reject``.

    ``reason`` is a REQUIRED coded enum; an invalid or missing code is a ``422``
    (Pydantic) before the service runs. The ``note`` is partner-internal free text;
    neither field is ever surfaced to the student.
    """

    reason: Literal[
        "not_qualified",
        "experience_mismatch",
        "position_filled",
        "incomplete",
        "other",
    ]
    note: str | None = Field(default=None, max_length=2000)
    version: int | None = None


class AdvanceRequestBody(BaseModel):
    """``POST /applications/{id}/advance`` — optimistic ``version`` only.

    The move is on the fine ``candidate_stages`` position; the target is always the
    next stage by ``sort_order`` (no body field needed). An ``Idempotency-Key``
    header (not a body field) dedupes a true network retry of the same advance.
    """

    version: int | None = None


class RollbackRequestBody(BaseModel):
    """``POST /applications/{id}/rollback``.

    ``target_stage_id`` is the prior stage to return to; ``reason`` is REQUIRED and
    partner-internal (min 20 chars — too short is a ``422``; never sent to the
    student). Optimistic ``version`` is optional.
    """

    target_stage_id: uuid.UUID
    reason: str = Field(min_length=20, max_length=2000)
    version: int | None = None


class BulkRejectRequestBody(BaseModel):
    """``POST /jobs/{jobId}/applications/bulk-reject`` — reject multiple applications.

    ``application_ids`` must be non-empty (max 100 per call). ``reason`` is the
    same coded enum as the single-reject endpoint. ``note`` is optional and
    partner-internal (never surfaced to students).
    """

    application_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)
    reason: Literal[
        "not_qualified",
        "experience_mismatch",
        "position_filled",
        "incomplete",
        "other",
    ]
    note: str | None = Field(default=None, max_length=2000)


class BulkReviewRequestBody(BaseModel):
    """``POST /jobs/{jobId}/applications/bulk-review`` — move multiple submitted
    applications to ``under_review`` (idempotent per item).

    ``application_ids`` must be non-empty (max 100 per call).
    """

    application_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)


class ScorecardScoreInput(BaseModel):
    """One criterion rating (1..5). The full ``DEFAULT_CRITERIA`` set is required;
    the "all criteria present / no duplicates" rule is enforced in the service."""

    criterion_key: str = Field(max_length=40)
    score: int = Field(ge=1, le=5)


class ScorecardSubmitBody(BaseModel):
    """``POST /applications/{id}/scorecards`` — submit / upsert the caller's card.

    ``recommendation`` is a REQUIRED 4-value coded enum (a missing/invalid value is
    a ``422`` before the service runs). ``comment`` is optional partner-internal
    free text; ``version`` is the per-scorecard optimistic version on edit.
    """

    recommendation: Literal["strong_no", "no", "yes", "strong_yes"]
    scores: list[ScorecardScoreInput] = Field(min_length=1, max_length=20)
    comment: str | None = Field(default=None, max_length=5000)
    version: int | None = None


class InterviewScheduleBody(BaseModel):
    """``POST /applications/{id}/interviews`` — schedule the current-stage interview.

    ``mode`` is a coded enum (``onsite`` requires ``location``, ``online`` requires
    ``meeting_link`` — enforced in the service for a field-scoped 422). ``assignee_ids``
    are partner-org members (validated in the service). ``meeting_link`` is encrypted
    at rest and surfaced only to attendees.
    """

    mode: Literal["onsite", "online", "phone"]
    scheduled_at: datetime
    assignee_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)
    duration_minutes: int = Field(default=60, ge=5, le=600)
    location: str | None = Field(default=None, max_length=500)
    meeting_link: str | None = Field(default=None, max_length=1000)
    title: str | None = Field(default=None, max_length=150)
    notes: str | None = Field(default=None, max_length=5000)


class InterviewRescheduleBody(BaseModel):
    """``PATCH /applications/{id}/interviews/{interview_id}`` — reschedule / edit.

    All fields optional; an omitted field is left unchanged. Optimistic ``version``
    (stale -> 409).
    """

    scheduled_at: datetime | None = None
    mode: Literal["onsite", "online", "phone"] | None = None
    location: str | None = Field(default=None, max_length=500)
    meeting_link: str | None = Field(default=None, max_length=1000)
    title: str | None = Field(default=None, max_length=150)
    notes: str | None = Field(default=None, max_length=5000)
    version: int | None = None


class InterviewAssigneesBody(BaseModel):
    """``PUT /applications/{id}/interviews/{interview_id}/assignees`` — replace set."""

    assignee_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)


class InterviewCancelBody(BaseModel):
    """``POST /applications/{id}/interviews/{interview_id}/cancel`` — version only."""

    version: int | None = None


class InterviewCompleteBody(BaseModel):
    """``POST /applications/{id}/interviews/{interview_id}/complete``."""

    outcome: Literal["completed", "no_show"]
    version: int | None = None


class OfferCreateBody(BaseModel):
    """``POST /applications/{id}/offers`` — create the draft offer (ADR-0007 §8).

    ``salary_amount`` is the gross comp figure; it is Fernet-encrypted at rest and
    surfaced only to the recruiter + owning student (never a notification body, the
    board glance, or the ``offer.accepted`` event). ``expiry_date`` is the response
    deadline.
    """

    position_title: str = Field(min_length=1, max_length=255)
    department: str | None = Field(default=None, max_length=200)
    start_date: date | None = None
    salary_amount: int | None = Field(default=None, ge=0)
    salary_currency: str = Field(default="VND", max_length=5)
    salary_period: str = Field(default="monthly", max_length=20)
    benefits_summary: str | None = Field(default=None, max_length=5000)
    terms_notes: str | None = Field(default=None, max_length=5000)
    expiry_date: datetime


class OfferUpdateBody(BaseModel):
    """``PATCH /applications/{id}/offers/{offer_id}`` — edit ONLY while ``draft``.

    All fields optional; an omitted field is left unchanged. Optimistic ``version``
    (stale -> 409).
    """

    position_title: str | None = Field(default=None, min_length=1, max_length=255)
    department: str | None = Field(default=None, max_length=200)
    start_date: date | None = None
    salary_amount: int | None = Field(default=None, ge=0)
    salary_currency: str | None = Field(default=None, max_length=5)
    salary_period: str | None = Field(default=None, max_length=20)
    benefits_summary: str | None = Field(default=None, max_length=5000)
    terms_notes: str | None = Field(default=None, max_length=5000)
    expiry_date: datetime | None = None
    version: int | None = None


class OfferSubmitBody(BaseModel):
    """``POST /offers/{offer_id}/submit`` — optimistic ``version`` only."""

    version: int | None = None


class OfferApproveBody(BaseModel):
    """``POST /offers/{offer_id}/approve`` — approve or reject-back to draft."""

    decision: Literal["approve", "reject"]
    version: int | None = None


class OfferSendBody(BaseModel):
    """``POST /offers/{offer_id}/send`` — optimistic ``version`` only."""

    version: int | None = None


class OfferRescindBody(BaseModel):
    """``POST /offers/{offer_id}/rescind`` — optimistic ``version`` only."""

    version: int | None = None


class OfferRespondBody(BaseModel):
    """``POST /offers/{offer_id}/respond`` — candidate accept/decline (ADR-0007 §3).

    Only ``accepted | declined`` in V1 (counter-offer deferred). ``notes`` becomes the
    partner-internal ``decline_reason`` on a decline. ``idempotency_key`` makes a
    network retry safe (the offer's terminal state is the natural idempotency anchor).
    """

    decision: Literal["accepted", "declined"]
    notes: str | None = Field(default=None, max_length=2000)
    idempotency_key: str = Field(min_length=1, max_length=200)


class RevealRequestBody(BaseModel):
    # Min-length 20 is enforced in the service for a friendly, field-scoped error.
    reason: str = Field(min_length=1, max_length=2000)


class RevealRespondBody(BaseModel):
    decision: str = Field(max_length=20)  # accepted | declined


# --------------------------------------------------------------------------- #
# Job application invitations                                                  #
# --------------------------------------------------------------------------- #


class InviteToApplyBody(BaseModel):
    student_id: uuid.UUID
    message: str | None = Field(default=None, max_length=500)


class InviteRespondBody(BaseModel):
    response: str = Field(max_length=20)  # accepted | declined
