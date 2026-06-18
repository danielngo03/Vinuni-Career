from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.ai_operations.application.legacy_ai_service import (
    embed_text,
    evaluate_job_policy,
    index_document,
    log_ai_usage,
    parse_job_requirements,
)
from app.modules.opportunities.infrastructure.models import Job
from app.modules.opportunities.schemas import JobCreate, JobModerationRequest
from app.modules.reporting.application.audit_service import write_audit
from app.platform.database.models.base import now_utc
from app.shared.enum import ApprovalSource, JobStatus
from app.shared.errors import AppError, ErrorCode


def create_job(db: Session, payload: JobCreate, *, actor_id: str | None = None) -> Job:
    if not payload.org_id:
        raise AppError(
            code=ErrorCode.BAD_REQUEST,
            message="Organization is required to create a job",
            status_code=400,
        )
    org_id = payload.org_id
    approved, reasons, trace = evaluate_job_policy(payload.description)
    job = Job(
        org_id=org_id,
        dept_id=payload.dept_id,
        title=payload.title.strip(),
        description=payload.description.strip(),
        job_type=payload.job_type,
        experience_level=payload.experience_level,
        location_type=payload.location_type,
        location_address=payload.location_address,
        salary_min=payload.salary_min,
        salary_max=payload.salary_max,
        currency=payload.currency,
        skills=payload.skills,
        benefits=payload.benefits,
        application_deadline=payload.application_deadline,
        is_active=payload.is_active,
        max_openings=payload.max_openings,
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
        org_id=org_id,
        user_id=actor_id,
        feature_name="job_policy_and_parse",
        input_text=payload.description,
        output_text=str(job.parsed_requirements),
        provider=trace.get("provider"),
        model=trace.get("model"),
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


def count_jobs(
    db: Session,
    *,
    org_id: str | None = None,
    status_filter: JobStatus | None = None,
) -> int:
    from sqlalchemy import func

    stmt = select(func.count()).select_from(Job).where(Job.deleted_at.is_(None))
    if org_id:
        stmt = stmt.where(Job.org_id == org_id)
    if status_filter:
        stmt = stmt.where(Job.status == status_filter)
    return int(db.scalar(stmt) or 0)


def moderate_job(
    db: Session,
    job_id: str,
    payload: JobModerationRequest,
    *,
    actor_id: str | None = None,
) -> Job:
    job = db.get(Job, job_id)
    if not job or job.deleted_at is not None:
        raise AppError(code=ErrorCode.NOT_FOUND, message="Job not found", status_code=404)
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
