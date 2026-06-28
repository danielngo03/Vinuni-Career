from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.extraction.gemini_document_jd import GeminiJDExtractionError, extract_jd_from_text
from app.ai.matching import normalize_skills
from app.modules.ai_operations.application.legacy_ai_service import (
    embed_text,
    evaluate_job_policy,
    index_document,
    log_ai_usage,
    parse_job_requirements,
)
from app.modules.opportunities.infrastructure.models import Job, JobScheduledAction
from app.modules.opportunities.schemas import (
    JobActionRequest,
    JobCreate,
    JobModerationRequest,
    JobScheduleCreate,
    JobUpdate,
)
from app.modules.reporting.application.audit_service import write_audit
from app.platform.database.models.base import now_utc
from app.shared.config import settings
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
    analysis_text = _payload_analysis_text(
        payload.description,
        payload.requirements,
        payload.responsibilities,
        payload.benefits_text,
    )
    approved, reasons, trace = evaluate_job_policy(analysis_text)
    content_hash = _content_hash(analysis_text)
    parsed_requirements = _parsed_requirements_with_metadata(
        payload.parsed_requirements or parse_job_requirements(analysis_text),
        content_hash=content_hash,
        analysis_stale=False,
        approved=approved,
        reasons=reasons,
        trace=trace,
    )
    job = Job(
        org_id=org_id,
        dept_id=payload.dept_id,
        title=payload.title.strip(),
        description=payload.description.strip(),
        requirements=payload.requirements.strip() if payload.requirements else None,
        responsibilities=payload.responsibilities.strip() if payload.responsibilities else None,
        benefits_text=payload.benefits_text.strip() if payload.benefits_text else None,
        industry=payload.industry,
        job_function=payload.job_function,
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
        parsed_requirements=parsed_requirements,
        embedding=embed_text(analysis_text),
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
        input_text=analysis_text,
        output_text=str(job.parsed_requirements),
        provider=trace.get("provider"),
        model=trace.get("model"),
    )
    db.flush()
    index_document(
        document_id=job.id,
        entity_type="job",
        title=job.title,
        body=analysis_text,
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


def create_blank_job(
    db: Session,
    *,
    org_id: str,
    dept_id: str | None = None,
    actor_id: str | None = None,
) -> Job:
    description = "# New job description\n\n## Overview\n\n## Responsibilities\n\n## Requirements\n\n## Benefits\n"
    job = Job(
        org_id=org_id,
        dept_id=dept_id,
        title="New job description",
        description=description,
        skills=[],
        benefits=[],
        parsed_requirements={
            "source": "manual_blank",
            "content_hash": _content_hash(description),
            "analysis_stale": True,
        },
        embedding=embed_text(description),
        status=JobStatus.DRAFT,
    )
    db.add(job)
    db.flush()
    write_audit(
        db,
        actor_id=actor_id,
        action="job.create_blank",
        target_resource="jobs",
        target_id=job.id,
        new_data={"status": job.status.value, "title": job.title},
    )
    db.commit()
    db.refresh(job)
    return job


def update_job(db: Session, job_id: str, payload: JobUpdate, *, actor_id: str | None = None) -> Job:
    job = db.get(Job, job_id)
    if not job or job.deleted_at is not None:
        raise AppError(code=ErrorCode.NOT_FOUND, message="Job not found", status_code=404)
    old_data = {
        "title": job.title,
        "description": job.description,
        "skills": job.skills,
        "status": job.status.value,
    }
    updates = payload.model_dump(exclude_unset=True)
    parsed_update = updates.pop("parsed_requirements", None)
    for field, value in updates.items():
        if isinstance(value, str):
            value = value.strip()
        setattr(job, field, value)
    if {"description", "requirements", "responsibilities", "benefits_text"} & set(updates):
        job.embedding = embed_text(_job_analysis_text(job))
    if parsed_update is not None:
        parsed_requirements = dict(parsed_update)
        content_hash = _content_hash(_job_analysis_text(job))
        parsed_requirements.update(
            {
                "content_hash": content_hash,
                "last_analyzed_content_hash": content_hash,
                "analysis_stale": False,
                "manual_edited_at": now_utc().isoformat(),
            }
        )
        job.parsed_requirements = parsed_requirements
    if {"description", "requirements", "responsibilities", "benefits_text"} & set(updates):
        content_hash = _content_hash(_job_analysis_text(job))
        parsed_requirements = dict(job.parsed_requirements or {})
        last_analyzed_hash = parsed_requirements.get("last_analyzed_content_hash")
        parsed_requirements.update(
            {
                "content_hash": content_hash,
                "manual_edited_at": now_utc().isoformat(),
                "analysis_stale": bool(last_analyzed_hash and last_analyzed_hash != content_hash),
            }
        )
        if not last_analyzed_hash:
            parsed_requirements["analysis_stale"] = True
        job.parsed_requirements = parsed_requirements
    write_audit(
        db,
        actor_id=actor_id,
        action="job.update",
        target_resource="jobs",
        target_id=job.id,
        old_data=old_data,
        new_data={
            "title": job.title,
            "description": job.description,
            "skills": job.skills,
            "status": job.status.value,
        },
    )
    db.commit()
    db.refresh(job)
    return job


def apply_job_action(
    db: Session,
    job_id: str,
    payload: JobActionRequest,
    *,
    actor_id: str | None = None,
) -> Job:
    job = db.get(Job, job_id)
    if not job or job.deleted_at is not None:
        raise AppError(code=ErrorCode.NOT_FOUND, message="Job not found", status_code=404)
    old_data = {"status": job.status.value, "is_active": job.is_active}
    _apply_scheduled_action(job, payload.action)
    write_audit(
        db,
        actor_id=actor_id,
        action="job.manual_action",
        target_resource="jobs",
        target_id=job.id,
        old_data=old_data,
        new_data={"status": job.status.value, "is_active": job.is_active, "action": payload.action},
    )
    db.commit()
    db.refresh(job)
    return job


def schedule_job_action(
    db: Session,
    job_id: str,
    payload: JobScheduleCreate,
    *,
    actor_id: str | None = None,
) -> JobScheduledAction:
    job = db.get(Job, job_id)
    if not job or job.deleted_at is not None:
        raise AppError(code=ErrorCode.NOT_FOUND, message="Job not found", status_code=404)
    run_at = _as_utc(payload.run_at)
    if run_at <= now_utc():
        raise AppError(
            code=ErrorCode.BAD_REQUEST,
            message="Scheduled time must be in the future",
            status_code=400,
        )
    scheduled = JobScheduledAction(
        job_id=job.id,
        action=payload.action,
        run_at=run_at,
        status="PENDING",
        requested_by=actor_id,
    )
    db.add(scheduled)
    write_audit(
        db,
        actor_id=actor_id,
        action="job.schedule_action",
        target_resource="job_scheduled_actions",
        target_id=scheduled.id,
        new_data={"job_id": job.id, "action": scheduled.action, "run_at": run_at.isoformat()},
    )
    db.commit()
    db.refresh(scheduled)
    return scheduled


def list_job_scheduled_actions(db: Session, job_id: str) -> list[JobScheduledAction]:
    return list(
        db.scalars(
            select(JobScheduledAction)
            .where(JobScheduledAction.job_id == job_id)
            .order_by(JobScheduledAction.run_at.asc())
        )
    )


def cancel_job_scheduled_action(
    db: Session,
    job_id: str,
    action_id: str,
    *,
    actor_id: str | None = None,
) -> JobScheduledAction:
    scheduled = db.get(JobScheduledAction, action_id)
    if not scheduled or scheduled.job_id != job_id:
        raise AppError(code=ErrorCode.NOT_FOUND, message="Scheduled action not found", status_code=404)
    if scheduled.status != "PENDING":
        raise AppError(
            code=ErrorCode.CONFLICT,
            message="Only pending scheduled actions can be cancelled",
            status_code=409,
        )
    scheduled.status = "CANCELLED"
    write_audit(
        db,
        actor_id=actor_id,
        action="job.cancel_scheduled_action",
        target_resource="job_scheduled_actions",
        target_id=scheduled.id,
        new_data={"job_id": job_id, "action": scheduled.action},
    )
    db.commit()
    db.refresh(scheduled)
    return scheduled


def run_due_job_scheduled_actions(db: Session, *, limit: int = 50) -> int:
    due = list(
        db.scalars(
            select(JobScheduledAction)
            .where(
                JobScheduledAction.status == "PENDING",
                JobScheduledAction.run_at <= now_utc(),
            )
            .order_by(JobScheduledAction.run_at.asc())
            .limit(limit)
        )
    )
    executed = 0
    for scheduled in due:
        job = db.get(Job, scheduled.job_id)
        if not job or job.deleted_at is not None:
            scheduled.status = "FAILED"
            scheduled.executed_at = now_utc()
            scheduled.error_message = "Job not found"
            continue
        try:
            _apply_scheduled_action(job, scheduled.action)
            scheduled.status = "DONE"
            scheduled.executed_at = now_utc()
            scheduled.error_message = None
            executed += 1
        except ValueError as exc:
            scheduled.status = "FAILED"
            scheduled.executed_at = now_utc()
            scheduled.error_message = str(exc)
    db.commit()
    return executed


def reanalyze_job(db: Session, job_id: str, *, actor_id: str | None = None) -> Job:
    job = db.get(Job, job_id)
    if not job or job.deleted_at is not None:
        raise AppError(code=ErrorCode.NOT_FOUND, message="Job not found", status_code=404)
    text = _job_analysis_text(job)
    approved, reasons, trace = evaluate_job_policy(text)
    try:
        extraction = extract_jd_from_text(text)
    except GeminiJDExtractionError as exc:
        raise AppError(
            code=ErrorCode.UPSTREAM_UNAVAILABLE,
            message=f"Unable to analyze this JD with Gemini right now: {exc}",
            status_code=502,
        ) from exc
    required_skills = normalize_skills([skill.name for skill in extraction.required_skills])
    nice_skills = normalize_skills([skill.name for skill in extraction.nice_to_have_skills])
    content_hash = _content_hash(text)
    parsed = {
        **extraction.model_dump(),
        "skills": required_skills,
        "nice_skill_names": nice_skills,
        "estimated_tokens": parse_job_requirements(text)["estimated_tokens"],
        "content_hash": content_hash,
        "last_analyzed_content_hash": content_hash,
        "analysis_stale": False,
    }
    job.parsed_requirements = {
        **parsed,
        "moderation": {"approved": approved, "reasons": reasons, "trace": trace},
    }
    if required_skills or nice_skills:
        job.skills = [*required_skills, *[skill for skill in nice_skills if skill not in required_skills]]
    job.embedding = embed_text(text)
    job.status = JobStatus.APPROVED if approved else JobStatus.PENDING_APPROVAL
    job.approval_source = ApprovalSource.AI_AUTOMATION if approved else None
    job.approved_by = actor_id if approved else None
    job.approved_at = now_utc() if approved else None
    log_ai_usage(
        db,
        org_id=job.org_id,
        user_id=actor_id,
        feature_name="job_policy_and_parse",
        input_text=text,
        output_text=str(job.parsed_requirements),
        provider=trace.get("provider"),
        model=trace.get("model"),
    )
    write_audit(
        db,
        actor_id=actor_id,
        action="job.reanalyze",
        target_resource="jobs",
        target_id=job.id,
        new_data={"status": job.status.value, "title": job.title},
    )
    db.commit()
    db.refresh(job)
    return job


def _job_analysis_text(job: Job) -> str:
    return "\n\n".join(
        part
        for part in [
            job.description,
            f"Requirements:\n{job.requirements}" if job.requirements else "",
            f"Responsibilities:\n{job.responsibilities}" if job.responsibilities else "",
            f"Benefits:\n{job.benefits_text}" if job.benefits_text else "",
        ]
        if part and part.strip()
    )


def _apply_scheduled_action(job: Job, action: str) -> None:
    if action == "PUBLISH":
        job.status = JobStatus.APPROVED
        job.is_active = True
        job.approval_source = ApprovalSource.AI_AUTOMATION
        job.approved_at = now_utc()
        return
    if action == "OPEN":
        job.is_active = True
        if job.status in {JobStatus.DRAFT, JobStatus.REJECTED, JobStatus.CLOSED}:
            job.status = JobStatus.APPROVED
            job.approval_source = ApprovalSource.AI_AUTOMATION
            job.approved_at = now_utc()
        return
    if action == "CLOSE":
        job.is_active = False
        job.status = JobStatus.CLOSED
        return
    raise ValueError(f"Unsupported scheduled job action: {action}")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=_app_timezone()).astimezone(UTC)
    return value.astimezone(UTC)


def _app_timezone():
    try:
        return ZoneInfo(settings.app_timezone)
    except ZoneInfoNotFoundError:
        return UTC


def _payload_analysis_text(
    description: str,
    requirements: str | None = None,
    responsibilities: str | None = None,
    benefits_text: str | None = None,
) -> str:
    return "\n\n".join(
        part
        for part in [
            description,
            f"Requirements:\n{requirements}" if requirements else "",
            f"Responsibilities:\n{responsibilities}" if responsibilities else "",
            f"Benefits:\n{benefits_text}" if benefits_text else "",
        ]
        if part and part.strip()
    )


def _parsed_requirements_with_metadata(
    parsed: dict,
    *,
    content_hash: str,
    analysis_stale: bool,
    approved: bool,
    reasons: list[str],
    trace: dict,
) -> dict:
    return {
        **parsed,
        "moderation": {"approved": approved, "reasons": reasons, "trace": trace},
        "content_hash": content_hash,
        "last_analyzed_content_hash": (
            content_hash if not analysis_stale else parsed.get("last_analyzed_content_hash")
        ),
        "analysis_stale": analysis_stale,
    }


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


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
