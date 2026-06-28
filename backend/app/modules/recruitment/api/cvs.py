from __future__ import annotations

import hashlib
import logging
from io import BytesIO
from typing import cast

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.ai.extraction.gemini_document_cv import (
    GeminiCVExtractionError,
    cv_extraction_to_text,
    extract_cv_from_pdf,
)
from app.ai.ingestion import FileKind, inspect_upload
from app.ai.ingestion.gatekeeper import extract_text_for_gatekeeping
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
logger = logging.getLogger(__name__)


def _extract_full_cv_text(content: bytes, detected_kind: str) -> str:
    if detected_kind == "pdf":
        try:
            from pypdf import PdfReader
        except ImportError:
            return extract_text_for_gatekeeping(content, "pdf")

        try:
            reader = PdfReader(BytesIO(content))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception:  # noqa: BLE001
            text = ""
        return text or extract_text_for_gatekeeping(content, "pdf")

    if detected_kind in {"docx", "text"}:
        return extract_text_for_gatekeeping(content, cast(FileKind, detected_kind))

    return ""

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

@router.post("/blank", response_model=CVView, status_code=201)
def create_blank_cv(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CV:
    if not db.get(StudentProfile, current_user.id):
        raise AppError(
            code=ErrorCode.FORBIDDEN,
            message="Only students with a profile can create CVs",
            status_code=403,
        )
    raw_markdown = "# CV moi\n\n## Tom tat\n\n## Ky nang\n\n## Kinh nghiem\n\n## Hoc van\n"
    return create_cv(
        db,
        CVCreate(
            student_id=current_user.id,
            title="CV moi",
            raw_text=raw_markdown,
            parsed_data={"raw_markdown": raw_markdown, "source": "manual_blank"},
            is_primary=False,
        ),
    )

@router.post("", response_model=CVView, status_code=201)
def create_student_cv(
    payload: CVCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CV:
    return create_cv(db, payload.model_copy(update={"student_id": current_user.id}))

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

    if decision.detected_kind == "pdf":
        try:
            extraction = extract_cv_from_pdf(content)
            raw_text = cv_extraction_to_text(extraction)
            if raw_text.strip():
                return create_cv(
                    db,
                    CVCreate(
                        student_id=current_user.id,
                        title=title or upload.filename or "My Resume",
                        summary=extraction.summary or None,
                        skills=[skill.name for skill in extraction.skills],
                        education_history=[
                            item.model_dump(exclude_none=True) for item in extraction.education
                        ],
                        work_experience=[
                            item.model_dump(exclude_none=True) for item in extraction.experiences
                        ],
                        certificates=[
                            {"name": certificate} for certificate in extraction.certifications
                        ],
                        projects=[
                            item.model_dump(exclude_none=True) for item in extraction.projects
                        ],
                        parsed_data={
                            "gemini_extraction": extraction.model_dump(),
                            "extraction_provider": "gemini",
                        },
                        raw_text=raw_text,
                        is_primary=True,
                    ),
                )
        except GeminiCVExtractionError as exc:
            logger.info("Gemini PDF CV extraction failed: %s", exc)
            raise AppError(
                code=ErrorCode.UPSTREAM_UNAVAILABLE,
                message=(
                    "Unable to extract this PDF CV with Gemini right now. "
                    "Please try again later."
                ),
                status_code=502,
            ) from exc
        raise AppError(
            code=ErrorCode.BAD_REQUEST,
            message="Gemini did not return usable CV content for this PDF.",
            status_code=400,
        )

    raw_text = _extract_full_cv_text(content, decision.detected_kind)
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

    if payload.title is not None:
        cv.title = payload.title
    if payload.raw_text is not None:
        raw_text = payload.raw_text.strip()
        content_hash = _content_hash(raw_text)
        parsed_data = dict(cv.parsed_data or {})
        last_analyzed_hash = parsed_data.get("last_analyzed_content_hash")
        parsed_data.update(
            {
                "raw_markdown": raw_text,
                "raw_text": raw_text,
                "content_hash": content_hash,
                "manual_edited_at": now_utc().isoformat(),
                "analysis_stale": bool(last_analyzed_hash and last_analyzed_hash != content_hash),
            }
        )
        if not last_analyzed_hash:
            parsed_data["analysis_stale"] = True
        cv.parsed_data = parsed_data
    db.commit()
    db.refresh(cv)
    return cv


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()

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
