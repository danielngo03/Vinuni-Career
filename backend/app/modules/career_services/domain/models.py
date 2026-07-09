"""Career-services ORM models (B-554: university counselor workspace).

Owns counselor-facing cohorts, at-risk flags, CV review queue items,
appointments, employer relationship notes, and intervention history.
``org_id`` on every row is the owning **university** organization (tenant
isolation mirrors ``organization`` conventions: a counselor from one university
org can never read/write another org's rows — enforced in the service layer via
``permission_checker.require(..., resource_org_id=org_id)``).

``student_id`` is a bare FK to ``users.id`` (students are not org members —
same convention as ``documents.cv_profiles.user_id``); ``counselor_id`` /
``author_id`` / etc. are university-staff ``users.id`` FKs.

Types use the shared cross-database variants (``JsonType``... not needed here,
plain columns only) so models run on PostgreSQL (runtime) and SQLite (unit
tests). The appointment double-booking guard uses a nullable ``conflict_key``
column (see :class:`Appointment` docstring) instead of a Postgres-only partial
unique index so the same invariant holds on both dialects.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import Base


class Cohort(Base):
    """A counselor-managed group of students (e.g. "Class of 2026 - CS")."""

    __tablename__ = "career_services_cohorts"
    __table_args__ = (UniqueConstraint("org_id", "name", name="uq_cs_cohort_org_name"),)

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_counselor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CohortMembership(Base):
    """A student's membership in a cohort. Idempotent: unique(cohort, student)."""

    __tablename__ = "career_services_cohort_memberships"
    __table_args__ = (UniqueConstraint("cohort_id", "student_id", name="uq_cs_cohort_member"),)

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    cohort_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("career_services_cohorts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    added_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AtRiskFlag(Base):
    """A counselor-raised at-risk signal for a student, with a resolution lifecycle."""

    __tablename__ = "career_services_at_risk_flags"

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    cohort_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("career_services_cohorts.id", ondelete="SET NULL"), nullable=True
    )
    reason_code: Mapped[str] = mapped_column(String(50), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="medium")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    flagged_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class CvReviewQueueItem(Base):
    """A student's CV queued for counselor review (feedback + assignment)."""

    __tablename__ = "career_services_cv_review_items"

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    cv_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("cv_profiles.id", ondelete="SET NULL"), nullable=True
    )
    requested_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    assigned_counselor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="queued")
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="normal")
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Appointment(Base):
    """A counselor <-> student appointment.

    Double-booking guard: ``conflict_key`` mirrors ``scheduled_at`` while the
    appointment holds the counselor's calendar (``requested``/``confirmed``) and
    is set to ``NULL`` once the slot is released (``cancelled``/``no_show``).
    ``UniqueConstraint(counselor_id, conflict_key)`` then blocks a second active
    booking for the same counselor at the same instant on both PostgreSQL and
    SQLite (standard SQL: NULLs never conflict in a unique constraint), while
    still allowing the slot to be rebooked after a cancellation.
    """

    __tablename__ = "career_services_appointments"
    __table_args__ = (
        UniqueConstraint("counselor_id", "conflict_key", name="uq_cs_appt_counselor_slot"),
    )

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    counselor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    conflict_key: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_minutes: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=30)
    mode: Mapped[str] = mapped_column(String(20), nullable=False, default="in_person")
    location: Mapped[str | None] = mapped_column(String(300), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="requested")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class EmployerRelationshipNote(Base):
    """A counselor's note about an employer relationship."""

    __tablename__ = "career_services_employer_notes"

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employer_org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    category: Mapped[str] = mapped_column(String(30), nullable=False, default="general")
    visibility: Mapped[str] = mapped_column(String(30), nullable=False, default="all_staff")
    note_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class InterventionRecord(Base):
    """A logged counselor intervention for a student, with an outcome."""

    __tablename__ = "career_services_interventions"

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    counselor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    intervention_type: Mapped[str] = mapped_column(String(40), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    outcome: Mapped[str] = mapped_column(String(30), nullable=False, default="no_outcome_yet")
    linked_appointment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("career_services_appointments.id", ondelete="SET NULL"),
        nullable=True,
    )
    linked_at_risk_flag_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("career_services_at_risk_flags.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


# Re-export for the central model registry / Alembic autogenerate metadata.
__all__ = [
    "Cohort",
    "CohortMembership",
    "AtRiskFlag",
    "CvReviewQueueItem",
    "Appointment",
    "EmployerRelationshipNote",
    "InterventionRecord",
]
