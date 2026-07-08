"""Onboarding ORM models.

``OnboardingState`` tracks which wizard step a user is on and resumes correctly
on re-login. ``StudentVerification`` records student-specific verification data
(student email OTP + AI check of student ID card).

These tables are created in migration 0054.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import Base, JsonType


class OnboardingState(Base):
    """One row per user; tracks current wizard step and completion.

    ``current_step`` values:
      role_select → seeker_type → seeker_profile → student_verify → complete
      role_select → employer_info → employer_docs → pending → complete

    ``role``: 'job_seeker' | 'employer'
    ``seeker_type``: 'student' | 'professional' | 'fresh_graduate'
    """

    __tablename__ = "onboarding_states"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str | None] = mapped_column(String(20), nullable=True)
    seeker_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    current_step: Mapped[str] = mapped_column(
        String(50), nullable=False, default="role_select"
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
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

    @property
    def is_complete(self) -> bool:
        return self.completed_at is not None or self.current_step == "complete"


class StudentVerification(Base):
    """Student identity verification record.

    ``ai_check_status``: pending | passed | failed | manual_review
    ``status``: unverified | verified | rejected
    """

    __tablename__ = "student_verifications"

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    university_name: Mapped[str] = mapped_column(String(255), nullable=False)
    student_id_number: Mapped[str] = mapped_column(String(50), nullable=False)
    student_email: Mapped[str] = mapped_column(String(320), nullable=False)
    student_email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    id_card_file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ai_check_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="pending"
    )
    ai_check_result: Mapped[dict | None] = mapped_column(JsonType, nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="unverified")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
