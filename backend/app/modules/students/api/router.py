from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.modules.access.api.auth import get_current_user
from app.modules.students.application.service import create_student_profile, list_student_profiles
from app.modules.students.schemas import StudentProfileCreate, StudentProfileView
from app.platform.database.models import StudentProfile, User
from app.platform.database.session import get_db
from app.shared.schemas import PageParams

router = APIRouter()


@router.post("", response_model=StudentProfileView, status_code=201)
def create_profile(
    payload: StudentProfileCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> StudentProfile:
    return create_student_profile(db, payload)


@router.get("", response_model=list[StudentProfileView])
def list_profiles(
    page: PageParams = Depends(),
    org_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[StudentProfile]:
    return list_student_profiles(db, org_id, limit=page.limit, offset=page.offset)
