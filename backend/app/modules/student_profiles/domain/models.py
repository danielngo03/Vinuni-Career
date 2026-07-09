"""Student-profile ORM model (identity-only aggregate).

Owner decision (2026-07-06): the student profile is **identity-only**. All career
content — education, experience, skills, headline/summary, major/degree — now lives
exclusively in the student's CVs (``documents`` module, max 5 per student).
Recruiters view CVs, never a separate career profile. The ONLY career signal the
profile keeps is the ``is_open_to_work`` boolean, so recruiters know whether a
student is job-seeking.

Kept columns:

- ``user_id`` — the owning user (one profile per user).
- ``phone`` / ``location_city`` / ``location_country`` — basic identity/contact.
- ``profile_visibility`` / ``show_email`` / ``show_phone`` — privacy gates.
- ``is_open_to_work`` — the sole career/job-seeking signal.
- ``avatar_path`` — internal storage key (exposed only via ``avatar_url``).

Removed in this slice (migration ``0069``): ``headline``, ``summary``, ``major``,
``degree_level``, ``graduation_year``, ``open_to_work_types``, ``profile_completion``,
and the four child tables (``student_education`` / ``student_experience`` /
``student_skills`` / ``student_links``).

``phone`` is stored plaintext in this slice and gated by ``show_phone``; Fernet
field-level encryption (``docs/SECURITY_PRIVACY.md``) remains a documented
follow-up — exposure is already privacy-gated, encryption-at-rest is additive.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.modules.student_profiles.domain import vocab
from app.shared.models import BaseEntity


class StudentProfile(BaseEntity):
    """The identity-only student profile aggregate root (one per user)."""

    __tablename__ = "student_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    location_city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    location_country: Mapped[str] = mapped_column(
        String(100), nullable=False, default="Vietnam"
    )

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

    # The sole career signal the identity-only profile keeps.
    is_open_to_work: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Institutional affiliation — the authoritative, surfaced VinUni-vs-external
    # fact (``vinuni_student`` | ``alumni`` | ``external`` | ``general``). Written
    # only via the affiliation facade; ``general`` until the student verifies or a
    # provisional label is derived. ``student_verified_at`` is the verified-student
    # badge source (set on successful student verification).
    affiliation: Mapped[str] = mapped_column(
        String(30), nullable=False, default="general", server_default="general"
    )
    student_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Avatar storage key (internal; never returned to clients — expose via avatar_url only).
    avatar_path: Mapped[str | None] = mapped_column(String(500), nullable=True)


__all__ = ["StudentProfile"]
