from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.engagement.infrastructure.models import CompanyReview
from app.modules.engagement.schemas import CompanyReviewCreate
from app.platform.database.models.identity import Organization
from app.platform.database.models.student import StudentProfile
from app.shared.errors import AppError, ErrorCode


def create_review(db: Session, payload: CompanyReviewCreate, *, student_id: str) -> CompanyReview:
    student = db.get(StudentProfile, student_id)
    if not student:
        raise AppError(code=ErrorCode.FORBIDDEN, message="Only students can review", status_code=403)

    org = db.get(Organization, payload.org_id)
    if not org:
        raise AppError(code=ErrorCode.NOT_FOUND, message="Organization not found", status_code=404)

    existing = db.scalar(select(CompanyReview).where(
        CompanyReview.student_id == student.id,
        CompanyReview.org_id == org.id
    ))
    if existing:
        raise AppError(code=ErrorCode.CONFLICT, message="Already reviewed this company", status_code=409)

    review = CompanyReview(
        student_id=student.id,
        org_id=org.id,
        title=payload.title,
        overall_rating=payload.overall_rating,
        culture_rating=payload.culture_rating,
        interview_experience_rating=payload.interview_experience_rating,
        review_content=payload.review_content,
        is_anonymous=payload.is_anonymous,
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    return review

def get_org_reviews(db: Session, org_id: str, limit: int = 20, offset: int = 0) -> list[CompanyReview]:
    stmt = (
        select(CompanyReview)
        .where(CompanyReview.org_id == org_id)
        .order_by(CompanyReview.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(db.scalars(stmt))
