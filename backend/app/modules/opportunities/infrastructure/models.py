from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.platform.database.models.base import SoftDeleteMixin, TimestampMixin, now_utc, uuid_str
from app.platform.database.models.identity import Organization
from app.platform.database.models.student import StudentProfile
from app.platform.database.session import Base
from app.shared.enum import (
    ApprovalSource,
    EventRegistrationStatus,
    EventStatus,
    EventType,
    ExperienceLevel,
    JobStatus,
    JobType,
    LocationType,
)


class Job(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "jobs"
    __table_args__ = (Index("ix_jobs_org_dept_status", "org_id", "dept_id", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    dept_id: Mapped[str | None] = mapped_column(ForeignKey("departments.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    requirements: Mapped[str | None] = mapped_column(Text, nullable=True)
    responsibilities: Mapped[str | None] = mapped_column(Text, nullable=True)
    benefits_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    industry: Mapped[str | None] = mapped_column(String(120), nullable=True)
    job_function: Mapped[str | None] = mapped_column(String(120), nullable=True)
    job_type: Mapped[JobType | None] = mapped_column(Enum(JobType), nullable=True)
    experience_level: Mapped[ExperienceLevel | None] = mapped_column(Enum(ExperienceLevel), nullable=True)
    location_type: Mapped[LocationType | None] = mapped_column(Enum(LocationType), nullable=True)
    location_address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    salary_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str] = mapped_column(String(10), default="VND")
    skills: Mapped[list | None] = mapped_column(JSON, nullable=True)
    benefits: Mapped[list | None] = mapped_column(JSON, nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    application_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False)
    max_openings: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parsed_requirements: Mapped[dict] = mapped_column(JSON, default=dict)
    embedding: Mapped[list | None] = mapped_column(JSON, nullable=True)
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), default=JobStatus.DRAFT, index=True)
    approval_source: Mapped[ApprovalSource | None] = mapped_column(
        Enum(ApprovalSource),
        nullable=True,
    )
    approved_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class Event(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "events"
    __table_args__ = (Index("ix_events_org_type_status", "org_id", "event_type", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    event_type: Mapped[EventType] = mapped_column(Enum(EventType), nullable=False, index=True)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    location_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    location_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    meeting_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    max_attendees: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[EventStatus] = mapped_column(Enum(EventStatus), default=EventStatus.DRAFT, index=True)
    approved_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    org: Mapped[Organization] = relationship()

class EventRegistration(Base, TimestampMixin):
    __tablename__ = "event_registrations"
    __table_args__ = (
        UniqueConstraint("event_id", "student_id", name="uq_event_registrations_event_student"),
        Index("ix_event_registrations_event_status", "event_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id"), index=True)
    student_id: Mapped[str] = mapped_column(ForeignKey("student_profiles.id"), index=True)
    status: Mapped[EventRegistrationStatus] = mapped_column(
        Enum(EventRegistrationStatus), default=EventRegistrationStatus.REGISTERED
    )
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    event: Mapped[Event] = relationship()
    student: Mapped[StudentProfile] = relationship()

class Bookmark(Base, TimestampMixin):
    __tablename__ = "bookmarks"
    __table_args__ = (
        UniqueConstraint("student_id", "job_id", name="uq_bookmark_student_job"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    student_id: Mapped[str] = mapped_column(ForeignKey("student_profiles.id"), index=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)

    student: Mapped[StudentProfile] = relationship()
    job: Mapped[Job] = relationship()
