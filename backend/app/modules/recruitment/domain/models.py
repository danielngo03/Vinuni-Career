"""Recruitment ORM models (``docs/DATA_MODEL.md`` §9).

Phase 1e owns ``applications`` and ``application_reveal_requests``. Types use the
shared cross-database variants (``JsonType``) so the same models run on
PostgreSQL (runtime) and SQLite (unit tests). Postgres-only constructs (partial /
unique-active indexes, ``set_updated_at`` trigger, the deferred
``application_cv_snapshots`` FK + NOT NULL) live in migration ``0006`` only.

Documented deviations from the canonical ``docs/DATA_MODEL.md`` §9 columns
(necessary because the ``student_profiles`` module is not yet built):

- ``applications.applicant_id`` references ``users(id)`` directly instead of
  ``student_profiles(id)`` (that module is Phase 2). The applicant is always the
  acting student user.
- ``applications.org_id`` — denormalized from ``jobs.org_id`` so partner reads are
  org-scoped without a join (``docs/ARCHITECTURE.md`` read-model guidance).
- ``applications.snapshot_id`` — convenience FK to the immutable CV snapshot
  created at submit time (the reverse ``application_cv_snapshots.application_id``
  link is owned by the documents module). No ORM FK is declared on the snapshot
  side here to avoid an ORM metadata create cycle; the migration adds it on
  Postgres.
- ``applications.idempotency_key`` — submit idempotency (``docs/API_CONTRACTS.md``).
- ``application_reveal_requests`` is the apply-flow reveal table (the broader
  ``contact_reveal_requests`` of the data model also serves passive search, a
  later phase); shape is identical for the apply use case.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import Base, JsonType


class Application(Base):
    """A student's application to a job. Soft-deleted only; never mutated content
    once submitted beyond status transitions (the CV is captured immutably in a
    separate snapshot)."""

    __tablename__ = "applications"

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    applicant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="submitted")
    cover_letter: Mapped[str | None] = mapped_column(Text, nullable=True)
    screening_answers: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)
    is_anonymous: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("application_cv_snapshots.id", ondelete="SET NULL"), nullable=True
    )
    reveal_approved_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reveal_approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rejection_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)
    rejection_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_status_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        onupdate=func.now(),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


# --------------------------------------------------------------------------- #
# Pipeline stage engine (ADR-0004 §3 / §6)                                     #
# --------------------------------------------------------------------------- #
#
# ``pipeline_templates`` / ``pipeline_stages`` carry the per-org CONFIGURABLE
# stage schema (PRD MODULE 7). V1 does not build the template editor: exactly one
# immutable ``is_default = is_system = true`` template is seeded per org (migration
# ``0012`` data step + the service's lazy ``ensure_org_default_template``).
#
# ``candidate_stages`` IS the append-only stage history (ADR-0004 §3): a row is
# inserted on entry and only ever closed once (``exited_at`` + ``exit_kind`` +
# terminal ``status`` set); no row is mutated again and none is deleted. The
# "at most one ACTIVE row per application" invariant is enforced by a Postgres
# partial unique index (migration ``0012``, dialect-guarded); SQLite unit tests
# rely on the service-layer guard. As with ``uq_applications_active`` the partial
# index is intentionally NOT declared on the ORM model so ``create_all`` does not
# emit it on SQLite.


class PipelineTemplate(Base):
    """A per-org ordered pipeline definition. V1 seeds one system default per org."""

    __tablename__ = "pipeline_templates"

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PipelineStage(Base):
    """One ordered stage of a :class:`PipelineTemplate`.

    ``stage_type`` is metadata for UI/notification labeling only — the engine
    branches on ``sort_order`` + ``required_action``, never on type. V1 stores the
    coarse ``DATA_MODEL`` §9 set (``screening|interview|assessment|offer|custom``).
    """

    __tablename__ = "pipeline_stages"
    __table_args__ = (
        UniqueConstraint("template_id", "sort_order", name="uq_pipeline_stage_order"),
    )

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    template_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pipeline_templates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    stage_type: Mapped[str] = mapped_column(String(30), nullable=False)
    sort_order: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    required_action: Mapped[str] = mapped_column(
        String(30), nullable=False, default="manual"
    )
    sla_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # ADR-0006: average-score gate for ``required_action='score_threshold'``;
    # nullable (meaningful only for that action). NUMERIC(2,1) matches overall_score.
    score_threshold: Mapped[Decimal | None] = mapped_column(Numeric(2, 1), nullable=True)
    is_terminal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    candidate_visible: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    automation_rules: Mapped[dict] = mapped_column(
        JsonType, nullable=False, default=dict
    )


class CandidateStage(Base):
    """Append-only stage-history row for an application (ADR-0004 §3).

    ``status ∈ {ACTIVE, PASSED, ROLLED_BACK, REJECTED}``; ``exit_kind ∈
    {advanced, rolled_back, rejected}``. A row is created ACTIVE on entry and
    closed exactly once on exit. ``idempotency_key`` stores the move's
    Idempotency-Key so an at-least-once retry never double-advances.
    """

    __tablename__ = "candidate_stages"

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stage_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pipeline_stages.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    entered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    entered_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    exited_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    exit_kind: Mapped[str | None] = mapped_column(String(20), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # SLA reminder idempotency (§ scheduler job ``pipeline.sla_reminder_sweep``):
    # the highest threshold level already notified for THIS stage instance
    # (``approaching`` at 80% of ``sla_hours`` elapsed, ``overdue`` at 100%+) plus
    # when it was sent. A re-tick only escalates (never re-sends the same or a
    # lower level), so the sweep is safe to run at any cadence.
    sla_reminder_level: Mapped[str | None] = mapped_column(String(20), nullable=True)
    sla_reminder_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


# --------------------------------------------------------------------------- #
# Scorecards (ADR-0005 §1/§5)                                                   #
# --------------------------------------------------------------------------- #
#
# A ``Scorecard`` is ONE reviewer's evaluation of ONE candidate at ONE pipeline
# stage. Unlike ``candidate_stages`` (append-only), a scorecard is EDITABLE in
# place by its author: re-submit upserts the row + its ``scorecard_scores`` and
# bumps the per-scorecard optimistic ``version``; withdraw is a soft ``status``
# transition (the row survives for the audit trail, excluded from gate/aggregate).
#
# Cardinality "one ACTIVE scorecard per (application, stage, reviewer)" is enforced
# by a Postgres PARTIAL unique index ``uq_scorecard_reviewer_active ... WHERE
# status = 'submitted'`` (migration ``0013``, dialect-guarded). As with
# ``uq_candidate_stage_active`` it is intentionally NOT declared on the ORM model
# so ``create_all`` omits it on SQLite (unit tests rely on the service-layer
# upsert guard).
#
# A scorecard carries NO student-identity field — it references ``application_id``
# (already redacted on every partner projection); the reveal handshake stays the
# only identity path. ``interview_id`` (DATA_MODEL §9) is added nullable by
# ADR-0006; V1 binds to ``application_id`` + ``stage_id`` directly.


class Scorecard(Base):
    """One reviewer's submitted evaluation of a candidate at a pipeline stage."""

    __tablename__ = "scorecards"

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stage_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pipeline_stages.id", ondelete="RESTRICT"), nullable=False
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    submitted_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    # ADR-0006: the interview this scorecard evaluates (auto-linked on submit when an
    # open interview exists for the stage). Nullable; ``ON DELETE SET NULL`` so
    # deleting an interview never cascades away evaluation history.
    interview_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("interviews.id", ondelete="SET NULL"), nullable=True, index=True
    )
    recommendation: Mapped[str] = mapped_column(String(20), nullable=False)
    overall_score: Mapped[Decimal | None] = mapped_column(
        Numeric(2, 1), nullable=True
    )
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="submitted"
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        onupdate=func.now(),
    )


