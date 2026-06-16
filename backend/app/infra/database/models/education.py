from __future__ import annotations

from sqlalchemy import JSON, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.enum import JobStatus
from app.infra.database.models.base import TimestampMixin, uuid_str
from app.infra.database.session import Base


class EmployerMaterial(Base, TimestampMixin):
    __tablename__ = "employer_materials"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    file_id: Mapped[str | None] = mapped_column(ForeignKey("files.id"), nullable=True)
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), default=JobStatus.PENDING_APPROVAL)
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class InterviewQuestionBank(Base, TimestampMixin):
    __tablename__ = "interview_question_banks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    org_id: Mapped[str | None] = mapped_column(ForeignKey("organizations.id"), nullable=True)
    job_id: Mapped[str | None] = mapped_column(ForeignKey("jobs.id"), nullable=True)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    ai_suggested_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), default=JobStatus.PENDING_APPROVAL)


class MockInterview(Base, TimestampMixin):
    __tablename__ = "mock_interviews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    student_id: Mapped[str] = mapped_column(ForeignKey("student_profiles.id"), index=True)
    job_id: Mapped[str | None] = mapped_column(ForeignKey("jobs.id"), nullable=True)
    overall_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    feedback_summary: Mapped[str | None] = mapped_column(Text, nullable=True)


class MockInterviewTurn(Base, TimestampMixin):
    __tablename__ = "mock_interview_turns"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    interview_id: Mapped[str] = mapped_column(ForeignKey("mock_interviews.id"), index=True)
    question_id: Mapped[str | None] = mapped_column(
        ForeignKey("interview_question_banks.id"),
        nullable=True,
    )
    ai_question: Mapped[str] = mapped_column(Text, nullable=False)
    student_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    evaluation_json: Mapped[dict] = mapped_column(JSON, default=dict)


class AIChatSession(Base, TimestampMixin):
    __tablename__ = "ai_chat_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    context_type: Mapped[str] = mapped_column(String(120), nullable=False)


class AIChatMessage(Base, TimestampMixin):
    __tablename__ = "ai_chat_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    session_id: Mapped[str] = mapped_column(ForeignKey("ai_chat_sessions.id"), index=True)
    role: Mapped[str] = mapped_column(String(40), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
