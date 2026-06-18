from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.modules.access.api.auth import get_current_user
from app.modules.engagement.application.review_service import create_review, get_org_reviews
from app.modules.engagement.infrastructure.models import CompanyReview
from app.modules.engagement.schemas import CompanyReviewCreate, CompanyReviewView
from app.platform.database.models.identity import User
from app.platform.database.session import get_db
from app.shared.schemas import PageParams

router = APIRouter()

@router.post("", response_model=CompanyReviewView, status_code=201)
def post_review(
    payload: CompanyReviewCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CompanyReview:
    return create_review(db, payload, student_id=current_user.id)

@router.get("/org/{org_id}", response_model=list[CompanyReviewView])
def get_reviews_for_org(
    org_id: str,
    page: PageParams = Depends(),
    db: Session = Depends(get_db),
) -> list[CompanyReview]:
    return get_org_reviews(db, org_id, limit=page.limit, offset=page.offset)
