from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.opportunities.infrastructure.models import Bookmark, Event, Job
from app.modules.recruitment.infrastructure.models import CV, ApplicationTrackingLog, JobApplication
from app.modules.reporting.infrastructure.models import AIUsageLog, AuditLog
from app.modules.reporting.schemas import (
    DashboardActivity,
    DashboardApplication,
    DashboardCV,
    DashboardEvent,
    DashboardIdentity,
    DashboardJob,
    DashboardTrendPoint,
    MetricItem,
    PartnerCandidate,
    PartnerDashboard,
    StudentDashboard,
    UniversityDashboard,
)
from app.platform.database.models.identity import Organization, User, UserOrgRole
from app.platform.database.models.student import StudentProfile
from app.shared.enum import JobStatus, OrgType
from app.shared.errors import AppError, ErrorCode


def get_student_dashboard(
    db: Session, user: User, identity_id: str | None = None
) -> StudentDashboard:
    identity = _resolve_identity(db, user.id, identity_id, portal="student")
    profile = db.get(StudentProfile, user.id)
    if not profile:
        raise AppError(
            code=ErrorCode.NOT_FOUND, message="Student profile not found", status_code=404
        )

    cvs = list(
        db.scalars(
            select(CV)
            .where(CV.student_id == profile.id, CV.deleted_at.is_(None))
            .order_by(CV.created_at.desc())
        )
    )
    primary_cv = next((cv for cv in cvs if cv.is_primary), cvs[0] if cvs else None)
    approved_jobs = list(
        db.scalars(
            select(Job)
            .where(Job.status == JobStatus.APPROVED, Job.deleted_at.is_(None))
            .order_by(Job.created_at.desc())
            .limit(12)
        )
    )
    applications = list(
        db.scalars(
            select(JobApplication)
            .where(JobApplication.student_id == profile.id)
            .order_by(JobApplication.applied_at.desc())
            .limit(10)
        )
    )
    applied_job_ids = {app.job_id for app in applications}
    recommended = [
        _job_to_dashboard(job, db, primary_cv=primary_cv)
        for job in approved_jobs
        if job.id not in applied_job_ids
    ][:6]
    app_views = [_application_to_dashboard(db, app) for app in applications]
    cv_views = [_cv_to_dashboard(cv) for cv in cvs]
    saved_jobs = list(
        db.scalars(
            select(Job)
            .join(Bookmark, Bookmark.job_id == Job.id)
            .where(Bookmark.student_id == profile.id, Job.deleted_at.is_(None))
            .order_by(Bookmark.created_at.desc())
            .limit(4)
        )
    )
    events = list(
        db.scalars(
            select(Event)
            .where(Event.deleted_at.is_(None))
            .order_by(Event.start_time.asc())
            .limit(4)
        )
    )
    matched_skills = {skill for job in recommended for skill in job.tags}
    primary_skills = (
        set((primary_cv.parsed_data or {}).get("skills") or []) if primary_cv else set()
    )
    best_score = max((job.match_score or 0 for job in recommended), default=0)
    privacy = {
        "pii_masking": 96 if cvs else 0,
        "primary_cv_ready": bool(primary_cv),
        "consent_requests": sum(1 for app in applications if not app.consent_to_unmask),
    }
    return StudentDashboard(
        identity=identity,
        metrics=[
            MetricItem(
                label="Job fit cao nhất",
                value=f"{best_score:.0f}%",
                delta=f"{len(recommended)} job đang phù hợp",
                icon="brain",
            ),
            MetricItem(
                label="CV ẩn danh",
                value=str(len(cvs)),
                delta="Dữ liệu PII được che trước khi HR xem",
                icon="lock",
            ),
            MetricItem(
                label="Ứng tuyển",
                value=str(len(applications)),
                delta="Theo dõi pipeline theo thời gian thực",
                icon="activity",
            ),
            MetricItem(
                label="Yêu cầu đồng thuận",
                value=str(privacy["consent_requests"]),
                delta="Quyền mở danh tính do sinh viên kiểm soát",
                icon="database",
            ),
        ],
        recommended_jobs=recommended,
        applications=app_views,
        cvs=cv_views,
        privacy=privacy,
        saved_jobs=[_job_to_dashboard(job, db) for job in saved_jobs],
        skill_gaps=sorted(matched_skills - primary_skills)[:6],
        events=[
            DashboardEvent(
                id=event.id,
                title=event.title,
                event_type=event.event_type.value,
                start_time=event.start_time.isoformat(),
                location=event.location_address or event.meeting_url,
            )
            for event in events
        ],
        recent_activity=_application_activity(db, applications),
        application_distribution=_status_distribution(applications),
    )


