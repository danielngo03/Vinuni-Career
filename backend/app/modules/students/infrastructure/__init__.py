"""Students — infrastructure (SQLAlchemy repository)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.modules.students.domain import AcademicProfile, PrivacySettings
from app.platform.database.models import StudentProfile
from app.shared.errors import AppError, ErrorCode


class StudentRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_profile(self, student_id: str) -> AcademicProfile:
        row = self._db.get(StudentProfile, student_id)
        if not row:
            raise AppError(
                code=ErrorCode.NOT_FOUND,
                message="Student profile not found",
                status_code=404,
            )
        raw_privacy = row.privacy_settings or {}
        return AcademicProfile(
            student_id=row.id,
            student_code=row.student_code,
            major_id=row.major_id,
            degree_level=row.degree_level.value if row.degree_level else None,
            enrollment_year=row.enrollment_year,
            graduation_year=row.graduation_year,
            gpa=None,  # GPA stored in AcademicRecord — loaded separately
            privacy=PrivacySettings(
                blind_hiring=raw_privacy.get("blind_hiring", True),
                pii_unmask_requires_consent=raw_privacy.get(
                    "pii_unmask_requires_consent", True
                ),
            ),
        )

    def update_privacy(self, student_id: str, privacy: PrivacySettings) -> None:
        row = self._db.get(StudentProfile, student_id)
        if not row:
            raise AppError(
                code=ErrorCode.NOT_FOUND,
                message="Student profile not found",
                status_code=404,
            )
        row.privacy_settings = {
            "blind_hiring": privacy.blind_hiring,
            "pii_unmask_requires_consent": privacy.pii_unmask_requires_consent,
            "share_gpa": privacy.share_gpa,
            "share_contact": privacy.share_contact,
        }
        self._db.flush()
