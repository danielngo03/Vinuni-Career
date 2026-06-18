from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.modules.access.api.auth import get_current_user
from app.modules.access.api.rbac import require_permission
from app.modules.recruitment.application.interview_service import (
    list_interviews,
    schedule_interview,
    update_interview,
)
from app.modules.recruitment.infrastructure.models import Interview
from app.modules.recruitment.schemas import InterviewCreate, InterviewUpdate, InterviewView
from app.platform.database.models import User
from app.platform.database.session import get_db

router = APIRouter()

@router.get("", response_model=list[InterviewView])
def get_interviews(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Interview]:
    return list_interviews(db, student_id=current_user.id)

@router.post("", response_model=InterviewView, status_code=201)
def create_interview(
    payload: InterviewCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("interview", "create")),
) -> Interview:
    return schedule_interview(db, payload)

@router.put("/{interview_id}", response_model=InterviewView)
def modify_interview(
    interview_id: str,
    payload: InterviewUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("interview", "update")),
) -> Interview:
    return update_interview(db, interview_id, payload)
