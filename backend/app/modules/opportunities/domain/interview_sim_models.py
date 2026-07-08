"""Interview Simulator persistence models (WS-6, Task K).

The interview simulator was ephemeral: generated questions, student answers, and
AI coaching feedback vanished after each request, so a student could never see a
progress/readiness trend across practice attempts. These two tables make the
simulator durable and STUDENT-SCOPED so the ``/student/interview-history`` read
can compute an honest, deterministic readiness signal over real attempts.

Grain:
- ``interview_sim_sessions``: one row per practice attempt (a student opens
  interview prep for a job). Aggregates (``answered_count`` / ``avg_score``) are
  denormalized on the session so the history read never scans every turn.
- ``interview_sim_turns``: one row per ANSWERED question — the question, the
  student's own answer, and the coaching feedback (score/praise/improve/hint).

Ownership: every row carries ``user_id`` (the owning student). Reads and writes
are owner-checked in the service layer; a partner or another student never sees
these rows, and they are never surfaced to the hiring org.

Privacy: no provider/model/token/prompt internals are stored — only the
user-facing question text, the student's own practice answer, and the coaching
feedback fields. ``job_id`` is kept nullable (``SET NULL`` on job delete) with a
denormalized ``job_title`` snapshot so a student's progress history survives a
job being removed.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import Base


class InterviewSimSession(Base):
    """One student practice attempt (interview prep opened for a job)."""

    __tablename__ = "interview_sim_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Owning student — every read/write is scoped + owner-checked by this.
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # The job practised for. Nullable + SET NULL so history survives job removal.
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Denormalized snapshot so the history read needs no jobs join and survives
    # a deleted job.
    job_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Hiring org at attempt time (nullable — kept for future scoped analytics).
    org_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)

    # Number of questions generated for this attempt.
    questions_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    # Denormalized count of answered/evaluated turns (running).
    answered_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    # Running average feedback score (1-5) over answered turns; NULL until the
    # first answer is evaluated. This is the readiness signal's raw input.
    avg_score: Mapped[float | None] = mapped_column(Numeric(4, 2), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class InterviewSimTurn(Base):
    """One answered question within a practice attempt (Q + answer + feedback)."""

    __tablename__ = "interview_sim_turns"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("interview_sim_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Denormalized owner so owner-checks / history queries need no session join.
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    question_number: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    question_type: Mapped[str] = mapped_column(String(32), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    rubric: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The student's own practice answer (never shown to the hiring org).
    answer: Mapped[str] = mapped_column(Text, nullable=False)

    # Coaching feedback (user-facing product content — NOT model internals).
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    praise: Mapped[str | None] = mapped_column(Text, nullable=True)
    improve: Mapped[str | None] = mapped_column(Text, nullable=True)
    hint: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Whether the feedback was the static fallback (AI unavailable).
    is_fallback: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
