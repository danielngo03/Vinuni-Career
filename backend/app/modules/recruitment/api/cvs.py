from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.ai.ingestion import inspect_upload
from app.modules.access.api.auth import get_current_user
from app.modules.access.api.rbac import require_permission
from app.modules.ai_operations.application.legacy_ai_service import mask_pii
from app.modules.recruitment.application.cv_service import create_cv
from app.modules.recruitment.infrastructure.models import CV
from app.modules.recruitment.schemas import (
    CVCreate,
    CVInspectResponse,
    CVMaskRequest,
    CVMaskResponse,
    CVUpdate,
    CVView,
)
from app.platform.database.models import User
from app.platform.database.models.base import now_utc
from app.platform.database.models.student import StudentProfile
from app.platform.database.session import get_db
from app.shared.errors import AppError, ErrorCode

router = APIRouter()

@router.post("/mask", response_model=CVMaskResponse)
def mask_cv(
    payload: CVMaskRequest,
    _: User = Depends(require_permission("cv", "mask")),
) -> CVMaskResponse:
    masked_text, entities = mask_pii(payload.text)
    return CVMaskResponse(masked_text=masked_text, entities=entities)

@router.post("/inspect", response_model=CVInspectResponse)
async def inspect_cv_upload(
    upload: UploadFile = File(...),
    _: User = Depends(require_permission("cv", "inspect")),
) -> CVInspectResponse:
    content = await upload.read()
    decision = inspect_upload(
        content,
        declared_content_type=upload.content_type,
        filename=upload.filename,
    )
    return CVInspectResponse(
        route=decision.route,
        detected_kind=decision.detected_kind,
        declared_content_type=decision.declared_content_type,
        byte_size=decision.byte_size,
        reasons=decision.reasons,
        needs_vision=decision.needs_vision,
        extracted_text_preview=decision.extracted_text_preview,
        metadata=decision.metadata,
    )

@router.post("", response_model=CVView, status_code=201)
def create_student_cv(
    payload: CVCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> CV:
    return create_cv(db, payload)

@router.post("/upload", response_model=CVView, status_code=201)
async def upload_student_cv(
    upload: UploadFile = File(..., alias="file"),
    title: str | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CV:
    if not db.get(StudentProfile, current_user.id):
        raise AppError(
            code=ErrorCode.FORBIDDEN,
            message="Only students with a profile can upload CVs",
            status_code=403,
        )
    content = await upload.read()
    decision = inspect_upload(
        content,
        declared_content_type=upload.content_type,
        filename=upload.filename,
    )
    if decision.route == "reject":
        raise AppError(
            code=ErrorCode.BAD_REQUEST,
            message="; ".join(decision.reasons),
            status_code=400,
        )
    raw_text = decision.extracted_text_preview or content.decode("utf-8", errors="ignore")
    if not raw_text.strip():
        raise AppError(
            code=ErrorCode.BAD_REQUEST,
            message="Unable to extract text from this CV. Please upload a text-based PDF or TXT file.",
            status_code=400,
        )
    return create_cv(
        db,
        CVCreate(
            student_id=current_user.id,
            title=title or upload.filename or "My Resume",
            raw_text=raw_text,
            is_primary=True,
        ),
    )

@router.get("/me", response_model=list[CVView])
def list_my_cvs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[CV]:
    return list(
        db.scalars(
            select(CV)
            .where(CV.student_id == current_user.id, CV.deleted_at.is_(None))
            .order_by(CV.created_at.desc())
        )
    )

@router.put("/{cv_id}/primary", response_model=CVView)
def set_primary_cv(
    cv_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CV:
    cv = db.get(CV, cv_id)
    if not cv or cv.deleted_at is not None or cv.student_id != current_user.id:
        raise AppError(code=ErrorCode.NOT_FOUND, message="CV not found", status_code=404)
    db.execute(update(CV).where(CV.student_id == current_user.id).values(is_primary=False))
    cv.is_primary = True
    db.commit()
    db.refresh(cv)
    return cv

@router.patch("/{cv_id}", response_model=CVView)
def update_cv(
    cv_id: str,
    payload: CVUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CV:
    cv = db.get(CV, cv_id)
    if not cv or cv.deleted_at is not None or cv.student_id != current_user.id:
        raise AppError(code=ErrorCode.NOT_FOUND, message="CV not found", status_code=404)

    cv.title = payload.title
    db.commit()
    db.refresh(cv)
    return cv

@router.delete("/{cv_id}", status_code=204)
def delete_cv(
    cv_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    cv = db.get(CV, cv_id)
    if not cv or cv.deleted_at is not None or cv.student_id != current_user.id:
        raise AppError(code=ErrorCode.NOT_FOUND, message="CV not found", status_code=404)

    cv.deleted_at = now_utc()
    db.commit()
