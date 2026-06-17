from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai_engines.jd_parser import parse_jd_form as ai_parse_jd_form
from app.ai_engines.jd_parser import parse_jd_raw_text as ai_parse_jd_raw_text
from app.domain.enum import ApplicationStatus, ApprovalSource, JobStatus
from app.infra.database.models import CV, ApplicationTrackingLog, Job, JobApplication
from app.infra.database.models.base import now_utc
from app.schemas.jobs import (
    JobApplicationCreate,
    JobCreate,
    JobFormParseRequest,
    JobDeleteResponse,
    JobManagementCreate,
    JobManagementView,
    JobModerationRequest,
    JobParseResponse,
    JobStatusUpdateRequest,
)
from app.services.ai_service import (
    embed_text,
    evaluate_job_policy,
    index_document,
    log_ai_usage,
    match_cv_to_job,
    parse_job_requirements,
)
from app.services.audit_service import write_audit


def parse_jd_raw_text(
    raw_text: str,
    *,
    job_id: str | None = None,
    company_id: str | None = None,
    source: str = "raw_text",
) -> JobParseResponse:
    return ai_parse_jd_raw_text(
        raw_text,
        job_id=job_id,
        company_id=company_id,
        source=source,
    )


def parse_jd_form(payload: JobFormParseRequest) -> JobParseResponse:
    return ai_parse_jd_form(payload)


def create_managed_job(
    db: Session,
    payload: JobManagementCreate,
    *,
    actor_id: str | None = None,
) -> JobManagementView:
    job_status = _management_status_to_domain(payload.status)
    parsed_requirements = payload.parsed_requirements or parse_job_requirements(payload.description)
    job = Job(
        org_id=payload.org_id,
        dept_id=payload.dept_id,
        title=payload.title.strip(),
        description=payload.description.strip(),
        parsed_requirements=parsed_requirements,
        embedding=embed_text(payload.description),
        status=job_status,
        approval_source=ApprovalSource.MANUAL_HR,
        approved_by=actor_id if job_status == JobStatus.APPROVED else None,
        approved_at=now_utc() if job_status == JobStatus.APPROVED else None,
    )
    db.add(job)
    db.flush()
    index_document(
        document_id=job.id,
        entity_type="job",
        title=job.title,
        body=job.description,
        metadata={"org_id": job.org_id, "status": job.status.value},
    )
    write_audit(
        db,
        actor_id=actor_id,
        action="job.manage.create",
        target_resource="jobs",
        target_id=job.id,
        new_data={"status": _domain_status_to_management(job.status), "title": job.title},
    )
    db.commit()
    db.refresh(job)
    return _job_management_view(job)


