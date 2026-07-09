"""Mock Interview ORM models.

Two tables, named to avoid any collision with ``recruitment`` real interviews
(``interviews`` / ``interview_assignees``) and with the ephemeral
``interview_sim`` task:

- ``mock_interview_sessions`` — one practice session, student-owned.
- ``mock_interview_turns`` — the transcript (TEXT ONLY, never audio at rest).

Privacy/leak-safety invariants (see ``.claude/rules/ai.md``):
- ``provider_ref`` / ``model_ref`` store LEAK-SAFE ALIASES only (never a vendor or
  concrete model id). The API presenter strips them entirely.
- ``text`` is the transcript; ``text_redacted`` is a ``redact_pii`` copy used for
  pseudonymized AI-ops review so debugging never requires reading raw PII.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.models import Base, JsonType

# --- status / modality vocabularies (domain constants) --------------------- #
MODALITY_VOICE = "voice"  # browser-native STT/TTS driving the text brain (Tier V1)
MODALITY_TEXT = "text"  # typed practice (Tier T / accessibility floor)
MODALITY_REALTIME = "realtime"  # native provider speech-to-speech (Tier V2)
MODALITIES = frozenset({MODALITY_VOICE, MODALITY_TEXT, MODALITY_REALTIME})

STATUS_ACTIVE = "active"
STATUS_COMPLETED = "completed"
STATUS_EXPIRED = "expired"
STATUS_ABORTED = "aborted"
STATUSES = frozenset({STATUS_ACTIVE, STATUS_COMPLETED, STATUS_EXPIRED, STATUS_ABORTED})

SPEAKER_INTERVIEWER = "interviewer"
SPEAKER_CANDIDATE = "candidate"
SPEAKERS = frozenset({SPEAKER_INTERVIEWER, SPEAKER_CANDIDATE})


def _utcnow() -> datetime:
    return datetime.now(UTC)


class MockInterviewSession(Base):
    """A single student-owned mock-interview practice session."""

    __tablename__ = "mock_interview_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Owner. Every session/turn/report query is hard-scoped to this user in the
    # application layer; partners never reach this table.
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    # The CV chosen to interview against. SET NULL so deleting a CV never orphans
    # or blocks a stored transcript the student may still want to review.
    cv_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("cv_profiles.id", ondelete="SET NULL"), nullable=True
    )

    locale: Mapped[str] = mapped_column(String(8), nullable=False, default="vi")
    modality: Mapped[str] = mapped_column(
        String(16), nullable=False, default=MODALITY_VOICE
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=STATUS_ACTIVE
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    question_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Frozen grounding (JD+CV projection the prompts consume). Stored at create so
    # every turn + the report use a stable interview even if the CV/JD later change,
    # and so per-turn grounding is not re-derived. Leak-safe (no provider/model).
    grounding_json: Mapped[dict | None] = mapped_column(JsonType, nullable=True)
    # Coaching report (NO score fields — see report_service). Nullable until end.
    report_json: Mapped[dict | None] = mapped_column(JsonType, nullable=True)

    # Student opt-in (consent-backed) to let pseudonymized transcripts feed AI
    # quality improvement. Defaults false; mirrors the compliance consent row.
    share_opt_in: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Set true when a safety guard flags a turn; drives moderation escalation and
    # the aggregate flag counts university governance sees.
    flagged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # INTERNAL — never serialized to any client. Leak-safe ALIASES only.
    provider_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    grounding_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    turns: Mapped[list[MockInterviewTurn]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="MockInterviewTurn.seq",
    )

    __table_args__ = (
        Index("ix_mock_interview_sessions_user_id", "user_id"),
        Index("ix_mock_interview_sessions_user_created", "user_id", "created_at"),
        Index("ix_mock_interview_sessions_job_id", "job_id"),
        Index("ix_mock_interview_sessions_status", "status"),
        # Concurrency guard (ADR-0016 §5 "1 concurrent session"): the DB — not a
        # check-then-insert race — guarantees at most ONE active session per user.
        # Partial unique index works on both Postgres and SQLite (3.8+).
        Index(
            "uq_mock_interview_one_active_per_user",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
            sqlite_where=text("status = 'active'"),
        ),
    )


class MockInterviewTurn(Base):
    """One transcript turn. TEXT ONLY — audio is never persisted."""

    __tablename__ = "mock_interview_turns"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("mock_interview_sessions.id", ondelete="CASCADE"), nullable=False
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    speaker: Mapped[str] = mapped_column(String(16), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # ``redact_pii`` copy for pseudonymized AI-ops review. Null until persisted.
    text_redacted: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    session: Mapped[MockInterviewSession] = relationship(back_populates="turns")

    __table_args__ = (
        # Unique per session so two concurrent turn writers cannot mint the same
        # seq and corrupt transcript ordering (backstop to per-session locking).
        Index(
            "uq_mock_interview_turns_session_seq",
            "session_id",
            "seq",
            unique=True,
        ),
    )