def get_partner_dashboard(
    db: Session, user: User, identity_id: str | None = None
) -> PartnerDashboard:
    identity = _resolve_identity(db, user.id, identity_id, portal="partner")
    jobs = list(
        db.scalars(
            select(Job)
            .where(Job.org_id == identity.org_id, Job.deleted_at.is_(None))
            .order_by(Job.created_at.desc())
            .limit(20)
        )
    )
    applications = list(
        db.scalars(
            select(JobApplication)
            .join(Job, Job.id == JobApplication.job_id)
            .where(Job.org_id == identity.org_id)
            .order_by(JobApplication.applied_at.desc())
            .limit(20)
        )
    )
    approved_jobs = sum(1 for job in jobs if job.status == JobStatus.APPROVED)
    pending_jobs = sum(1 for job in jobs if job.status == JobStatus.PENDING_APPROVAL)
    usage = _usage_summary(db, identity.org_id)
    return PartnerDashboard(
        identity=identity,
        metrics=[
            MetricItem(
                label="Job đang mở",
                value=str(approved_jobs),
                delta=f"{pending_jobs} tin chờ trường duyệt",
                icon="database",
            ),
            MetricItem(
                label="Hồ sơ ẩn danh",
                value=str(len(applications)),
                delta="Ứng viên chưa mở PII",
                icon="lock",
            ),
            MetricItem(
                label="Shortlist AI",
                value=_avg_score(applications),
                delta="Tính từ CV đã ứng tuyển",
                icon="brain",
            ),
            MetricItem(
                label="Token AI",
                value=str(usage["total_tokens"]),
                delta=f"${usage['estimated_cost_usd']:.4f}",
                icon="wallet",
            ),
        ],
        jobs=[_job_to_dashboard(job, db) for job in jobs],
        candidates=[
            _candidate_to_dashboard(db, app, idx) for idx, app in enumerate(applications, start=1)
        ],
        ai_usage=usage,
        application_distribution=_status_distribution(applications),
        usage_trend=_usage_trend(db, identity.org_id),
        recent_activity=_application_activity(db, applications),
    )


def get_university_dashboard(
    db: Session, user: User, identity_id: str | None = None
) -> UniversityDashboard:
    identity = _resolve_identity(db, user.id, identity_id, portal="university")
    partners = list(
        db.scalars(
            select(Organization)
            .where(Organization.type == OrgType.PARTNER, Organization.deleted_at.is_(None))
            .order_by(Organization.created_at.desc())
            .limit(12)
        )
    )
    pending_jobs = list(
        db.scalars(
            select(Job)
            .where(Job.status == JobStatus.PENDING_APPROVAL, Job.deleted_at.is_(None))
            .order_by(Job.created_at.desc())
            .limit(12)
        )
    )
    total_jobs = (
        db.scalar(select(func.count()).select_from(Job).where(Job.deleted_at.is_(None))) or 0
    )
    verified_partners = sum(1 for org in partners if org.is_verified_partner)
    usage = _usage_summary(db, identity.org_id)
    return UniversityDashboard(
        identity=identity,
        metrics=[
            MetricItem(
                label="Đối tác",
                value=str(len(partners)),
                delta=f"{verified_partners} đã xác minh",
                icon="database",
            ),
            MetricItem(
                label="Chờ duyệt",
                value=str(len(pending_jobs)),
                delta="JD cần moderator xem lại",
                icon="activity",
            ),
            MetricItem(
                label="Tổng job",
                value=str(total_jobs),
                delta="Đồng bộ từ doanh nghiệp",
                icon="brain",
            ),
            MetricItem(
                label="Token AI",
                value=str(usage["total_tokens"]),
                delta=f"${usage['estimated_cost_usd']:.4f}",
                icon="wallet",
            ),
        ],
        moderation_queue=[_job_to_dashboard(job, db) for job in pending_jobs],
        partners=[
            {
                "id": org.id,
                "name": org.name,
                "is_verified_partner": org.is_verified_partner,
                "metadata": org.metadata_json,
            }
            for org in partners
        ],
        ai_usage=usage,
        moderation_distribution=_job_status_distribution(db),
        usage_trend=_usage_trend(db, identity.org_id),
        recent_activity=_audit_activity(db),
    )


