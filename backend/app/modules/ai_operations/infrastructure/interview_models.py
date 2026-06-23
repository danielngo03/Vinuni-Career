from __future__ import annotations

from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.platform.database.models.base import TimestampMixin, uuid_str
from app.platform.database.session import Base


class AIInterviewSession(Base, TimestampMixin):
    __tablename__ = "ai_interview_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    cv_id: Mapped[str] = mapped_column(ForeignKey("cvs.id"), index=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    current_phase: Mapped[str] = mapped_column(String(40), default="career")
    question_count: Mapped[int] = mapped_column(Integer, default=0)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    cv_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    jd_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    matching_result: Mapped[dict] = mapped_column(JSON, default=dict)
    coverage_state: Mapped[dict] = mapped_column(JSON, default=dict)
    evaluation_state: Mapped[dict] = mapped_column(JSON, default=dict)

    turns: Mapped[list[AIInterviewTurn]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="AIInterviewTurn.sequence",
    )


class AIInterviewTurn(Base, TimestampMixin):
    __tablename__ = "ai_interview_turns"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("ai_interview_sessions.id"),
        index=True,
    )
    sequence: Mapped[int] = mapped_column(Integer)
    phase: Mapped[str] = mapped_column(String(40))
    topic_key: Mapped[str] = mapped_column(String(160))
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    internal_output: Mapped[dict] = mapped_column(JSON, default=dict)

    session: Mapped[AIInterviewSession] = relationship(back_populates="turns")
