from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.students.schemas import StudentProfileCreate
from app.platform.database.models import Organization, StudentProfile, User
from app.shared.enum import OrgType
from app.shared.errors import AppError, ErrorCode


def calculate_profile_completeness(profile: StudentProfile, has_primary_cv: bool = False) -> int:
    score = 0
    if profile.phone_number:
        score += 10
    if profile.address:
        score += 10
    if profile.bio:
        score += 10
    if profile.skills and len(profile.skills) > 0:
        score += 20
    if profile.social_links:
        score += 10
    if has_primary_cv:
        score += 40
    return min(score, 100)


def create_student_profile(db: Session, payload: StudentProfileCreate) -> StudentProfile:
    if not db.get(User, payload.user_id):
        raise AppError(code=ErrorCode.NOT_FOUND, message="User not found", status_code=404)
    org = db.get(Organization, payload.org_id)
    if not org:
        raise AppError(code=ErrorCode.NOT_FOUND, message="Organization not found", status_code=404)
    if org.type != OrgType.UNIVERSITY:
        raise AppError(code=ErrorCode.BAD_REQUEST, message="Student must belong to a University organization", status_code=400)
    if db.get(StudentProfile, payload.user_id):
        raise AppError(
            code=ErrorCode.CONFLICT,
            message="Student profile already exists",
            status_code=409,
        )

    profile = StudentProfile(
        id=payload.user_id,
        org_id=payload.org_id,
        major_id=payload.major_id,
        student_code=payload.student_code,
        enrollment_year=payload.enrollment_year,
        graduation_year=payload.graduation_year,
        date_of_birth=payload.date_of_birth,
        phone_number=payload.phone_number,
        address=payload.address,
        bio=payload.bio,
        current_status=payload.current_status,
        degree_level=payload.degree_level,
        gpa_overall=payload.gpa_overall,
        attendance_overall=payload.attendance_overall,
        social_links=payload.social_links,
        skills=payload.skills,
        privacy_settings=payload.privacy_settings,
    )
    profile.profile_completeness = calculate_profile_completeness(profile)
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
