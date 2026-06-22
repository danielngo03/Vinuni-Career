from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.ai_operations.application.legacy_ai_service import (
    log_ai_usage,
    match_cv_to_job,
)
from app.modules.opportunities.infrastructure.models import Job
from app.modules.recruitment.infrastructure.models import CV, ApplicationTrackingLog, JobApplication
from app.modules.recruitment.schemas import JobApplicationCreate
from app.modules.reporting.application.audit_service import write_audit
from app.platform.database.models.base import now_utc
from app.shared.enum import ApplicationStatus, JobStatus
from app.shared.errors import AppError, ErrorCode


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def apply_to_job(
    db: Session,
    job_id: str,
    payload: JobApplicationCreate,
    *,
    actor_id: str | None = None,
) -> JobApplication:
    job = db.get(Job, job_id)
    if not job or job.deleted_at is not None:
        raise AppError(code=ErrorCode.NOT_FOUND, message="Job not found", status_code=404)
    if job.status != JobStatus.APPROVED:
        raise AppError(code=ErrorCode.CONFLICT, message="Job is not open", status_code=409)
    if not job.is_active:
        raise AppError(code=ErrorCode.CONFLICT, message="Job is inactive", status_code=409)
    if job.application_deadline and _as_utc(job.application_deadline) < now_utc():
        raise AppError(
            code=ErrorCode.BAD_REQUEST,
            message="Job application deadline has passed",
            status_code=400,
        )

    cv = db.get(CV, payload.cv_id)
    if not cv or cv.student_id != payload.student_id:
        raise AppError(code=ErrorCode.NOT_FOUND, message="CV not found", status_code=404)
    if not cv.is_primary:
        raise AppError(
            code=ErrorCode.BAD_REQUEST,
            message="You must use your Primary CV to apply",
            status_code=400,
        )

    existing = db.scalar(
        select(JobApplication).where(
            JobApplication.job_id == job_id,
            JobApplication.student_id == payload.student_id,
        )
    )
    if existing:
        raise AppError(code=ErrorCode.CONFLICT, message="Already applied", status_code=409)

    match = match_cv_to_job(str(cv.masked_data), job.description)
    application = JobApplication(
        job_id=job_id,
        student_id=payload.student_id,
        cv_id=payload.cv_id,
        cover_letter=payload.cover_letter,
        status=ApplicationStatus.APPLIED,
        ai_match_score=match.score,
        ai_reasoning=match.model_dump(),
        consent_to_unmask=payload.consent_to_unmask,
    )
    db.add(application)
    db.flush()
    db.add(
        ApplicationTrackingLog(
            application_id=application.id,
            changed_by=actor_id,
            old_status=None,
            new_status=ApplicationStatus.APPLIED,
            note="Application submitted.",
        )
    )
    log_ai_usage(
        db,
        org_id=job.org_id,
        user_id=actor_id,
        feature_name="cv_job_match",
        input_text=f"{cv.masked_data}\n{job.description}",
        output_text=str(match.model_dump()),
        provider=match.reasoning.get("provider"),
        model=match.reasoning.get("model"),
    )
    write_audit(
        db,
        actor_id=actor_id,
        action="job.apply",
        target_resource="job_applications",
        target_id=application.id,
        new_data={"job_id": job_id, "student_id": payload.student_id},
    )
    db.commit()
    db.refresh(application)
    return application


def update_application_status(
    db: Session,
    application_id: str,
    new_status: ApplicationStatus,
    *,
    actor_id: str | None = None,
    note: str | None = None,
) -> JobApplication:
    application = db.get(JobApplication, application_id)
    if not application:
        raise AppError(code=ErrorCode.NOT_FOUND, message="Application not found", status_code=404)

    job = db.get(Job, application.job_id)
    if not job:
        raise AppError(code=ErrorCode.NOT_FOUND, message="Job not found", status_code=404)

    old_status = application.status
    if old_status == new_status:
        return application

    valid_transitions = {
        ApplicationStatus.APPLIED: [ApplicationStatus.SHORTLISTED, ApplicationStatus.REJECTED],
        ApplicationStatus.SHORTLISTED: [ApplicationStatus.HR_INTERVIEW, ApplicationStatus.REJECTED],
        ApplicationStatus.HR_INTERVIEW: [
            ApplicationStatus.TECH_INTERVIEW,
            ApplicationStatus.FINAL_INTERVIEW,
            ApplicationStatus.OFFERED,
            ApplicationStatus.REJECTED,
        ],
        ApplicationStatus.TECH_INTERVIEW: [
            ApplicationStatus.FINAL_INTERVIEW,
            ApplicationStatus.OFFERED,
            ApplicationStatus.REJECTED,
        ],
        ApplicationStatus.FINAL_INTERVIEW: [ApplicationStatus.OFFERED, ApplicationStatus.REJECTED],
        ApplicationStatus.OFFERED: [
            ApplicationStatus.HIRED,
            ApplicationStatus.REJECTED,
            ApplicationStatus.DECLINED,
        ],
        ApplicationStatus.HIRED: [],
        ApplicationStatus.REJECTED: [],
        ApplicationStatus.DECLINED: [],
    }

    if new_status not in valid_transitions.get(old_status, []):
        raise AppError(
            code=ErrorCode.BAD_REQUEST,
            message=f"Invalid transition from {old_status.value} to {new_status.value}",
            status_code=400,
        )

    application.status = new_status
    db.add(
        ApplicationTrackingLog(
            application_id=application.id,
            changed_by=actor_id,
            old_status=old_status,
            new_status=new_status,
            note=note,
        )
    )

    if new_status == ApplicationStatus.HIRED and job.max_openings:
        from sqlalchemy import func
        hired_count = (
            db.scalar(
                select(func.count()).where(
                    JobApplication.job_id == job.id,
                    JobApplication.status == ApplicationStatus.HIRED,
                    JobApplication.id != application.id,
                )
            )
            or 0
        )

        if hired_count + 1 >= job.max_openings:
            job.status = JobStatus.CLOSED
            pending_apps = db.scalars(
                select(JobApplication).where(
                    JobApplication.job_id == job.id,
                    JobApplication.status.in_(
                        [
                            ApplicationStatus.APPLIED,
                            ApplicationStatus.SHORTLISTED,
                            ApplicationStatus.HR_INTERVIEW,
                            ApplicationStatus.TECH_INTERVIEW,
                            ApplicationStatus.FINAL_INTERVIEW,
                        ]
                    ),
                    JobApplication.id != application.id,
                )
            ).all()
            for pending_app in pending_apps:
                pending_app.status = ApplicationStatus.REJECTED
                db.add(
                    ApplicationTrackingLog(
                        application_id=pending_app.id,
                        changed_by=None,
                        old_status=pending_app.status,
                        new_status=ApplicationStatus.REJECTED,
                        note="Auto-rejected because the job has reached its maximum openings.",
                    )
                )

    db.commit()
    db.refresh(application)
    return application
