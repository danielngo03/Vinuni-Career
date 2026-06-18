from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.recruitment.infrastructure.models import Interview, JobApplication
from app.modules.recruitment.schemas import InterviewCreate, InterviewUpdate
from app.shared.errors import AppError, ErrorCode


def list_interviews(db: Session, student_id: str) -> list[Interview]:
    stmt = (
        select(Interview)
        .join(JobApplication, JobApplication.id == Interview.application_id)
        .where(JobApplication.student_id == student_id, Interview.deleted_at.is_(None))
        .order_by(Interview.start_time.asc())
    )
    return list(db.scalars(stmt))

def schedule_interview(db: Session, payload: InterviewCreate) -> Interview:
    app = db.get(JobApplication, payload.application_id)
    if not app:
        raise AppError(code=ErrorCode.NOT_FOUND, message="Application not found", status_code=404)

    interview = Interview(
        application_id=payload.application_id,
        interview_type=payload.interview_type,
        start_time=payload.start_time,
        end_time=payload.end_time,
        meeting_url=payload.meeting_url,
        location=payload.location,
        notes=payload.notes,
    )
    db.add(interview)
    db.commit()
    db.refresh(interview)
    return interview

def update_interview(db: Session, interview_id: str, payload: InterviewUpdate) -> Interview:
    interview = db.get(Interview, interview_id)
    if not interview or interview.deleted_at is not None:
        raise AppError(code=ErrorCode.NOT_FOUND, message="Interview not found", status_code=404)

    if payload.status:
        interview.status = payload.status
    if payload.start_time:
        interview.start_time = payload.start_time
    if payload.end_time:
        interview.end_time = payload.end_time
    if payload.meeting_url is not None:
        interview.meeting_url = payload.meeting_url
    if payload.location is not None:
        interview.location = payload.location
    if payload.notes is not None:
        interview.notes = payload.notes

    db.commit()
    db.refresh(interview)
    return interview
