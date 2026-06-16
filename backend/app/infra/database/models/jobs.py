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
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.enum import ApplicationStatus, ApprovalSource, JobStatus
from app.infra.database.models.base import SoftDeleteMixin, TimestampMixin, now_utc, uuid_str
from app.infra.database.session import Base


class Job(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "jobs"
    __table_args__ = (Index("ix_jobs_org_dept_status", "org_id", "dept_id", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    dept_id: Mapped[str | None] = mapped_column(ForeignKey("departments.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    parsed_requirements: Mapped[dict] = mapped_column(JSON, default=dict)
    embedding: Mapped[list | None] = mapped_column(JSON, nullable=True)
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), default=JobStatus.DRAFT, index=True)
    approval_source: Mapped[ApprovalSource | None] = mapped_column(
        Enum(ApprovalSource),
        nullable=True,
    )
    approved_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


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