class ScorecardScore(Base):
    """One criterion score (1..5) of a :class:`Scorecard` (normalized, not JSONB).

    Normalized so per-criterion aggregation (board summary, the deferred §7.8
    comparison view, future ``score_threshold`` gating) is a SQL ``GROUP BY`` and
    the future criteria editor can map ``criterion_key -> criterion_id`` with no
    data rewrite. Replaced (delete+insert) when the author edits the scorecard.
    """

    __tablename__ = "scorecard_scores"
    __table_args__ = (
        UniqueConstraint("scorecard_id", "criterion_key", name="uq_scorecard_score_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    scorecard_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scorecards.id", ondelete="CASCADE"), nullable=False, index=True
    )
    criterion_key: Mapped[str] = mapped_column(String(40), nullable=False)
    score: Mapped[int] = mapped_column(SmallInteger, nullable=False)


# --------------------------------------------------------------------------- #
# Interviews + reviewer assignees (ADR-0006 §1/§5)                              #
# --------------------------------------------------------------------------- #
#
# An ``Interview`` is ONE editable-in-place scheduled round for an application at a
# pipeline stage (the round IS the stage; the interview carries only a delivery
# ``mode ∈ {onsite, online, phone}``). Unlike ``candidate_stages`` it is mutable:
# reschedule/cancel/complete edit the row in place + bump the optimistic
# ``version``; the full history lives in audit.
#
# ``meeting_link`` is FERNET-ENCRYPTED at rest and decrypted only when rendering an
# ATTENDEE surface (candidate + assigned interviewers); it never appears on the
# board glance or any non-attendee/student surface.
#
# "At most one OPEN (scheduled) interview per (application, stage)" is enforced by a
# Postgres PARTIAL unique index ``uq_interview_open_per_stage ... WHERE
# status='scheduled'`` (migration ``0014``, dialect-guarded); SQLite unit tests rely
# on the service-layer guard. An interview carries NO student-identity field — the
# reveal handshake stays the only identity path (scheduling an anonymous interview
# REQUIRES an already-accepted reveal, enforced in the service).


class Interview(Base):
    """One scheduled interview round for an application at a pipeline stage."""

    __tablename__ = "interviews"

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stage_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pipeline_stages.id", ondelete="RESTRICT"), nullable=False
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    title: Mapped[str | None] = mapped_column(String(150), nullable=True)
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    duration_minutes: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=60
    )
    location: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Fernet ciphertext (urlsafe base64) — never stored as plaintext at rest.
    meeting_link: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="scheduled"
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        onupdate=func.now(),
    )


