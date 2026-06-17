from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.ai_engines.cv_parser import parse_cv_form as ai_parse_cv_form
from app.ai_engines.cv_parser import parse_cv_raw_text as ai_parse_cv_raw_text
from app.infra.database.models import CV, StudentProfile
from app.schemas.cvs import CVCreate, CVFormParseRequest, CVParseResponse
from app.services.ai_service import embed_text, index_document, mask_pii


def parse_cv_raw_text(
    raw_text: str,
    *,
    student_id: str | None = None,
    source: str = "raw_text",
) -> CVParseResponse:
    return ai_parse_cv_raw_text(raw_text, student_id=student_id, source=source)


def parse_cv_form(payload: CVFormParseRequest) -> CVParseResponse:
    return ai_parse_cv_form(payload)


def create_cv(db: Session, payload: CVCreate) -> CV:
    if not db.get(StudentProfile, payload.student_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student profile not found",
        )

    raw_text = payload.raw_text or "\n".join(str(value) for value in payload.parsed_data.values())
    masked_text, entities = mask_pii(raw_text)
    cv = CV(
        student_id=payload.student_id,
        parsed_data={**payload.parsed_data, "raw_text": raw_text},
        masked_data={"text": masked_text, "entities": entities},
        embedding=embed_text(masked_text),
        is_primary=payload.is_primary,
    )
    db.add(cv)
    db.flush()
    index_document(
        document_id=cv.id,
        entity_type="cv",
        title=f"CV {cv.student_id}",
        body=masked_text,
        metadata={"student_id": cv.student_id, "is_primary": cv.is_primary},
    )
    db.commit()
    db.refresh(cv)
    return cv