def list_managed_jobs(
    db: Session,
    *,
    org_id: str | None = None,
    status_filter: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[JobManagementView]:
    stmt = (
        select(Job)
        .where(Job.deleted_at.is_(None), Job.status.in_([JobStatus.APPROVED, JobStatus.CLOSED]))
        .order_by(Job.created_at.desc())
    )
    if org_id:
        stmt = stmt.where(Job.org_id == org_id)
    if status_filter:
        stmt = stmt.where(Job.status == _management_status_to_domain(status_filter))
    return [_job_management_view(job) for job in db.scalars(stmt.limit(limit).offset(offset))]


def update_managed_job_status(
    db: Session,
    job_id: str,
    payload: JobStatusUpdateRequest,
    *,
    actor_id: str | None = None,
) -> JobManagementView:
    job = _get_active_job(db, job_id)
    old_status = job.status
    job.status = _management_status_to_domain(payload.status)
    job.approval_source = ApprovalSource.MANUAL_HR
    job.approved_by = actor_id if job.status == JobStatus.APPROVED else None
    job.approved_at = now_utc() if job.status == JobStatus.APPROVED else None
    write_audit(
        db,
        actor_id=actor_id,
        action="job.manage.status",
        target_resource="jobs",
        target_id=job.id,
        old_data={"status": _domain_status_to_management(old_status)},
        new_data={"status": payload.status},
    )
    db.commit()
    db.refresh(job)
    return _job_management_view(job)


def delete_managed_job(
    db: Session,
    job_id: str,
    *,
    actor_id: str | None = None,
) -> JobDeleteResponse:
    job = _get_active_job(db, job_id)
    job.deleted_at = now_utc()
    write_audit(
        db,
        actor_id=actor_id,
        action="job.manage.delete",
        target_resource="jobs",
        target_id=job.id,
        old_data={"status": _domain_status_to_management(job.status), "title": job.title},
        new_data={"deleted": True},
    )
    db.commit()
    return JobDeleteResponse(status="deleted", job_id=job_id)


def create_job(db: Session, payload: JobCreate, *, actor_id: str | None = None) -> Job:
    approved, reasons, trace = evaluate_job_policy(payload.description)
    job = Job(
        org_id=payload.org_id,
        dept_id=payload.dept_id,
        title=payload.title.strip(),
        description=payload.description.strip(),
        parsed_requirements={
            **parse_job_requirements(payload.description),
            "moderation": {"approved": approved, "reasons": reasons, "trace": trace},
        },
        embedding=embed_text(payload.description),
        status=JobStatus.APPROVED if approved else JobStatus.PENDING_APPROVAL,
        approval_source=ApprovalSource.AI_AUTOMATION if approved else None,
        approved_by=actor_id if approved else None,
        approved_at=now_utc() if approved else None,
    )
    db.add(job)
    log_ai_usage(
        db,
        org_id=payload.org_id,
        user_id=actor_id,
        feature_name="job_policy_and_parse",
        input_text=payload.description,
        output_text=str(job.parsed_requirements),
    )
    db.flush()
    index_document(
        document_id=job.id,
        entity_type="job",
        title=job.title,
        body=job.description,
        metadata={"org_id": job.org_id, "status": job.status.value},
    )
    write_audit(
        db,
        actor_id=actor_id,
        action="job.create",
        target_resource="jobs",
        target_id=job.id,
        new_data={"status": job.status.value, "title": job.title},
    )
    db.commit()
    db.refresh(job)
    return job


def list_jobs(
    db: Session,
    *,
    org_id: str | None = None,
    status_filter: JobStatus | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[Job]:
    stmt = select(Job).where(Job.deleted_at.is_(None)).order_by(Job.created_at.desc())
    if org_id:
        stmt = stmt.where(Job.org_id == org_id)
    if status_filter:
        stmt = stmt.where(Job.status == status_filter)
    return list(db.scalars(stmt.limit(limit).offset(offset)))


def moderate_job(
    db: Session,
    job_id: str,
    payload: JobModerationRequest,
    *,
    actor_id: str | None = None,
) -> Job:
    job = db.get(Job, job_id)
    if not job or job.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    old_status = job.status
    job.status = JobStatus.APPROVED if payload.approve else JobStatus.REJECTED
    job.approval_source = ApprovalSource.MANUAL_HR
    job.approved_by = actor_id
    job.approved_at = now_utc() if payload.approve else None
    write_audit(
        db,
        actor_id=actor_id,
        action="job.moderate",
        target_resource="jobs",
        target_id=job.id,
        old_data={"status": old_status.value},
        new_data={"status": job.status.value, "reason": payload.reason},
    )
    db.commit()
    db.refresh(job)
    return job


def apply_to_job(
    db: Session,
    job_id: str,
    payload: JobApplicationCreate,
    *,
    actor_id: str | None = None,
) -> JobApplication:
    job = db.get(Job, job_id)
    if not job or job.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    if job.status != JobStatus.APPROVED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Job is not open")

    cv = db.get(CV, payload.cv_id)
    if not cv or cv.student_id != payload.student_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CV not found")

    existing = db.scalar(
        select(JobApplication).where(
            JobApplication.job_id == job_id,
            JobApplication.student_id == payload.student_id,
        )
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already applied")

    match = match_cv_to_job(str(cv.masked_data), job.description)
    application = JobApplication(
        job_id=job_id,
        student_id=payload.student_id,
        cv_id=payload.cv_id,
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


def _get_active_job(db: Session, job_id: str) -> Job:
    job = db.get(Job, job_id)
    if not job or job.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


def _management_status_to_domain(value: str) -> JobStatus:
    if value == "open":
        return JobStatus.APPROVED
    if value == "closed":
        return JobStatus.CLOSED
    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid job status")


def _domain_status_to_management(value: JobStatus) -> str:
    if value == JobStatus.CLOSED:
        return "closed"
    return "open"


def _job_management_view(job: Job) -> JobManagementView:
    return JobManagementView(
        id=job.id,
        org_id=job.org_id,
        dept_id=job.dept_id,
        title=job.title,
        description=job.description,
        parsed_requirements=job.parsed_requirements,
        status=_domain_status_to_management(job.status),
    )