class InterviewAssignee(Base):
    """One assigned interviewer (partner-org member) on an :class:`Interview`.

    PERSON mode (V1): an explicit list; ``threshold_pct = 1.0`` so the advance gate
    requires ALL assigned interviewers to submit. This set is the gate's ``required``
    denominator. DEPARTMENT mode + fractional thresholds are deferred (ADR-0006 §7).
    """

    __tablename__ = "interview_assignees"
    __table_args__ = (
        UniqueConstraint("interview_id", "user_id", name="uq_interview_assignee"),
    )

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    interview_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("interviews.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


# --------------------------------------------------------------------------- #
# Offers (ADR-0007 §1/§7)                                                       #
# --------------------------------------------------------------------------- #
#
# An ``Offer`` is the terminal POSITIVE outcome of the pipeline — the only path to
# ``applications.status='hired'``. It carries comp + a response deadline + an
# 8-state approval/response machine (``draft | pending_approval | approved | sent |
# accepted | declined | expired | rescinded``). Content is mutable in place ONLY
# while ``draft`` (frozen at submit so the candidate never sees post-send comp
# drift); from ``pending_approval`` onward only status transitions mutate the row.
#
# ``salary_amount`` is FERNET-ENCRYPTED at rest (recruiter + owning-student only,
# DATA_MODEL §17): it is decrypted only when rendering a recruiter or the owning
# student surface and NEVER appears in a notification/email body, the board glance,
# or the ``offer.accepted`` event payload.
#
# "At most one LIVE offer per application" (LIVE = draft/pending_approval/approved/
# sent) is enforced by a Postgres PARTIAL unique index
# ``uq_offer_live_per_application ... WHERE status IN (...)`` (migration ``0015``,
# dialect-guarded); SQLite unit tests rely on the service-layer guard. An offer
# carries NO student-identity field — the reveal handshake stays the only identity
# path (SENDING an anonymous offer REQUIRES an already-accepted reveal, §5).


class Offer(Base):
    """A comp offer extended to a candidate at the Offer pipeline stage."""

    __tablename__ = "offers"

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stage_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pipeline_stages.id", ondelete="RESTRICT"), nullable=False
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    position_title: Mapped[str] = mapped_column(String(255), nullable=False)
    department: Mapped[str | None] = mapped_column(String(200), nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Fernet ciphertext (urlsafe base64) — never stored in plaintext at rest.
    salary_amount: Mapped[str | None] = mapped_column(String(255), nullable=True)
    salary_currency: Mapped[str] = mapped_column(
        String(5), nullable=False, default="VND"
    )
    salary_period: Mapped[str] = mapped_column(
        String(20), nullable=False, default="monthly"
    )
    benefits_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    terms_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    expiry_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    student_response_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    decline_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        onupdate=func.now(),
    )


class ApplicationTimelineEvent(Base):
    """Real, append-only student-facing timeline event for an application.

    ``docs/DATA_MODEL.md`` §32 — a single narrative timeline the student projection
    reads from, replacing the frontend's prior client-side guess derived from
    ``status`` alone. ``label_en``/``label_vi`` are the FRIENDLY, neutral copy
    stored at write time (``domain/timeline.py``); ``event_metadata`` MAY carry
    partner-internal detail (rejection reason code, target stage name) for audit
    but is NEVER surfaced to the student projection for those partner-internal
    event types (``api/presenters.py`` / ``application/timeline.py`` enforce this).
    Rows are never mutated or deleted — one row per emitted event, in the SAME
    transaction as the state change it records.
    """

    __tablename__ = "application_timeline_events"

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(60), nullable=False)
    label_en: Mapped[str] = mapped_column(String(200), nullable=False)
    label_vi: Mapped[str] = mapped_column(String(200), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    event_metadata: Mapped[dict] = mapped_column(
        "metadata", JsonType, nullable=False, default=dict
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ApplicationRevealRequest(Base):
    """A partner's request to reveal an anonymous applicant's identity.

    One request per (application, requester_org); 72h expiry. The student
    accepts/declines; on accept the partner may see identity + download the CV.
    """

    __tablename__ = "application_reveal_requests"
    __table_args__ = (
        UniqueConstraint("application_id", "requester_org_id", name="uq_reveal_app_org"),
    )

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    requester_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    requester_org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    responded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


# --------------------------------------------------------------------------- #
# Job application invitations (partner → student outreach)                     #
# --------------------------------------------------------------------------- #


class JobApplicationInvitation(Base):
    """A partner's direct invitation for a specific student to apply to a job.

    One active invitation per (job_id, student_id) is enforced by a partial
    unique index on Postgres (migration 0036); SQLite tests rely on the service
    guard. Status flow: pending → accepted | declined | expired.
    When accepted the service auto-creates an Application.
    """

    __tablename__ = "job_application_invitations"

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    inviting_org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    inviting_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    responded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        onupdate=func.now(),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
