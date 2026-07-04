"""Student-profile ORM models (``docs/DATA_MODEL.md`` §6, Phase 1f).

The ``student_profiles`` module owns the canonical student profile aggregate: the
core profile plus its child collections (education / experience / skills / links).
Types use the shared cross-database variants (``JsonType``) so the same models run
on PostgreSQL (runtime) and SQLite (unit tests); Postgres-only constructs
(partial / unique indexes, ``set_updated_at`` triggers) live in migration
``0007`` only.

Documented deviations from the canonical ``docs/DATA_MODEL.md`` §6 (kept narrow,
greenfield-namespaced, and noted for a follow-up doc reconciliation):

- Child tables are namespaced ``student_education`` / ``student_experience`` /
  ``student_skills`` / ``student_links`` (the data model uses ``educations`` /
  ``work_experiences`` for two of them). Namespacing keeps the module's tables
  grouped and avoids collisions; column shapes follow the data model.
- The per-field ``privacy_settings`` table of the data model is folded into the
  profile row as ``profile_visibility`` (an overall gate) + ``show_email`` /
  ``show_phone`` contact gates. The remaining career_preferences fields
  (``is_open_to_work`` / ``open_to_work_types`` / ``location``) live on the
  profile row. Splitting them back into side tables is a later slice.
- ``open_to_work_types`` / ``skills_used`` are ``JsonType`` arrays rather than
  Postgres ``VARCHAR[]`` so the same model builds on SQLite for tests.
- ``phone`` is stored in plaintext in this slice and gated by ``show_phone``;
  Fernet field-level encryption (``docs/SECURITY_PRIVACY.md``) is a documented
  follow-up — exposure is already privacy-gated, encryption-at-rest is additive.
- Children carry ``deleted_at`` + ``version`` (soft delete + optimistic locking)
  for safe owner CRUD; the data model only listed ``created_at`` on children.
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.modules.student_profiles.domain import vocab
from app.shared.models import BaseEntity, JsonType


class StudentProfile(BaseEntity):
    """The core student profile aggregate root (one per user)."""

    __tablename__ = "student_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    headline: Mapped[str | None] = mapped_column(String(255), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    location_city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    location_country: Mapped[str] = mapped_column(
        String(100), nullable=False, default="Vietnam"
    )
    major: Mapped[str | None] = mapped_column(String(200), nullable=True)
    degree_level: Mapped[str | None] = mapped_column(String(30), nullable=True)
    graduation_year: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)

    # Visibility / privacy.
    profile_visibility: Mapped[str] = mapped_column(
        String(20), nullable=False, default=vocab.VISIBILITY_VINUNI_ONLY
    )
    show_email: Mapped[str] = mapped_column(
        String(20), nullable=False, default=vocab.CONTACT_INVITED
    )
    show_phone: Mapped[str] = mapped_column(
        String(20), nullable=False, default=vocab.CONTACT_HIDDEN
    )

    # Open-to-work signal.
    is_open_to_work: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    open_to_work_types: Mapped[list] = mapped_column(JsonType, nullable=False, default=list)

    # Avatar storage key (internal; never returned to clients — expose via avatar_url only).
    avatar_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Completion cache (0-100), recomputed on every write.
    profile_completion: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0
    )


class StudentEducation(BaseEntity):
    __tablename__ = "student_education"

    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    institution: Mapped[str] = mapped_column(String(255), nullable=False)
    degree: Mapped[str | None] = mapped_column(String(100), nullable=True)
    field_of_study: Mapped[str | None] = mapped_column(String(200), nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    gpa: Mapped[float | None] = mapped_column(Numeric(3, 2), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)


class StudentExperience(BaseEntity):
    __tablename__ = "student_experience"

    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    employment_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    skills_used: Mapped[list] = mapped_column(JsonType, nullable=False, default=list)
    sort_order: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)


class StudentSkill(BaseEntity):
    __tablename__ = "student_skills"
    __table_args__ = (
        UniqueConstraint("student_id", "name", name="uq_student_skill_name"),
    )

    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    proficiency: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    sort_order: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)


class StudentLink(BaseEntity):
    __tablename__ = "student_links"

    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    sort_order: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)


__all__ = [
    "StudentProfile",
    "StudentEducation",
    "StudentExperience",
    "StudentSkill",
    "StudentLink",
]
