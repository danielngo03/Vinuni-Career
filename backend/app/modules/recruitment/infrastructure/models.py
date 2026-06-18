from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.platform.database.models.base import SoftDeleteMixin, TimestampMixin, now_utc, uuid_str
from app.platform.database.session import Base
from app.shared.enum import ApplicationStatus, InterviewStatus, InterviewType


class CV(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "cvs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    student_id: Mapped[str] = mapped_column(ForeignKey("student_profiles.id"), index=True)
    file_id: Mapped[str | None] = mapped_column(ForeignKey("files.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(255), default="My Resume")
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    experience_years: Mapped[float | None] = mapped_column(Numeric(4, 1), nullable=True)
    skills: Mapped[list | None] = mapped_column(JSON, nullable=True)
    education_history: Mapped[list | None] = mapped_column(JSON, nullable=True)
    work_experience: Mapped[list | None] = mapped_column(JSON, nullable=True)
    certificates: Mapped[list | None] = mapped_column(JSON, nullable=True)
    projects: Mapped[list | None] = mapped_column(JSON, nullable=True)
    awards: Mapped[list | None] = mapped_column(JSON, nullable=True)
    parsed_data: Mapped[dict] = mapped_column(JSON, default=dict)
    masked_data: Mapped[dict] = mapped_column(JSON, default=dict)
    embedding: Mapped[list | None] = mapped_column(JSON, nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)

class JobApplication(Base, TimestampMixin):
    __tablename__ = "job_applications"
    __table_args__ = (
        UniqueConstraint("job_id", "student_id", name="uq_job_applications_job_student"),
        Index("ix_job_applications_job_status", "job_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    student_id: Mapped[str] = mapped_column(ForeignKey("student_profiles.id"), index=True)
    cv_id: Mapped[str] = mapped_column(ForeignKey("cvs.id"))
    cover_letter: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ApplicationStatus] = mapped_column(
        Enum(ApplicationStatus), default=ApplicationStatus.APPLIED
    )
    ai_match_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    ai_reasoning: Mapped[dict] = mapped_column(JSON, default=dict)
    consent_to_unmask: Mapped[bool] = mapped_column(Boolean, default=False)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class ApplicationTrackingLog(Base):
    __tablename__ = "application_tracking_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    application_id: Mapped[str] = mapped_column(ForeignKey("job_applications.id"), index=True)
    changed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    old_status: Mapped[ApplicationStatus | None] = mapped_column(
        Enum(ApplicationStatus),
        nullable=True,
    )
    new_status: Mapped[ApplicationStatus] = mapped_column(Enum(ApplicationStatus))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class Interview(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "interviews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    application_id: Mapped[str] = mapped_column(ForeignKey("job_applications.id"), index=True)
    interview_type: Mapped[InterviewType] = mapped_column(Enum(InterviewType), default=InterviewType.HR_ROUND)
    status: Mapped[InterviewStatus] = mapped_column(Enum(InterviewStatus), default=InterviewStatus.SCHEDULED)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    meeting_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    application: Mapped[JobApplication] = relationship()