def _resolve_identity(
    db: Session, user_id: str, identity_id: str | None, *, portal: str
) -> DashboardIdentity:
    stmt = select(UserOrgRole).where(UserOrgRole.user_id == user_id)
    if identity_id:
        stmt = stmt.where(UserOrgRole.id == identity_id)
    for item in db.scalars(stmt).unique():
        item_portal = _portal_for(item)
        if item_portal == portal:
            return DashboardIdentity(
                id=item.id,
                org_id=item.org_id,
                org_name=item.org.name,
                org_type=item.org.type.value,
                role_name=item.role.name,
                portal=item_portal,
            )
    raise AppError(
        code=ErrorCode.FORBIDDEN, message=f"No {portal} identity for current user", status_code=403
    )


def _portal_for(item: UserOrgRole) -> str:
    if item.org.type == OrgType.UNIVERSITY and item.role.name == "student":
        return "student"
    if item.org.type == OrgType.PARTNER:
        return "partner"
    return "university"


def _job_to_dashboard(job: Job, db: Session, *, primary_cv: CV | None = None) -> DashboardJob:
    org = db.get(Organization, job.org_id)
    metadata = job.parsed_requirements or {}
    tags = _extract_skills(metadata)
    match_score = None
    reason = None
    if primary_cv:
        cv_skills = {
            str(skill).strip()
            for skill in (primary_cv.skills or [])
            if str(skill).strip()
        }
        normalized_cv_skills = {skill.casefold(): skill for skill in cv_skills}
        matched_skills = [
            normalized_cv_skills[tag.casefold()]
            for tag in tags
            if tag.casefold() in normalized_cv_skills
        ]
        match_score = round(100 * len(matched_skills) / max(1, len(tags)), 2)
        reason = (
            f"Khớp kỹ năng: {', '.join(matched_skills[:3])}"
            if matched_skills
            else "Cần bổ sung kỹ năng theo JD."
        )
    return DashboardJob(
        id=job.id,
        title=job.title,
        company=org.name if org else "Unknown organization",
        location=str(
            metadata.get("location") or (org.metadata_json.get("location") if org else "") or ""
        ),
        salary_range=str(
            metadata.get("salary_range")
            or (org.metadata_json.get("salary_range") if org else "")
            or ""
        ),
        status=job.status.value,
        match_score=match_score,
        tags=tags[:6],
        reason=reason,
    )


def _application_to_dashboard(db: Session, app: JobApplication) -> DashboardApplication:
    job = db.get(Job, app.job_id)
    org = db.get(Organization, job.org_id) if job else None
    return DashboardApplication(
        id=app.id,
        job_id=app.job_id,
        job_title=job.title if job else "Unknown job",
        company=org.name if org else "Unknown organization",
        status=app.status.value,
        ai_match_score=float(app.ai_match_score) if app.ai_match_score is not None else None,
        consent_to_unmask=app.consent_to_unmask,
    )


def _candidate_to_dashboard(db: Session, app: JobApplication, idx: int) -> PartnerCandidate:
    job = db.get(Job, app.job_id)
    cv = db.get(CV, app.cv_id)
    return PartnerCandidate(
        application_id=app.id,
        job_id=app.job_id,
        job_title=job.title if job else "Unknown job",
        anonymous_label=f"Ứng viên #{idx:03d}",
        status=app.status.value,
        ai_match_score=float(app.ai_match_score) if app.ai_match_score is not None else None,
        masked_preview=_masked_preview(cv.masked_data if cv else {}),
        consent_to_unmask=app.consent_to_unmask,
    )


