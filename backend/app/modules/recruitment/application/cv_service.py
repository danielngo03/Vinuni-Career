from __future__ import annotations

from sqlalchemy.orm import Session

from app.ai.agents import run_cv_pipeline
from app.modules.ai_operations.application.legacy_ai_service import embed_text, index_document
from app.modules.recruitment.infrastructure.models import CV
from app.modules.recruitment.schemas import CVCreate
from app.platform.database.models.student import StudentProfile
from app.shared.errors import AppError, ErrorCode


def create_cv(db: Session, payload: CVCreate) -> CV:
    if not db.get(StudentProfile, payload.student_id):
        raise AppError(
            code=ErrorCode.NOT_FOUND,
            message="No Student Profile found for this user",
            status_code=404,
        )

    from sqlalchemy import func, select
    current_cv_count = db.scalar(
        select(func.count(CV.id))
        .where(CV.student_id == payload.student_id, CV.deleted_at.is_(None))
    )
    if (current_cv_count or 0) >= 5:
        raise AppError(
            code=ErrorCode.BAD_REQUEST,
            message="Maximum limit of 5 CVs reached.",
            status_code=400,
        )

    raw_text = payload.raw_text or "\n".join(str(value) for value in payload.parsed_data.values())
    pipeline = run_cv_pipeline(raw_text)
    masked_text = pipeline.masked_data.get("text", raw_text)
    if payload.is_primary:
        from sqlalchemy import update
        db.execute(
            update(CV)
            .where(CV.student_id == payload.student_id)
            .values(is_primary=False)
        )

    cv = CV(
        student_id=payload.student_id,
        title=payload.title,
        summary=payload.summary,
        experience_years=payload.experience_years,
        skills=payload.skills or pipeline.normalized_skills,
        education_history=payload.education_history,
        work_experience=payload.work_experience,
        certificates=payload.certificates,
        projects=payload.projects,
        awards=payload.awards,
        parsed_data={**payload.parsed_data, **pipeline.parsed_data},
        masked_data=pipeline.masked_data,
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
