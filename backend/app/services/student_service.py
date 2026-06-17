from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infra.database.models import Organization, StudentProfile, User
from app.schemas.students import StudentProfileCreate


def create_student_profile(db: Session, payload: StudentProfileCreate) -> StudentProfile:
    if not db.get(User, payload.user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if not db.get(Organization, payload.org_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    if db.get(StudentProfile, payload.user_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Student profile already exists",
        )

    profile = StudentProfile(
        id=payload.user_id,
        org_id=payload.org_id,
        student_code=payload.student_code,
        gpa_overall=payload.gpa_overall,
        attendance_overall=payload.attendance_overall,
        privacy_settings=payload.privacy_settings,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


def list_student_profiles(
    db: Session,
    org_id: str | None,
    *,
    limit: int,
    offset: int,
) -> list[StudentProfile]:
    stmt = select(StudentProfile).order_by(StudentProfile.student_code).limit(limit).offset(offset)
    if org_id:
        stmt = stmt.where(StudentProfile.org_id == org_id)
    return list(db.scalars(stmt))
