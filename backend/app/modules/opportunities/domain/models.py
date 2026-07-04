"""Opportunities (jobs) ORM models (``docs/DATA_MODEL.md`` §8).

``jobs`` carries the full posting + lifecycle + moderation state; screening
questions are modeled relationally in ``screening_questions`` (CASCADE on job
delete). Types use the shared cross-database variants so the same models run on
PostgreSQL (runtime) and SQLite (unit tests). Postgres-only constructs
(``tsv_search`` generated column, GIN / partial indexes, ``set_updated_at``
trigger) live in migration ``0004`` only.

Additions beyond the canonical ``docs/DATA_MODEL.md`` §8 columns, documented here:

- ``visibility``: the §5 visibility matrix level, stored as a first-class column
  so it can be enforced at the DB query layer (the doc describes the matrix but
  did not pin a column). Default ``public``.
- ``submitted_at``: timestamp of the draft -> pending_review transition, mirroring
  the partner-registration ``reviewed_at`` audit-friendly pattern.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import Base, JsonType

# ---------------------------------------------------------------------------
# JobTranslation is imported by translation_service and the router; it is
# defined further down in this module (after Job) to preserve readability.
# ---------------------------------------------------------------------------


class Job(Base):
    """A partner job posting. Never hard-deleted (soft delete via ``deleted_at``)."""

    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), nullable=False, index=True
    )
    posted_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(300), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    requirements: Mapped[str | None] = mapped_column(Text, nullable=True)
    benefits: Mapped[str | None] = mapped_column(Text, nullable=True)

    employment_type: Mapped[str] = mapped_column(String(30), nullable=False)
    location_type: Mapped[str] = mapped_column(String(20), nullable=False)
    location_city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    location_country: Mapped[str] = mapped_column(
        String(100), nullable=False, default="Vietnam"
    )
    # Multi-location: each item is {type, city, country}. First item mirrors the
    # legacy location_type/city/country fields for backward compat. Empty = use
    # legacy fields only.
    locations: Mapped[list] = mapped_column(JsonType, nullable=False, default=list)

    required_skills: Mapped[list] = mapped_column(
        JsonType, nullable=False, default=list
    )
    preferred_skills: Mapped[list] = mapped_column(
        JsonType, nullable=False, default=list
    )
    experience_min_years: Mapped[int | None] = mapped_column(
        SmallInteger, nullable=True
    )
    experience_max_years: Mapped[int | None] = mapped_column(
        SmallInteger, nullable=True
    )
    industry_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("industries.id", ondelete="SET NULL"), nullable=True, index=True
    )
    degree_required: Mapped[str | None] = mapped_column(String(30), nullable=True)
    seniority_level: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # Structured candidate eligibility/preferences. Shape is validated at the API
    # layer and intentionally JSON-backed so partners can express "not required",
    # multiple nationalities, age ranges, preferred-only requirements, etc.
    candidate_requirements: Mapped[dict] = mapped_column(
        JsonType, nullable=False, default=dict
    )

    salary_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_currency: Mapped[str] = mapped_column(
        String(5), nullable=False, default="VND"
    )
    salary_is_disclosed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    # Structured salary mode (B-544/B-545): authoritative source for
    # `salary_is_disclosed` + min/max semantics. See ``api/schemas.py``
    # ``JobCreateRequest`` model_validator for the mode/min/max consistency rules.
    # 'negotiable' | 'hidden' | 'fixed' | 'range' | 'from' | 'to'
    salary_mode: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # 'monthly' | 'yearly'
    salary_period: Mapped[str] = mapped_column(
        String(10), nullable=False, default="monthly"
    )
    # 'unspecified' | 'gross' | 'net'
    salary_gross_net: Mapped[str] = mapped_column(
        String(15), nullable=False, default="unspecified"
    )
    # Structured experience mode, mirrors salary_mode.
    # 'no_requirement' | 'fresher' | 'range' | 'min' | 'max'
    experience_mode: Mapped[str | None] = mapped_column(String(20), nullable=True)
    headcount: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    application_deadline: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    visibility: Mapped[str] = mapped_column(
        String(20), nullable=False, default="public"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="draft"
    )  # draft|pending_review|active|closed|expired|rejected
    moderation_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )  # pending|approved|rejected|flagged
    moderation_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Structured rejection/escalation reason code (``app.shared.moderation``);
    # ``moderation_note`` remains the optional supplementary free-text field for
    # backward compatibility with the original free-text-only reason.
    moderation_reason_code: Mapped[str | None] = mapped_column(
        String(30), nullable=True
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # SLA deadline computed at submission time (``settings.job_moderation_sla_hours``).
    due_by: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Moderator currently reviewing this job (claim/assign). Cleared on
    # approve/reject/re-submit.
    claimed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    view_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    application_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    is_featured: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_sponsored: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    settings: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)

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
    # BCP-47 language code of the original JD content (detect at create time).
    # Default "en" matches the server_default in migration 0038.
    language_code: Mapped[str] = mapped_column(
        String(10), nullable=False, default="en"
    )


class JobTranslation(Base):
    """AI-generated translation cache for a job posting.

    Composite primary key (job_id, target_lang) guarantees at-most-one cached
    translation per language. The ``translated_by`` column records the AI model
    alias used (internal only — never exposed via public API). Cascade-deleted
    when the parent job is hard-deleted (soft-deleted jobs keep their cache).
    """

    __tablename__ = "job_translations"

    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True
    )
    target_lang: Mapped[str] = mapped_column(String(10), primary_key=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    requirements: Mapped[str | None] = mapped_column(Text, nullable=True)
    benefits: Mapped[str | None] = mapped_column(Text, nullable=True)
    # AI model alias used — internal only, never surfaced to users.
    translated_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class SavedJob(Base):
    """Student-favourited job posting. Unique per (user, job)."""

    __tablename__ = "saved_jobs"

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    saved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (UniqueConstraint("user_id", "job_id", name="uq_saved_jobs_user_job"),)


class JobAlert(Base):
    """Student subscription to new-job notifications matching saved criteria.

    When new jobs are published, the alert matching service compares them against
    each active alert and dispatches in-app + email notifications per the
    student's preference. Max 10 active alerts per user (enforced in service layer).
    """

    __tablename__ = "job_alerts"

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    keywords: Mapped[str | None] = mapped_column(String(255), nullable=True)
    employment_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    location_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    province_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_job_alerts_user_name"),
    )


class ScreeningQuestion(Base):
    """A per-job applicant screening question (CASCADE on job delete)."""

    __tablename__ = "screening_questions"

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    q_type: Mapped[str] = mapped_column(String(20), nullable=False)
    options: Mapped[list | None] = mapped_column(JsonType, nullable=True)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
