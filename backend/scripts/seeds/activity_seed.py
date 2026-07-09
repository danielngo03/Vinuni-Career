# ruff: noqa: E501
"""Activity seed — the *usable* data that turns the shell seed into a live product.

``scripts/seed_dev.py`` builds the SHELL (users, orgs, RBAC, jobs, onboarding,
events-less marketplace). After a DB reset that leaves every persona logged in to
an empty product. This module seeds the MISSING activity so each persona has real,
usable data:

1. ``seed_ai_defaults``          — provider/model registry + 6 default function slots
2. ``seed_student_profiles``     — identity-only profile: location + open-to-work + visibility
3. ``seed_student_cvs``          — one finalized (``ready``) builder CV per student
4. ``seed_applications``         — students apply across companies (mix anonymous)
5. ``seed_pipeline``             — review -> advance -> interview -> scorecard -> offer
6. ``seed_events``               — job fairs / workshops per a couple orgs
7. ``seed_company_reviews``      — published reviews backed by real interview/offer eligibility
8. ``seed_notifications``        — a few partner-facing in-app rows
9. ``seed_advertising``          — active sponsored placements on real jobs (reuses the demo chain)

Everything is IDEMPOTENT (re-runnable against the live DB). Recruitment flows go
through the real SERVICE layer so snapshots, counters, audit, stage rows,
notifications and offer state are all correct. The acting partner principal is a
trusted offline single-writer granted ``*`` for the org that owns the job (the
same rationale/pattern as ``scripts/seed_demo_marketplace``): real service RBAC
gates all pass while tenant isolation still binds the principal to its org.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.ai.gateway import provider_registry
from app.modules.auth.application.context import RequestContext
from app.modules.auth.domain.personas import permissions_for
from app.modules.documents.application import cv_lifecycle_service, cv_service
from app.modules.documents.domain.models import CvProfile
from app.modules.notifications.domain.models import Notification
from app.modules.opportunities.domain.event_models import Event
from app.modules.opportunities.domain.models import Job
from app.modules.organization.domain.catalog import slugify
from app.modules.organization.domain.models import Organization
from app.modules.recruitment.application import (
    apply_service,
    decision_service,
    interview_service,
    offer_service,
    scorecard_service,
    stage_service,
)
from app.modules.recruitment.domain import offer as offer_domain
from app.modules.recruitment.domain import scorecard as scorecard_domain
from app.modules.recruitment.domain.models import Application
from app.modules.reviews.application import rating_projection
from app.modules.reviews.domain import entities as review_entities
from app.modules.reviews.domain.models import CompanyReview, ReviewRating
from app.modules.users.domain.models import User
from app.shared.permissions import Principal
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

NOW = datetime.now(tz=UTC)
CTX = RequestContext(ip="127.0.0.1", user_agent="seed-dev/activity")

# Org owning a job -> the seeded partner user that acts on its pipeline. Only orgs
# with a seeded active member can drive review/interview/offer flows.
PARTNER_ACTOR: dict[str, str] = {
    "fpt-software": "partner",
    "vietcombank": "vcb_recruiter",
    "momo-payment": "momo_recruiter",
}


# --------------------------------------------------------------------------- #
# Principals                                                                   #
# --------------------------------------------------------------------------- #


def _student_principal(user: User) -> Principal:
    return Principal(
        user_id=user.id,
        persona="student",
        org_id=None,
        is_superadmin=False,
        permissions=permissions_for("student"),
    )


def _partner_principal(user: User, org: Organization) -> Principal:
    """Trusted offline single-writer for ``org`` (mirrors a partner admin's ``*``)."""

    return Principal(
        user_id=user.id,
        persona="partner_member",
        org_id=org.id,
        is_superadmin=False,
        permissions=frozenset({"*"}),
    )


# --------------------------------------------------------------------------- #
# 1. AI provider/model registry + default slots                               #
# --------------------------------------------------------------------------- #


async def seed_ai_defaults(session: AsyncSession) -> None:
    print("\n[ai defaults]")
    await provider_registry.ensure_defaults(session)
    await session.commit()
    print("  [ok] AI provider/model registry + 6 default function slots ensured")


# --------------------------------------------------------------------------- #
# 2. Student profiles (identity-only: location + open-to-work + visibility)    #
# --------------------------------------------------------------------------- #

_STUDENT_PROFILE_SPECS: dict[str, dict] = {
    "vinuni_student": {"phone": "+84 90 123 4567", "location_city": "Hà Nội", "visibility": "public"},
    "vinuni_student_data": {"phone": "+84 90 234 5678", "location_city": "Hà Nội", "visibility": "public"},
    "vinuni_student_business": {"phone": "+84 90 345 6789", "location_city": "Hồ Chí Minh", "visibility": "vinuni_only"},
    "external_student": {"phone": "+84 90 456 7890", "location_city": "Hồ Chí Minh", "visibility": "vinuni_only"},
}


async def seed_student_profiles(session: AsyncSession, users: dict[str, User]) -> None:
    from app.modules.student_profiles.application import profile_service

    print("\n[student profiles]")
    for key, spec in _STUDENT_PROFILE_SPECS.items():
        user = users.get(key)
        if user is None:
            continue
        principal = _student_principal(user)
        # Lazy-create the identity-only profile shell, then set the discoverable
        # career signal (open-to-work) + visibility so the talent pool works.
        await profile_service.get_my_profile(session, principal=principal)
        await profile_service.update_my_profile(
            session,
            principal=principal,
            payload={
                "phone": spec["phone"],
                "location_city": spec["location_city"],
                "location_country": "Vietnam",
                "is_open_to_work": True,
                "profile_visibility": spec["visibility"],
                "show_email": "invited",
                "show_phone": "invited",
            },
            ctx=CTX,
        )
        print(f"  [set] profile {user.email} -> open_to_work, {spec['visibility']}")


# --------------------------------------------------------------------------- #
# 3. Builder CVs (one finalized `ready` CV per student)                        #
# --------------------------------------------------------------------------- #

# Each CV carries structured section content in the EXACT shape the CV-JD scorer
# consumes: header (flat contact fields), summary (`text`), education/experience/
# projects (`entries` with heading/subheading/timeframe/highlights), skills
# (`items` with a 0-100 `level`). This is what makes fit scores + talent search real.
_STUDENT_CV_CONTENT: dict[str, dict] = {
    "vinuni_student": {
        "title": "Backend Engineer CV — Nguyễn Minh Anh",
        "header": {"name": "Nguyễn Minh Anh", "title": "Backend Software Engineer", "email": "student@vinuni.edu.vn", "phone": "+84 90 123 4567", "location": "Hà Nội, Việt Nam"},
        "summary": "Sinh viên năm cuối Khoa học Máy tính tại VinUniversity, đam mê phát triển backend và hệ thống phân tán. Có kinh nghiệm xây dựng REST API với Python/FastAPI và tối ưu cơ sở dữ liệu PostgreSQL.",
        "education": [{"heading": "Cử nhân Khoa học Máy tính", "subheading": "VinUniversity", "timeframe": "2022 - 2026", "location": "Hà Nội", "highlights": ["GPA 3.6/4.0", "Học bổng tài năng VinUni", "Chủ nhiệm CLB Lập trình"]}],
        "experience": [{"heading": "Software Engineering Intern", "subheading": "TechLab Startup", "timeframe": "06/2024 - 12/2024", "location": "Hà Nội", "highlights": ["Xây dựng REST API với FastAPI và PostgreSQL phục vụ 10k+ người dùng", "Viết unit/integration test đạt 85% coverage", "Triển khai CI/CD với GitHub Actions và Docker"]}],
        "projects": [{"heading": "Career Platform", "subheading": "Đồ án cá nhân", "timeframe": "2024", "highlights": ["Nền tảng tuyển dụng với async worker và hàng đợi tác vụ", "Backend FastAPI + SQLAlchemy 2.x async + Redis"]}],
        "skills": [{"name": "Python", "level": 85}, {"name": "FastAPI", "level": 80}, {"name": "PostgreSQL", "level": 76}, {"name": "Docker", "level": 70}, {"name": "Java", "level": 64}, {"name": "Git", "level": 82}, {"name": "REST APIs", "level": 84}, {"name": "Microservices", "level": 66}],
    },
    "vinuni_student_data": {
        "title": "Data Analyst CV — Lê Gia Hân",
        "header": {"name": "Lê Gia Hân", "title": "Data Analyst", "email": "data.student@vinuni.edu.vn", "phone": "+84 90 234 5678", "location": "Hà Nội, Việt Nam"},
        "summary": "Sinh viên Khoa học Dữ liệu với nền tảng thống kê vững chắc và kỹ năng SQL/Python. Quan tâm đến phân tích dữ liệu ngân hàng và trực quan hóa dữ liệu bằng Power BI.",
        "education": [{"heading": "Cử nhân Khoa học Dữ liệu", "subheading": "VinUniversity", "timeframe": "2022 - 2026", "location": "Hà Nội", "highlights": ["GPA 3.7/4.0", "Chứng chỉ Google Data Analytics"]}],
        "experience": [{"heading": "Data Analyst Intern", "subheading": "FinInsight Analytics", "timeframe": "05/2024 - 11/2024", "location": "Hà Nội", "highlights": ["Phân tích dữ liệu giao dịch và hành vi khách hàng bằng SQL và Python", "Xây dựng dashboard Power BI theo dõi KPI cho khối bán lẻ", "Tự động hóa quy trình ETL báo cáo hàng tuần"]}],
        "projects": [{"heading": "Customer Churn Prediction", "subheading": "Đồ án học phần", "timeframe": "2024", "highlights": ["Mô hình dự báo rời bỏ khách hàng với scikit-learn", "Đạt AUC 0.86 trên tập kiểm định"]}],
        "skills": [{"name": "SQL", "level": 88}, {"name": "Python", "level": 82}, {"name": "Power BI", "level": 78}, {"name": "Pandas", "level": 80}, {"name": "Statistics", "level": 75}, {"name": "Machine Learning", "level": 64}, {"name": "Tableau", "level": 68}, {"name": "Data Analysis", "level": 85}],
    },
    "vinuni_student_business": {
        "title": "Business Development CV — Đỗ Minh Quân",
        "header": {"name": "Đỗ Minh Quân", "title": "Business Development", "email": "business.student@vinuni.edu.vn", "phone": "+84 90 345 6789", "location": "Hồ Chí Minh, Việt Nam"},
        "summary": "Sinh viên Quản trị Kinh doanh năng động, có kinh nghiệm nghiên cứu thị trường và phát triển đối tác. Đam mê fintech và mô hình kinh doanh nền tảng.",
        "education": [{"heading": "Cử nhân Quản trị Kinh doanh", "subheading": "VinUniversity", "timeframe": "2022 - 2026", "location": "Hồ Chí Minh", "highlights": ["GPA 3.5/4.0", "Phó chủ tịch CLB Khởi nghiệp"]}],
        "experience": [{"heading": "Business Development Intern", "subheading": "GrowthPartners Vietnam", "timeframe": "06/2024 - 12/2024", "location": "Hồ Chí Minh", "highlights": ["Nghiên cứu thị trường và xác định 40+ merchant tiềm năng", "Chuẩn bị pitch deck và hỗ trợ chốt 8 hợp đồng đối tác", "Theo dõi pipeline deal trên CRM"]}],
        "projects": [{"heading": "Market Entry Analysis — F&B", "subheading": "Case competition", "timeframe": "2024", "highlights": ["Top 5 toàn quốc cuộc thi phân tích kinh doanh", "Đề xuất chiến lược thâm nhập thị trường mới"]}],
        "skills": [{"name": "Market Research", "level": 82}, {"name": "Excel", "level": 85}, {"name": "Business Development", "level": 76}, {"name": "Communication", "level": 88}, {"name": "PowerPoint", "level": 84}, {"name": "Data Analysis", "level": 70}, {"name": "CRM", "level": 68}],
    },
    "external_student": {
        "title": "Software Engineer CV — Trần Hữu Đức",
        "header": {"name": "Trần Hữu Đức", "title": "Software Engineer", "email": "student@gmail.com", "phone": "+84 90 456 7890", "location": "Hồ Chí Minh, Việt Nam"},
        "summary": "Lập trình viên trẻ với nền tảng full-stack, thành thạo Python và JavaScript. Tìm kiếm cơ hội thực tập backend để phát triển kỹ năng kỹ thuật.",
        "education": [{"heading": "Cử nhân Công nghệ Thông tin", "subheading": "Đại học Bách Khoa TP.HCM", "timeframe": "2021 - 2025", "location": "Hồ Chí Minh", "highlights": ["GPA 3.4/4.0", "Thành viên đội tuyển ACM-ICPC cấp trường"]}],
        "experience": [{"heading": "Freelance Web Developer", "subheading": "Tự do", "timeframe": "2023 - 2024", "location": "Remote", "highlights": ["Xây dựng 5+ website cho khách hàng nhỏ với React và FastAPI", "Thiết kế và triển khai REST API cùng cơ sở dữ liệu PostgreSQL"]}],
        "projects": [{"heading": "E-commerce API", "subheading": "Đồ án cá nhân", "timeframe": "2024", "highlights": ["API thương mại điện tử với xác thực JWT", "Backend Python + PostgreSQL + Redis cache"]}],
        "skills": [{"name": "Python", "level": 78}, {"name": "SQL", "level": 74}, {"name": "Git", "level": 80}, {"name": "REST APIs", "level": 76}, {"name": "JavaScript", "level": 70}, {"name": "React", "level": 68}, {"name": "FastAPI", "level": 66}],
    },
}


async def _existing_ready_cv(session: AsyncSession, *, user_id: uuid.UUID, title: str) -> CvProfile | None:
    return (
        await session.execute(
            select(CvProfile).where(
                CvProfile.user_id == user_id,
                CvProfile.title == title,
                CvProfile.status == "ready",
                CvProfile.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()


def _cv_selection(detail: dict) -> dict:
    return {
        "type": "builder_cv",
        "cv_profile_id": detail["id"],
        "cv_version_id": detail["current_version_id"],
        "uploaded_document_id": None,
    }


async def _write_section(
    session: AsyncSession,
    *,
    principal: Principal,
    cv_id: uuid.UUID,
    by_type: dict[str, uuid.UUID],
    section_type: str,
    content: dict,
) -> None:
    sid = by_type.get(section_type)
    if sid is None:
        return
    await cv_service.upsert_section(
        session,
        principal=principal,
        cv_id=cv_id,
        section_id=sid,
        payload={"section_type": section_type, "content": content},
        ctx=CTX,
    )


async def seed_student_cvs(session: AsyncSession, users: dict[str, User]) -> dict[str, dict]:
    """Create one finalized (``ready``) builder CV per student; return cv_selections."""

    print("\n[student CVs]")
    selections: dict[str, dict] = {}
    for key, content in _STUDENT_CV_CONTENT.items():
        user = users.get(key)
        if user is None:
            continue
        principal = _student_principal(user)
        title = content["title"]

        existing = await _existing_ready_cv(session, user_id=user.id, title=title)
        if existing is not None:
            detail = await cv_service.get_cv(session, principal=principal, cv_id=existing.id)
            selections[key] = _cv_selection(detail)
            print(f"  [skip] CV for {user.email} already finalized")
            continue

        cv = await cv_service.create_cv(
            session,
            principal=principal,
            payload={"title": title, "creation_mode": "blank_template", "language": "vi"},
            ctx=CTX,
        )
        cv_id = uuid.UUID(cv["id"])
        by_type = {s["section_type"]: uuid.UUID(s["id"]) for s in cv["sections"]}

        section_payloads = [
            ("header", content["header"]),
            ("summary", {"text": content["summary"]}),
            ("education", {"entries": content["education"]}),
            ("experience", {"entries": content["experience"]}),
            ("projects", {"entries": content["projects"]}),
            ("skills", {"items": content["skills"]}),
        ]
        for section_type, section_content in section_payloads:
            await _write_section(
                session,
                principal=principal,
                cv_id=cv_id,
                by_type=by_type,
                section_type=section_type,
                content=section_content,
            )

        detail = await cv_lifecycle_service.finalize_cv(
            session, principal=principal, cv_id=cv_id, ctx=CTX
        )
        selections[key] = _cv_selection(detail)
        print(f"  [create] CV '{title}' finalized for {user.email}")

    return selections


# --------------------------------------------------------------------------- #
# 4. Applications                                                              #
# --------------------------------------------------------------------------- #

# (student_key, org_slug, job title substring, is_anonymous, progression target)
# targets: applied | reviewed | interview | offer_sent | offer_accepted
_APPLICATION_SPECS: list[tuple[str, str, str, bool, str]] = [
    ("vinuni_student", "fpt-software", "Software Engineering Intern", False, "offer_accepted"),
    ("vinuni_student", "fpt-software", "Senior Java Backend", False, "reviewed"),
    ("vinuni_student", "tiki-corporation", "Machine Learning Engineer", True, "applied"),
    ("vinuni_student", "momo-payment", "Kỹ sư Backend", False, "interview"),
    ("vinuni_student_data", "vietcombank", "Phân tích Dữ liệu", False, "interview"),
    ("vinuni_student_data", "tiki-corporation", "Machine Learning Engineer", False, "applied"),
    ("vinuni_student_data", "fpt-software", "QA Automation", True, "applied"),
    ("vinuni_student_business", "momo-payment", "Business Development Intern", False, "offer_sent"),
    ("vinuni_student_business", "kpmg-vietnam", "ESG", False, "applied"),
    ("vinuni_student_business", "tiki-corporation", "Product Manager", False, "applied"),
    ("external_student", "fpt-software", "Software Engineering Intern", False, "interview"),
    ("external_student", "ssi-securities", "Investment Research", False, "applied"),
]


async def _find_job(session: AsyncSession, *, org_id: uuid.UUID, title_substr: str) -> Job | None:
    return (
        await session.execute(
            select(Job)
            .where(
                Job.org_id == org_id,
                Job.title.ilike(f"%{title_substr}%"),
                Job.status == "active",
                Job.deleted_at.is_(None),
            )
            .order_by(Job.title)
            .limit(1)
        )
    ).scalar_one_or_none()


async def seed_applications(
    session: AsyncSession,
    orgs: dict[str, Organization],
    users: dict[str, User],
    cv_selections: dict[str, dict],
) -> list[dict]:
    """Apply students to jobs across companies (idempotent via stable keys).

    Returns a progression plan: one entry per application with its target state.
    """

    print("\n[applications]")
    plan: list[dict] = []
    for student_key, org_slug, title_substr, is_anonymous, target in _APPLICATION_SPECS:
        student = users.get(student_key)
        org = orgs.get(org_slug)
        cv_selection = cv_selections.get(student_key)
        if student is None or org is None or cv_selection is None:
            continue
        job = await _find_job(session, org_id=org.id, title_substr=title_substr)
        if job is None:
            print(f"  [warn] no job '{title_substr}' at {org_slug}; skipping")
            continue

        principal = _student_principal(student)
        idem = f"seed-apply-{student_key}-{job.id}"
        result = await apply_service.apply_to_job(
            session,
            principal=principal,
            payload={
                "job_id": job.id,
                "cv_selection": cv_selection,
                "cover_letter": "Em rất mong muốn được ứng tuyển và đóng góp cho vị trí này.",
                "screening_answers": {},
                "is_anonymous": is_anonymous,
                "idempotency_key": idem,
            },
            ctx=CTX,
        )
        app_id = uuid.UUID(result["id"])
        plan.append(
            {
                "application_id": app_id,
                "org_slug": org_slug,
                "student_key": student_key,
                "target": target,
                "is_anonymous": is_anonymous,
                "job_title": job.title,
            }
        )
        tag = "anon" if is_anonymous else "named"
        print(f"  [apply] {student.email} -> {job.title[:40]} ({tag}, target={target})")

    return plan


# --------------------------------------------------------------------------- #
# 5. Pipeline progression (review -> advance -> interview -> scorecard -> offer) #
# --------------------------------------------------------------------------- #

_ORDER = {"applied": 0, "reviewed": 1, "interview": 2, "offer_sent": 3, "offer_accepted": 4}


async def _app_status(session: AsyncSession, app_id: uuid.UUID) -> str | None:
    return (
        await session.execute(select(Application.status).where(Application.id == app_id))
    ).scalar_one_or_none()


async def _progress_one(
    session: AsyncSession,
    *,
    entry: dict,
    actor: Principal,
    student: Principal,
) -> None:
    app_id = entry["application_id"]
    target_order = _ORDER[entry["target"]]

    # review: submitted -> under_review (+ materialize Screening stage-1).
    await decision_service.review_application(session, principal=actor, application_id=app_id, ctx=CTX)
    if target_order < _ORDER["interview"]:
        return

    # advance to stage-2 (Interview), then schedule + score.
    await stage_service.advance_application_stage(
        session, principal=actor, application_id=app_id,
        idempotency_key=f"seed-adv2-{app_id}", ctx=CTX,
    )
    await interview_service.schedule_interview(
        session, principal=actor, application_id=app_id,
        mode="online", scheduled_at=NOW + timedelta(days=3),
        assignee_ids=[actor.user_id], duration_minutes=60,
        meeting_link="https://meet.google.com/seed-interview",
        title="Vòng phỏng vấn kỹ thuật", ctx=CTX,
    )
    await scorecard_service.submit_scorecard(
        session, principal=actor, application_id=app_id,
        recommendation="yes",
        scores=[{"criterion_key": k, "score": 4} for k in scorecard_domain.DEFAULT_CRITERION_KEYS],
        comment="Ứng viên thể hiện tốt, phù hợp với vị trí.", ctx=CTX,
    )
    if target_order < _ORDER["offer_sent"]:
        return

    # advance to stage-3 (Offer), then create -> submit -> approve -> send.
    await stage_service.advance_application_stage(
        session, principal=actor, application_id=app_id,
        idempotency_key=f"seed-adv3-{app_id}", ctx=CTX,
    )
    offer = await offer_service.create_offer(
        session, principal=actor, application_id=app_id,
        position_title=entry["job_title"], expiry_date=NOW + timedelta(days=14),
        salary_amount=8_000_000 if "Intern" in entry["job_title"] else 30_000_000,
        salary_currency=offer_domain.DEFAULT_CURRENCY, salary_period=offer_domain.DEFAULT_PERIOD,
        benefits_summary="Thưởng hiệu suất, bảo hiểm sức khỏe, đào tạo.",
        ctx=CTX,
    )
    offer_id = uuid.UUID(offer["id"])
    await offer_service.submit_offer(session, principal=actor, offer_id=offer_id, ctx=CTX)
    await offer_service.approve_offer(
        session, principal=actor, offer_id=offer_id,
        decision=offer_domain.APPROVE_DECISION, ctx=CTX,
    )
    await offer_service.send_offer(session, principal=actor, offer_id=offer_id, ctx=CTX)
    if target_order < _ORDER["offer_accepted"]:
        return

    # candidate accepts the sent offer.
    await offer_service.respond_offer(
        session, principal=student, offer_id=offer_id,
        decision=offer_domain.RESPOND_ACCEPTED,
        idempotency_key=f"seed-respond-{offer_id}", ctx=CTX,
    )


async def seed_pipeline(
    session: AsyncSession,
    plan: list[dict],
    orgs: dict[str, Organization],
    users: dict[str, User],
) -> None:
    print("\n[pipeline progression]")
    for entry in plan:
        if entry["target"] == "applied":
            continue
        org_slug = entry["org_slug"]
        actor_key = PARTNER_ACTOR.get(org_slug)
        if actor_key is None:
            continue  # no seeded partner member for this org
        # Only progress a freshly-submitted application; anything already moved was
        # progressed on an earlier run — skip so re-runs never double-advance.
        status = await _app_status(session, entry["application_id"])
        if status != "submitted":
            print(f"  [skip] {entry['student_key']} @ {org_slug} already progressed ({status})")
            continue
        actor = _partner_principal(users[actor_key], orgs[org_slug])
        student = _student_principal(users[entry["student_key"]])
        await _progress_one(session, entry=entry, actor=actor, student=student)
        print(f"  [progress] {entry['student_key']} @ {org_slug} -> {entry['target']}")


# --------------------------------------------------------------------------- #
# 6. Events                                                                    #
# --------------------------------------------------------------------------- #

_EVENT_SPECS: list[dict] = [
    {
        "org": "fpt-software", "creator": "partner",
        "title": "FPT Software Career Fair 2026",
        "description": "Ngày hội việc làm FPT Software 2026 — gặp gỡ nhà tuyển dụng, phỏng vấn nhanh và tìm hiểu cơ hội thực tập/toàn thời gian trong lĩnh vực công nghệ.",
        "event_type": "career_fair", "format": "onsite",
        "venue_name": "FPT Tower", "venue_address": "10 Phạm Văn Bạch, Cầu Giấy, Hà Nội",
        "days": 14, "duration_hours": 6, "capacity": 300, "is_sponsored": True, "is_featured": True,
        "tags": ["technology", "internship", "fulltime"],
    },
    {
        "org": "vinuni", "creator": "career_admin",
        "title": "VinUni Workshop: CV & Interview Mastery",
        "description": "Hội thảo thực hành do Trung tâm Hướng nghiệp VinUni tổ chức: cách viết CV nổi bật, chuẩn bị phỏng vấn và xây dựng thương hiệu cá nhân.",
        "event_type": "workshop", "format": "hybrid",
        "venue_name": "VinUniversity Campus", "venue_address": "Vinhomes Ocean Park, Gia Lâm, Hà Nội",
        "days": 10, "duration_hours": 3, "capacity": 120, "is_sponsored": False, "is_featured": True,
        "tags": ["career", "workshop", "students"],
    },
    {
        "org": "momo-payment", "creator": "momo_recruiter",
        "title": "MoMo Fintech Info Session",
        "description": "Buổi giới thiệu về văn hóa, sản phẩm và lộ trình tuyển dụng tại MoMo — dành cho sinh viên quan tâm đến fintech và thanh toán số.",
        "event_type": "info_session", "format": "online",
        "venue_name": None, "venue_address": None,
        "days": 7, "duration_hours": 2, "capacity": None, "is_sponsored": False, "is_featured": False,
        "tags": ["fintech", "info-session"],
    },
]


async def seed_events(session: AsyncSession, orgs: dict[str, Organization], users: dict[str, User]) -> None:
    print("\n[events]")
    created = 0
    for spec in _EVENT_SPECS:
        org = orgs.get(spec["org"])
        creator = users.get(spec["creator"])
        if org is None or creator is None:
            continue
        slug = slugify(f"{spec['title']}-{org.slug}")[:590]
        existing = (
            await session.execute(select(Event.id).where(Event.slug == slug))
        ).scalar_one_or_none()
        if existing is not None:
            print(f"  [skip] event '{spec['title']}' already exists")
            continue
        starts = NOW + timedelta(days=spec["days"])
        event = Event(
            id=uuid.uuid4(),
            org_id=org.id,
            created_by=creator.id,
            title=spec["title"],
            slug=slug,
            description=spec["description"],
            event_type=spec["event_type"],
            format=spec["format"],
            venue_name=spec["venue_name"],
            venue_address=spec["venue_address"],
            starts_at=starts,
            ends_at=starts + timedelta(hours=spec["duration_hours"]),
            timezone="Asia/Ho_Chi_Minh",
            registration_opens_at=NOW - timedelta(days=1),
            registration_closes_at=starts - timedelta(hours=6),
            capacity=spec["capacity"],
            registration_count=0,
            visibility="public",
            status="published",
            moderation_status="approved",
            approved_by=users["admin"].id if "admin" in users else creator.id,
            approved_at=NOW,
            submitted_at=NOW - timedelta(days=1),
            published_at=NOW,
            is_featured=spec["is_featured"],
            is_sponsored=spec["is_sponsored"],
            tags=spec["tags"],
            settings={"seed_source": "activity-seed"},
        )
        session.add(event)
        created += 1
        print(f"  [create] event '{spec['title']}' ({spec['event_type']}, published)")
    await session.commit()
    print(f"  [ok] {created} events seeded")


# --------------------------------------------------------------------------- #
# 7. Company reviews (published, backed by real interview/offer eligibility)   #
# --------------------------------------------------------------------------- #

# (reviewer student_key, org_slug, eligibility, overall, wlb, culture, comp, growth, interview_exp)
_REVIEW_SPECS: list[dict] = [
    {
        "reviewer": "external_student", "org": "fpt-software",
        "eligibility": review_entities.ELIG_INTERVIEW,
        "title": "Quy trình phỏng vấn chuyên nghiệp",
        "body": "Trải nghiệm phỏng vấn tại FPT Software rất rõ ràng và chuyên nghiệp. Người phỏng vấn thân thiện, câu hỏi sát với thực tế công việc. Môi trường quốc tế và có nhiều cơ hội học hỏi.",
        "pros": "Môi trường quốc tế, đãi ngộ tốt, nhiều dự án lớn.",
        "cons": "Áp lực tiến độ dự án đôi khi cao.",
        "ratings": {"overall": 4, "work_life_balance": 3, "culture_values": 4, "compensation": 4, "career_growth": 5, "interview_experience": 5},
    },
    {
        "reviewer": "vinuni_student_data", "org": "vietcombank",
        "eligibility": review_entities.ELIG_INTERVIEW,
        "title": "Ngân hàng lớn, quy trình bài bản",
        "body": "Vietcombank có quy trình tuyển dụng bài bản và minh bạch. Đội ngũ nhân sự hỗ trợ nhiệt tình. Là môi trường tốt để phát triển sự nghiệp trong ngành tài chính - ngân hàng.",
        "pros": "Thương hiệu uy tín, phúc lợi ổn định, lộ trình rõ ràng.",
        "cons": "Quy trình nội bộ khá nhiều thủ tục.",
        "ratings": {"overall": 4, "work_life_balance": 4, "culture_values": 4, "compensation": 4, "career_growth": 4, "interview_experience": 4},
    },
    {
        "reviewer": "vinuni_student_business", "org": "momo-payment",
        "eligibility": review_entities.ELIG_OFFER,
        "title": "Văn hóa startup năng động",
        "body": "MoMo có văn hóa làm việc trẻ trung, tốc độ nhanh và đề cao sáng tạo. Nhận được offer sau quy trình phỏng vấn gọn gàng. Rất phù hợp với người thích môi trường fintech.",
        "pros": "Năng động, sáng tạo, ESOP hấp dẫn, học hỏi nhanh.",
        "cons": "Nhịp độ công việc nhanh, cần khả năng thích ứng cao.",
        "ratings": {"overall": 5, "work_life_balance": 3, "culture_values": 5, "compensation": 4, "career_growth": 5, "interview_experience": 5},
    },
]


async def _application_id_for(session: AsyncSession, *, applicant_id: uuid.UUID, org_id: uuid.UUID) -> uuid.UUID | None:
    return (
        await session.execute(
            select(Application.id)
            .where(Application.applicant_id == applicant_id, Application.org_id == org_id)
            .order_by(Application.created_at)
            .limit(1)
        )
    ).scalar_one_or_none()


async def seed_company_reviews(session: AsyncSession, orgs: dict[str, Organization], users: dict[str, User]) -> None:
    print("\n[company reviews]")
    touched_orgs: set[uuid.UUID] = set()
    created = 0
    for spec in _REVIEW_SPECS:
        reviewer = users.get(spec["reviewer"])
        org = orgs.get(spec["org"])
        if reviewer is None or org is None:
            continue
        existing = (
            await session.execute(
                select(CompanyReview.id).where(
                    CompanyReview.org_id == org.id,
                    CompanyReview.reviewer_id == reviewer.id,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            print(f"  [skip] review of {org.slug} by {reviewer.email} exists")
            continue
        application_id = await _application_id_for(session, applicant_id=reviewer.id, org_id=org.id)
        review = CompanyReview(
            id=uuid.uuid4(),
            org_id=org.id,
            reviewer_id=reviewer.id,
            eligibility_type=spec["eligibility"],
            application_id=application_id,
            title=spec["title"],
            body=spec["body"],
            pros=spec["pros"],
            cons=spec["cons"],
            is_anonymous=False,
            status=review_entities.STATUS_PUBLISHED,
            published_at=NOW,
        )
        session.add(review)
        await session.flush()
        session.add(ReviewRating(review_id=review.id, **spec["ratings"]))
        touched_orgs.add(org.id)
        created += 1
        print(f"  [create] published review of {org.slug} by {reviewer.email}")
    await session.commit()
    # Recompute the denormalized company rating aggregate for each touched org.
    for org_id in touched_orgs:
        await rating_projection.recompute(session, org_id)
    await session.commit()
    print(f"  [ok] {created} reviews seeded")


# --------------------------------------------------------------------------- #
# 8. Notifications (partner-facing in-app rows; student rows come from pipeline) #
# --------------------------------------------------------------------------- #

_NOTIFICATION_SPECS: list[dict] = [
    {
        "recipient": "partner", "notif_type": "recruitment.application_received",
        "title": "Ứng viên mới ứng tuyển", "body": "Bạn có ứng viên mới cho vị trí Software Engineering Intern. Xem hồ sơ trong bảng tuyển dụng.",
        "action_url": "/partner/pipeline",
    },
    {
        "recipient": "fpt_recruiter", "notif_type": "recruitment.interview_reminder",
        "title": "Nhắc lịch phỏng vấn", "body": "Bạn có một buổi phỏng vấn kỹ thuật sắp diễn ra. Kiểm tra lịch và chuẩn bị scorecard.",
        "action_url": "/partner/interviews",
    },
    {
        "recipient": "momo_recruiter", "notif_type": "recruitment.offer_update",
        "title": "Cập nhật đề nghị tuyển dụng", "body": "Một đề nghị tuyển dụng đã được gửi tới ứng viên và đang chờ phản hồi.",
        "action_url": "/partner/offers",
    },
    {
        "recipient": "career_admin", "notif_type": "moderation.pending",
        "title": "Nội dung chờ kiểm duyệt", "body": "Có tin tuyển dụng và sự kiện mới cần được xem xét trong hàng đợi kiểm duyệt.",
        "action_url": "/university/moderation",
    },
]


async def seed_notifications(session: AsyncSession, users: dict[str, User]) -> None:
    print("\n[notifications]")
    created = 0
    for spec in _NOTIFICATION_SPECS:
        user = users.get(spec["recipient"])
        if user is None:
            continue
        exists = (
            await session.execute(
                select(Notification.id).where(
                    Notification.recipient_id == user.id,
                    Notification.notif_type == spec["notif_type"],
                    Notification.title == spec["title"],
                )
            )
        ).scalar_one_or_none()
        if exists is not None:
            continue
        session.add(
            Notification(
                id=uuid.uuid4(),
                recipient_id=user.id,
                sender_id=None,
                notif_type=spec["notif_type"],
                title=spec["title"],
                body=spec["body"],
                action_url=spec["action_url"],
                is_read=False,
                channels=["in_app"],
                delivered_at={},
            )
        )
        created += 1
        print(f"  [create] notification '{spec['title']}' -> {user.email}")
    await session.commit()
    print(f"  [ok] {created} partner/staff notifications seeded")


# --------------------------------------------------------------------------- #
# 9. Advertising (active sponsored placements on real jobs)                    #
# --------------------------------------------------------------------------- #

# (org_slug, job title substring, actor user key, creative slot)
_AD_SPECS: list[tuple[str, str, str, str]] = [
    ("momo-payment", "Kỹ sư Backend", "momo_recruiter", "homepage_hero"),
    ("fpt-software", "Senior Java Backend", "partner", "right_rail"),
]


async def seed_advertising(session: AsyncSession, orgs: dict[str, Organization], users: dict[str, User]) -> None:
    print("\n[advertising]")
    # Reuse the demo seed's real create->submit->pay->approve->creative->review
    # chain so the placement is genuinely servable (an approved creative + active
    # window), pointed at REAL sponsored jobs instead of demo targets.
    try:
        from scripts.seed_demo_marketplace import _seed_one_placement
    except Exception as exc:  # noqa: BLE001 - optional dependency for local ads
        print(f"  [skip] advertising seed unavailable: {exc}")
        return

    created = 0
    for org_slug, title_substr, actor_key, slot in _AD_SPECS:
        org = orgs.get(org_slug)
        actor = users.get(actor_key)
        if org is None or actor is None:
            continue
        job = await _find_job(session, org_id=org.id, title_substr=title_substr)
        if job is None:
            continue
        try:
            did = await _seed_one_placement(
                session, target_type="job", target_id=job.id, org_id=org.id,
                poster_id=actor.id, slot=slot, label=job.title,
            )
        except Exception as exc:  # noqa: BLE001 - ad package/storage may be absent locally
            print(f"  [warn] placement for {job.title[:30]} failed: {exc}")
            continue
        if did:
            created += 1
            print(f"  [create] sponsored placement -> {job.title[:40]} ({slot})")
        else:
            print(f"  [skip] placement for {job.title[:40]} already exists")
    await session.commit()
    print(f"  [ok] {created} sponsored placements seeded")


# --------------------------------------------------------------------------- #
# Orchestrator                                                                 #
# --------------------------------------------------------------------------- #


async def seed_activity(
    session: AsyncSession,
    *,
    orgs: dict[str, Organization],
    users: dict[str, User],
) -> None:
    """Run every activity seed in dependency order (called after the shell seed)."""

    await seed_ai_defaults(session)
    await seed_student_profiles(session, users)
    cv_selections = await seed_student_cvs(session, users)
    plan = await seed_applications(session, orgs, users, cv_selections)
    await seed_pipeline(session, plan, orgs, users)
    await seed_events(session, orgs, users)
    await seed_company_reviews(session, orgs, users)
    await seed_notifications(session, users)
    await seed_advertising(session, orgs, users)
