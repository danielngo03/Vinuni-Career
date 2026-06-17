from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from app.api.dependencies.auth import get_current_user
from app.api.dependencies.rbac import require_permission
from app.infra.database.models import CV, User
from app.infra.database.session import get_db
from app.schemas.cvs import (
    CVCreate,
    CVFormParseRequest,
    CVMaskRequest,
    CVMaskResponse,
    CVParseResponse,
    CVRawParseRequest,
    CVView,
)
from app.services.ai_service import mask_pii
from app.services.cv_service import create_cv, parse_cv_form, parse_cv_raw_text

router = APIRouter()


@router.post("/mask", response_model=CVMaskResponse)
def mask_cv(
    payload: CVMaskRequest,
    _: User = Depends(require_permission("cv", "mask")),
) -> CVMaskResponse:
    masked_text, entities = mask_pii(payload.text)
    return CVMaskResponse(masked_text=masked_text, entities=entities)


@router.post("/parse/raw", response_model=CVParseResponse)
def parse_cv_from_raw_text(payload: CVRawParseRequest) -> CVParseResponse:
    return parse_cv_raw_text(payload.raw_text, student_id=payload.student_id)


@router.post("/parse/form", response_model=CVParseResponse)
def parse_cv_from_form(payload: CVFormParseRequest) -> CVParseResponse:
    return parse_cv_form(payload)


@router.post("/parse/upload", response_model=CVParseResponse)
async def parse_cv_from_upload(
    file: UploadFile = File(...),
    student_id: str | None = None,
) -> CVParseResponse:
    content = await file.read()
    text = content.decode("utf-8", errors="ignore")
    return parse_cv_raw_text(text, student_id=student_id, source="upload")


@router.post("", response_model=CVView, status_code=201)
def create_student_cv(
    payload: CVCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> CV:
    return create_cv(db, payload)
