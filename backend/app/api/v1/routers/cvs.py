from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies.auth import get_current_user
from app.api.dependencies.rbac import require_permission
from app.infra.database.models import CV, User
from app.infra.database.session import get_db
from app.schemas.cvs import CVCreate, CVMaskRequest, CVMaskResponse, CVView
from app.services.ai_service import mask_pii
from app.services.cv_service import create_cv

router = APIRouter()


@router.post("/mask", response_model=CVMaskResponse)
def mask_cv(
    payload: CVMaskRequest,
    _: User = Depends(require_permission("cv", "mask")),
) -> CVMaskResponse:
    masked_text, entities = mask_pii(payload.text)
    return CVMaskResponse(masked_text=masked_text, entities=entities)


@router.post("", response_model=CVView, status_code=201)
def create_student_cv(
    payload: CVCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> CV:
    return create_cv(db, payload)