def _cv_to_dashboard(cv: CV) -> DashboardCV:
    return DashboardCV(
        id=cv.id,
        is_primary=cv.is_primary,
        masked_preview=_masked_preview(cv.masked_data),
        skills=list(cv.skills or (cv.parsed_data or {}).get("skills") or [])[:8],
    )


def _extract_skills(parsed_requirements: dict[str, Any]) -> list[str]:
    skills = parsed_requirements.get("skills") or parsed_requirements.get("required_skills") or []
    return [str(skill) for skill in skills if skill][:8]


def _masked_preview(masked_data: dict[str, Any]) -> str:
    text = str(masked_data.get("text") or masked_data)[:220]
    return text.replace("\n", " ")


def _usage_summary(db: Session, org_id: str) -> dict[str, Any]:
    row = db.execute(
        select(
            func.coalesce(func.sum(AIUsageLog.input_tokens), 0),
            func.coalesce(func.sum(AIUsageLog.output_tokens), 0),
            func.coalesce(func.sum(AIUsageLog.cost_usd), 0),
        ).where(AIUsageLog.org_id == org_id)
    ).one()
    input_tokens = int(row[0] or 0)
    output_tokens = int(row[1] or 0)
    cost = float(row[2] or 0)
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "estimated_cost_usd": cost,
    }


def _avg_score(applications: list[JobApplication]) -> str:
    scores = [float(app.ai_match_score) for app in applications if app.ai_match_score is not None]
    if not scores:
        return "0%"
    return f"{sum(scores) / len(scores):.0f}%"


def _status_distribution(applications: list[JobApplication]) -> list[DashboardTrendPoint]:
    counts: dict[str, int] = {}
    for application in applications:
        counts[application.status.value] = counts.get(application.status.value, 0) + 1
    return [DashboardTrendPoint(label=key, value=value) for key, value in counts.items()]


def _job_status_distribution(db: Session) -> list[DashboardTrendPoint]:
    rows = db.execute(
        select(Job.status, func.count()).where(Job.deleted_at.is_(None)).group_by(Job.status)
    ).all()
    return [
        DashboardTrendPoint(label=status.value, value=int(count))
        for status, count in rows
    ]


def _usage_trend(db: Session, org_id: str) -> list[DashboardTrendPoint]:
    logs = list(
        db.scalars(
            select(AIUsageLog)
            .where(AIUsageLog.org_id == org_id)
            .order_by(AIUsageLog.created_at.asc())
            .limit(30)
        )
    )
    daily: dict[str, int] = {}
    for log in logs:
        label = log.created_at.strftime("%d/%m")
        daily[label] = daily.get(label, 0) + log.input_tokens + log.output_tokens
    return [DashboardTrendPoint(label=label, value=value) for label, value in daily.items()]


def _application_activity(
    db: Session,
    applications: list[JobApplication],
) -> list[DashboardActivity]:
    application_ids = [application.id for application in applications]
    if not application_ids:
        return []
    logs = list(
        db.scalars(
            select(ApplicationTrackingLog)
            .where(ApplicationTrackingLog.application_id.in_(application_ids))
            .order_by(ApplicationTrackingLog.changed_at.desc())
            .limit(8)
        )
    )
    return [
        DashboardActivity(
            id=log.id,
            title=log.new_status.value.replace("_", " ").title(),
            description=log.note or "Application status updated",
            occurred_at=log.changed_at.isoformat(),
            tone="success" if log.new_status.value in {"HIRED", "OFFERED"} else "info",
        )
        for log in logs
    ]


def _audit_activity(db: Session) -> list[DashboardActivity]:
    logs = list(db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(8)))
    return [
        DashboardActivity(
            id=log.id,
            title=log.action.replace(".", " ").title(),
            description=f"{log.target_resource} · {log.target_id or 'system'}",
            occurred_at=log.created_at.isoformat(),
            tone="info",
        )
        for log in logs
    ]
