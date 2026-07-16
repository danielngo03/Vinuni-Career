"""Rich demo-data seed — layers a large, realistic dataset ON TOP of the base
``seed_dev`` + ``activity_seed`` output (additive + idempotent; never wipes).

What it adds, to make the platform look like it has had real activity for the
two weeks 2026-07-01 → 2026-07-11:

* ~46 more students (VinUni + external) with open-to-work profiles.
* Real uploaded-PDF CVs ingested from ``example/CV`` through the ACTUAL
  documents ingestion cascade (native text → OCR → vision-LLM for images),
  producing viewable/downloadable PDFs + structured data for CV-JD matching.
* ~40 more jobs across the existing companies (FPT-heavy), with real logos
  already handled by ``seed_dev``.
* ~200 applications, then a rich FPT/VCB/MoMo pipeline (review → interview →
  scorecard → offer), all driven through the real service layer.
* A final pass that back-dates jobs/applications/pipeline across the 2-week
  window so dashboards, activity feeds and "posted N days ago" read naturally.

Run from ``backend/``::

    uv run python scripts/seeds/rich_demo_seed.py            # all phases
    uv run python scripts/seeds/rich_demo_seed.py --phase students,jobs
    uv run python scripts/seeds/rich_demo_seed.py --students 60 --jobs 50 --apps 260

Idempotent: re-running skips students/jobs/CVs/applications it already created
(stable emails / job slugs / idempotency keys), so it is safe to re-run.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import random
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Run from backend/ so `.dev/storage` resolves and the app package imports.
_BACKEND = Path(__file__).resolve().parents[2]
os.chdir(_BACKEND)
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

# Load backend/.env, then force synchronous CV ingestion so the extraction
# cascade runs inline in THIS event loop (deterministic; no worker needed).
for _line in (_BACKEND / ".env").read_text().splitlines():
    _line = _line.strip()
    if not _line or _line.startswith("#") or "=" not in _line:
        continue
    _k, _v = _line.split("=", 1)
    os.environ.setdefault(_k.strip(), _v.strip().strip('"'))
os.environ["CV_INGESTION_ASYNC"] = "false"

from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.modules.auth.application.context import RequestContext  # noqa: E402
from app.modules.auth.domain.personas import permissions_for  # noqa: E402
from app.modules.documents.application import ingestion_service  # noqa: E402
from app.modules.opportunities.domain.models import Job  # noqa: E402
from app.modules.organization.domain.models import Membership, Organization  # noqa: E402
from app.modules.recruitment.application import apply_service  # noqa: E402
from app.modules.users.domain.models import User  # noqa: E402
from app.shared.permissions import Principal  # noqa: E402

# Reuse the shell-seed helpers (get-or-create user/identity/job).
from scripts.seed_dev import (  # noqa: E402
    _create_job,
    _get_or_create_identity,
    _get_or_create_user,
)

CTX = RequestContext(ip="127.0.0.1", user_agent="seed-dev/rich-demo")
EXAMPLE_CV_DIR = _BACKEND.parent / "example" / "CV"

# The two-week "real activity" window.
WIN_START = datetime(2026, 7, 1, 7, 0, tzinfo=UTC)
WIN_END = datetime(2026, 7, 11, 11, 0, tzinfo=UTC)
RNG = random.Random(20260711)  # reproducible spread


def _rand_dt(start: datetime = WIN_START, end: datetime = WIN_END) -> datetime:
    span = (end - start).total_seconds()
    return start + timedelta(seconds=RNG.random() * span)


# --------------------------------------------------------------------------- #
# Student roster (deterministic, realistic Vietnamese names)                   #
# --------------------------------------------------------------------------- #

_SURNAMES = [
    "Nguyễn", "Trần", "Lê", "Phạm", "Hoàng", "Huỳnh", "Phan", "Vũ", "Võ",
    "Đặng", "Bùi", "Đỗ", "Hồ", "Ngô", "Dương", "Lý", "Đinh", "Mai", "Trịnh", "Đoàn",
]
_MIDDLE = ["Minh", "Thị", "Văn", "Hoàng", "Quốc", "Gia", "Thanh", "Hữu", "Ngọc", "Anh", "Đức", "Bảo", "Khánh", "Thành"]
_GIVEN = [
    "An", "Bình", "Chi", "Dũng", "Duy", "Giang", "Hà", "Hải", "Hạnh", "Hiếu",
    "Hoa", "Huy", "Khoa", "Lan", "Linh", "Long", "Mai", "Nam", "Nga", "Ngân",
    "Nhi", "Phong", "Phúc", "Quân", "Quang", "Sơn", "Tâm", "Thảo", "Thu", "Trang",
    "Trung", "Tú", "Tuấn", "Uyên", "Vy", "Yến", "Đạt", "Kiên", "Lâm", "Vinh",
]
_MAJORS = [
    ("Khoa học Máy tính", "swe"), ("Khoa học Dữ liệu", "data"),
    ("Trí tuệ Nhân tạo", "ai"), ("Kỹ thuật Máy tính", "swe"),
    ("Công nghệ Thông tin", "swe"), ("Kỹ thuật Điện", "eng"),
    ("Quản trị Kinh doanh", "biz"), ("Tài chính - Ngân hàng", "finance"),
    ("Marketing", "marketing"), ("Kinh tế", "biz"),
    ("Logistics & Quản lý Chuỗi cung ứng", "biz"),
]
_CITIES = ["Hà Nội", "Hà Nội", "Hà Nội", "Hồ Chí Minh", "Đà Nẵng"]


def _ascii(s: str) -> str:
    from scripts.seed_dev import _slugify

    return _slugify(s)


def build_roster(n: int) -> list[dict]:
    """Deterministically build ``n`` unique student records."""
    seen: set[str] = set()
    out: list[dict] = []
    tries = 0
    while len(out) < n and tries < n * 40:
        tries += 1
        sur = RNG.choice(_SURNAMES)
        mid = RNG.choice(_MIDDLE)
        giv = RNG.choice(_GIVEN)
        full = f"{sur} {mid} {giv}"
        major, family = RNG.choice(_MAJORS)
        base = f"{_ascii(giv)}.{_ascii(sur)}"
        email = f"{base}{len(out) + 1:02d}@vinuni.edu.vn"
        if email in seen:
            continue
        seen.add(email)
        out.append({
            "email": email,
            "full_name": full,
            "major": major,
            "family": family,
            "city": RNG.choice(_CITIES),
            "grad_year": RNG.choice([2025, 2026, 2026, 2027]),
        })
    return out


def _student_principal(user: User) -> Principal:
    return Principal(user_id=user.id, persona="student", org_id=None,
                     is_superadmin=False, permissions=permissions_for("student"))


def _partner_principal(user: User, org: Organization) -> Principal:
    return Principal(user_id=user.id, persona="partner_member", org_id=org.id,
                     is_superadmin=False, permissions=frozenset({"*"}))


# --------------------------------------------------------------------------- #
# Session helper                                                               #
# --------------------------------------------------------------------------- #

def make_sessionmaker():
    s = get_settings()
    engine = create_async_engine(s.database_url, echo=False)
    return engine, sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _load_orgs(session: AsyncSession) -> dict[str, Organization]:
    rows = (await session.execute(select(Organization).where(Organization.org_type == "partner"))).scalars().all()
    return {o.slug: o for o in rows}


async def _load_users(session: AsyncSession) -> dict[str, User]:
    rows = (await session.execute(select(User))).scalars().all()
    return {u.email: u for u in rows}


async def _org_poster(session: AsyncSession, org: Organization, fallback: User) -> User:
    """A user allowed to post for ``org`` — reuse whoever posted its existing jobs."""
    poster_id = (
        await session.execute(
            select(Job.posted_by).where(Job.org_id == org.id).limit(1)
        )
    ).scalar_one_or_none()
    if poster_id is not None:
        u = (await session.execute(select(User).where(User.id == poster_id))).scalar_one_or_none()
        if u is not None:
            return u
    mem_uid = (
        await session.execute(select(Membership.user_id).where(Membership.org_id == org.id).limit(1))
    ).scalar_one_or_none()
    if mem_uid is not None:
        u = (await session.execute(select(User).where(User.id == mem_uid))).scalar_one_or_none()
        if u is not None:
            return u
    return fallback


# --------------------------------------------------------------------------- #
# Job catalog                                                                  #
# --------------------------------------------------------------------------- #

# family -> [(title, skills, (salary_min_M, salary_max_M))]  (salary in million VND / month)
_ROLE_CATALOG: dict[str, list[tuple[str, list[str], tuple[int, int]]]] = {
    "swe": [
        ("Kỹ sư Backend (Python/Java)", ["Python", "Java", "PostgreSQL", "REST APIs", "Docker", "Microservices"], (18, 40)),
        ("Kỹ sư Frontend (React)", ["JavaScript", "TypeScript", "React", "CSS", "Redux"], (16, 36)),
        ("Fullstack Developer", ["JavaScript", "TypeScript", "React", "Node.js", "PostgreSQL"], (18, 38)),
        ("Mobile Developer (Flutter)", ["Flutter", "Dart", "REST APIs", "Firebase"], (16, 34)),
        ("iOS Developer (Swift)", ["Swift", "SwiftUI", "iOS", "REST APIs"], (18, 38)),
        ("DevOps Engineer", ["Docker", "Kubernetes", "CI/CD", "AWS", "Terraform", "Linux"], (22, 45)),
    ],
    "qa": [
        ("QA Automation Engineer", ["Selenium", "Python", "Test Automation", "CI/CD", "Cypress"], (15, 32)),
        ("Manual QA Engineer", ["Test Cases", "JIRA", "SQL", "API Testing"], (12, 24)),
    ],
    "data": [
        ("Data Analyst", ["SQL", "Python", "Power BI", "Excel", "Tableau"], (14, 28)),
        ("Data Engineer", ["Python", "SQL", "Spark", "Airflow", "ETL"], (20, 42)),
        ("Machine Learning Engineer", ["Python", "PyTorch", "TensorFlow", "Machine Learning", "SQL"], (22, 48)),
        ("BI Analyst", ["SQL", "Power BI", "Tableau", "Data Analysis"], (14, 28)),
    ],
    "ai": [
        ("AI Engineer", ["Python", "PyTorch", "LLM", "NLP", "Machine Learning"], (24, 50)),
        ("Computer Vision Engineer", ["Python", "OpenCV", "PyTorch", "Deep Learning"], (22, 46)),
    ],
    "biz": [
        ("Business Analyst", ["Business Analysis", "SQL", "Excel", "Agile", "Communication"], (14, 28)),
        ("Product Manager", ["Product Management", "Agile", "Roadmap", "Analytics"], (25, 50)),
        ("Business Development Executive", ["Business Development", "Communication", "Negotiation", "CRM"], (14, 30)),
        ("Operations Associate", ["Operations", "Excel", "Process Improvement", "Communication"], (12, 24)),
    ],
    "finance": [
        ("Financial Analyst", ["Financial Analysis", "Excel", "Accounting", "Valuation"], (16, 32)),
        ("Investment Analyst", ["Financial Modeling", "Valuation", "Excel", "Equity Research"], (18, 40)),
        ("Risk Analyst", ["Risk Management", "SQL", "Excel", "Statistics"], (16, 34)),
    ],
    "marketing": [
        ("Digital Marketing Specialist", ["SEO", "Google Ads", "Content Marketing", "Analytics"], (12, 26)),
        ("Growth Marketing Associate", ["Growth", "Analytics", "A/B Testing", "SEO"], (14, 30)),
    ],
    "eng": [
        ("Kỹ sư Điện - Điện tử", ["Electrical", "Embedded", "C", "PCB Design"], (16, 34)),
        ("Kỹ sư Cơ khí", ["Mechanical", "CAD", "SolidWorks", "Manufacturing"], (15, 32)),
    ],
}

# company slug -> (preferred families, number of NEW jobs to create)
_COMPANY_PLAN: dict[str, tuple[list[str], int]] = {
    "fpt-software": (["swe", "data", "ai", "qa"], 16),
    "vietcombank": (["finance", "data", "biz"], 5),
    "tiki-corporation": (["swe", "data", "biz", "marketing"], 5),
    "momo-payment": (["swe", "data", "biz", "finance"], 5),
    "kms-technology": (["swe", "qa"], 3),
    "kpmg-vietnam": (["finance", "biz"], 2),
    "vinfast": (["eng", "swe", "data"], 3),
    "vinmec": (["biz", "data"], 1),
    "ssi-securities": (["finance", "data"], 2),
    "axon-active": (["swe", "qa"], 2),
}

_SENIORITY = [("", 0, "vi"), ("Senior ", 4, "en"), ("Junior ", 1, "vi"), ("", 2, "vi")]


def _jd(title: str, company: str, skills: list[str], family: str) -> tuple[str, str, str]:
    sk = ", ".join(skills)
    desc = (
        f"{company} đang tuyển vị trí {title}. Bạn sẽ tham gia vào các dự án thực tế, "
        f"làm việc cùng đội ngũ giàu kinh nghiệm và đóng góp trực tiếp vào sản phẩm phục vụ "
        f"hàng triệu người dùng. Công việc chính bao gồm phân tích yêu cầu, thiết kế và "
        f"triển khai giải pháp, phối hợp cùng các nhóm liên quan và liên tục cải tiến chất lượng.\n\n"
        f"Trách nhiệm chính:\n"
        f"- Tham gia toàn bộ vòng đời sản phẩm từ phân tích tới triển khai và vận hành.\n"
        f"- Ứng dụng {sk} để xây dựng giải pháp hiệu quả, đáng tin cậy.\n"
        f"- Phối hợp với các nhóm sản phẩm, kỹ thuật và vận hành theo mô hình Agile.\n"
        f"- Chủ động đề xuất cải tiến và chia sẻ kiến thức trong nhóm."
    )
    req = (
        f"Yêu cầu:\n"
        f"- Nền tảng vững về {sk}.\n"
        f"- Tư duy giải quyết vấn đề tốt, khả năng tự học và làm việc nhóm.\n"
        f"- Giao tiếp tiếng Anh cơ bản; ưu tiên ứng viên có kinh nghiệm dự án thực tế.\n"
        f"- Sinh viên năm cuối hoặc mới tốt nghiệp đều được khuyến khích ứng tuyển."
    )
    ben = (
        "Quyền lợi:\n"
        "- Lương thưởng cạnh tranh, xét tăng lương định kỳ.\n"
        "- Bảo hiểm đầy đủ, chăm sóc sức khỏe, 15+ ngày phép/năm.\n"
        "- Môi trường trẻ trung, lộ trình thăng tiến rõ ràng, ngân sách đào tạo.\n"
        "- Laptop cấp phát, mô hình làm việc hybrid linh hoạt."
    )
    return desc, req, ben


def _plan_jobs_for(slug: str, families: list[str], count: int) -> list[dict]:
    """Deterministically pick ``count`` role specs for a company."""
    specs: list[dict] = []
    fam_cycle = 0
    for _ in range(count):
        family = families[fam_cycle % len(families)]
        fam_cycle += 1
        roles = _ROLE_CATALOG[family]
        base_title, skills, (smin, smax) = roles[RNG.randrange(len(roles))]
        pref, exp, lang = _SENIORITY[RNG.randrange(len(_SENIORITY))]
        is_intern = family in {"swe", "data", "biz", "qa", "marketing"} and RNG.random() < 0.22
        if is_intern:
            title = f"Thực tập sinh {base_title}"
            emp = "internship"
            smin_v, smax_v = 5, 12
            exp = 0
        else:
            title = f"{pref}{base_title}".strip()
            emp = "full_time"
            bump = exp * 3
            smin_v, smax_v = smin + bump, smax + bump
        specs.append({
            "title": title,
            "skills": skills,
            "family": family,
            "employment_type": emp,
            "salary_min": smin_v * 1_000_000,
            "salary_max": smax_v * 1_000_000,
            "experience_min_years": exp,
            "language_code": lang,
            "location_type": RNG.choice(["onsite", "onsite", "hybrid", "remote"]),
        })
    return specs


# --------------------------------------------------------------------------- #
# Phase: students                                                             #
# --------------------------------------------------------------------------- #

async def phase_students(Session, n: int) -> list[uuid.UUID]:
    from app.modules.student_profiles.application import profile_service

    print(f"\n[students] target +{n}")
    roster = build_roster(n)
    created: list[uuid.UUID] = []
    async with Session() as session:
        for rec in roster:
            user = await _get_or_create_user(
                session, email=rec["email"], full_name=rec["full_name"],
                preferred_language="vi",
            )
            await _get_or_create_identity(session, user=user, persona="student")
            created.append(user.id)
        await session.commit()

    # Profiles (services own their commits) — separate session.
    async with Session() as session:
        users = {u.id: u for u in (await session.execute(select(User).where(User.id.in_(created)))).scalars().all()}
        for rec in roster:
            user = next((u for u in users.values() if u.email == rec["email"]), None)
            if user is None:
                continue
            principal = _student_principal(user)
            await profile_service.get_my_profile(session, principal=principal)
            await profile_service.update_my_profile(
                session, principal=principal,
                payload={
                    "phone": f"+84 9{RNG.randrange(10, 99)} {RNG.randrange(100, 999)} {RNG.randrange(1000, 9999)}",
                    "location_city": rec["city"], "location_country": "Vietnam",
                    "is_open_to_work": RNG.random() < 0.85,
                    "profile_visibility": RNG.choice(["public", "public", "vinuni_only"]),
                    "show_email": "invited", "show_phone": "invited",
                },
                ctx=CTX,
            )
    print(f"[students] ensured {len(created)}")
    return created


# --------------------------------------------------------------------------- #
# Phase: jobs                                                                 #
# --------------------------------------------------------------------------- #

async def phase_jobs(Session) -> list[uuid.UUID]:
    print("\n[jobs] creating company jobs")
    new_ids: list[uuid.UUID] = []
    async with Session() as session:
        orgs = await _load_orgs(session)
        users = await _load_users(session)
        fallback = users.get("partner@gmail.com")
        for slug, (families, count) in _COMPANY_PLAN.items():
            org = orgs.get(slug)
            if org is None:
                print(f"  [warn] org {slug} missing; skip")
                continue
            poster = await _org_poster(session, org, fallback)
            if poster is None:
                continue
            for spec in _plan_jobs_for(slug, families, count):
                desc, req, ben = _jd(spec["title"], org.display_name, spec["skills"], spec["family"])
                # Skip if a same-title active job already exists for this org (idempotent-ish).
                exists = (
                    await session.execute(
                        select(Job.id).where(Job.org_id == org.id, Job.title == spec["title"], Job.deleted_at.is_(None))
                    )
                ).scalar_one_or_none()
                if exists is not None:
                    continue
                job = await _create_job(
                    session, org=org, posted_by=poster, title=spec["title"],
                    description=desc, requirements=req, benefits=ben,
                    employment_type=spec["employment_type"], location_type=spec["location_type"],
                    location_city=RNG.choice(_CITIES), required_skills=spec["skills"][:4],
                    preferred_skills=spec["skills"][4:], experience_min_years=spec["experience_min_years"],
                    salary_min=spec["salary_min"], salary_max=spec["salary_max"],
                    language_code=spec["language_code"], deadline_days=RNG.choice([20, 30, 45, 60]),
                )
                new_ids.append(job.id)
            print(f"  [jobs] {slug}: +{count} planned")
        await session.commit()
    print(f"[jobs] created {len(new_ids)} new jobs")
    return new_ids


# --------------------------------------------------------------------------- #
# Phase: uploaded CVs (real PDFs through the ingestion cascade)               #
# --------------------------------------------------------------------------- #

def _example_cv_files() -> list[Path]:
    files = sorted(EXAMPLE_CV_DIR.glob("CV-*"))
    return [f for f in files if f.suffix.lower() in (".pdf", ".jpg", ".jpeg", ".png")]


async def phase_cvs(Session, student_ids: list[uuid.UUID], max_students: int) -> dict[str, dict]:
    """Ingest real example CV files for students; returns {user_id_hex: cv_selection}."""
    files = _example_cv_files()
    print(f"\n[cvs] {len(files)} example files; ingesting for up to {max_students} students")
    selections: dict[str, dict] = {}
    async with Session() as session:
        students = (await session.execute(select(User).where(User.id.in_(student_ids)))).scalars().all()
    targets = students[:max_students]
    for idx, user in enumerate(targets):
        principal = _student_principal(user)
        n_cv = 1 if RNG.random() < 0.7 else 2
        first_sel = None
        for j in range(n_cv):
            f = files[(idx * 2 + j) % len(files)]
            data = f.read_bytes()
            ct = "application/pdf" if f.suffix.lower() == ".pdf" else "image/jpeg"
            idem = f"rich-cv-{user.id}-{f.name}"
            try:
                async with Session() as session:
                    up = await ingestion_service.create_upload(
                        session, principal=principal, filename=f.name, data=data,
                        content_type=ct, idempotency_key=idem, ctx=CTX)
                    await session.commit()
                    doc_id = uuid.UUID(up["document_id"])
                    ing = await ingestion_service.start_ingestion(
                        session, principal=principal, document_id=doc_id, ctx=CTX,
                        idempotency_key=idem)
                    status = ing.get("status")
                    if status not in ("ready", "needs_review"):
                        print(f"  [cv] {user.email} {f.name}: status={status}; skip import")
                        continue
                    cv = await ingestion_service.import_ingestion(
                        session, principal=principal, ingestion_id=uuid.UUID(ing["ingestion_id"]),
                        payload={"title": f"CV — {user.full_name}", "fact_confirmation": True}, ctx=CTX)
                    await session.commit()
                    sel = {"type": "builder_cv", "cv_profile_id": cv["id"],
                           "cv_version_id": cv.get("current_version_id"), "uploaded_document_id": None}
                    if first_sel is None and sel["cv_version_id"]:
                        first_sel = sel
            except Exception as exc:  # noqa: BLE001 — a bad file must not stop the seed
                print(f"  [cv] {user.email} {f.name}: ERROR {type(exc).__name__}: {str(exc)[:80]}")
        if first_sel is not None:
            selections[user.id.hex] = first_sel
        if (idx + 1) % 10 == 0:
            print(f"  [cv] progress {idx + 1}/{len(targets)}")
    print(f"[cvs] students with an uploaded CV: {len(selections)}")
    return selections


# --------------------------------------------------------------------------- #
# Phase: applications                                                         #
# --------------------------------------------------------------------------- #

# FPT gets the most applicant volume; others a realistic share.
_APPLY_WEIGHT = {"fpt-software": 6, "vietcombank": 3, "momo-payment": 3,
                 "tiki-corporation": 3, "kms-technology": 2, "vinfast": 2}


async def phase_applications(Session, cv_selections: dict[str, dict], target: int) -> list[dict]:
    print(f"\n[applications] target ~{target}")
    entries: list[dict] = []
    async with Session() as session:
        orgs = {o.id: o for o in (await session.execute(select(Organization))).scalars().all()}
        jobs = (
            await session.execute(
                select(Job).where(Job.status == "active", Job.deleted_at.is_(None))
            )
        ).scalars().all()
    # Weighted job pool by owning org.
    pool: list[Job] = []
    for j in jobs:
        slug = orgs[j.org_id].slug if j.org_id in orgs else ""
        pool.extend([j] * _APPLY_WEIGHT.get(slug, 1))
    if not pool:
        print("  [warn] no active jobs; skip")
        return entries

    student_ids = list(cv_selections.keys())
    RNG.shuffle(student_ids)
    made = 0
    for uid_hex in student_ids:
        if made >= target:
            break
        selection = cv_selections[uid_hex]
        user_id = uuid.UUID(uid_hex)
        k = RNG.randint(2, 6)
        chosen: dict[uuid.UUID, Job] = {}
        for _ in range(k * 3):
            if len(chosen) >= k:
                break
            j = RNG.choice(pool)
            chosen.setdefault(j.id, j)
        async with Session() as session:
            user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
            if user is None:
                continue
            principal = _student_principal(user)
            for job in chosen.values():
                if made >= target:
                    break
                idem = f"rich-apply-{user_id}-{job.id}"
                try:
                    result = await apply_service.apply_to_job(
                        session, principal=principal,
                        payload={
                            "job_id": job.id, "cv_selection": selection,
                            "cover_letter": "Em rất mong muốn được ứng tuyển và đóng góp cho vị trí này.",
                            "screening_answers": {}, "is_anonymous": False,
                            "idempotency_key": idem,
                        }, ctx=CTX,
                    )
                    slug = orgs[job.org_id].slug if job.org_id in orgs else ""
                    entries.append({
                        "application_id": uuid.UUID(result["id"]), "org_slug": slug,
                        "user_id": user_id, "job_title": job.title,
                    })
                    made += 1
                except Exception as exc:  # noqa: BLE001
                    msg = str(exc)[:60]
                    if "already" not in msg.lower():
                        print(f"  [apply] {user.email} -> {job.title[:30]}: {type(exc).__name__} {msg}")
        if made % 25 == 0 and made:
            print(f"  [apply] progress {made}/{target}")
    print(f"[applications] created {len(entries)}")
    return entries


# --------------------------------------------------------------------------- #
# Phase: pipeline progression (FPT/VCB/MoMo)                                   #
# --------------------------------------------------------------------------- #

_PARTNER_ACTOR_EMAIL = {
    "fpt-software": "partner@gmail.com",
    "vietcombank": "recruiter.vcb@example.com",
    "momo-payment": "recruiter.momo@example.com",
}
# progression target distribution (per eligible application)
_TARGETS = (["reviewed"] * 5 + ["interview"] * 4 + ["offer_sent"] * 2
            + ["offer_accepted"] * 2 + ["rejected"] * 3 + ["applied"] * 4)
_ORDER = {"applied": 0, "reviewed": 1, "interview": 2, "offer_sent": 3, "offer_accepted": 4}


async def _progress(session, *, app_id, target, actor, student, job_title):
    from app.modules.recruitment.application import (
        decision_service, interview_service, offer_service, scorecard_service, stage_service,
    )
    from app.modules.recruitment.domain import offer as offer_domain
    from app.modules.recruitment.domain import scorecard as scorecard_domain

    if target == "rejected":
        await decision_service.review_application(session, principal=actor, application_id=app_id, ctx=CTX)
        try:
            await decision_service.reject_application(
                session, principal=actor, application_id=app_id,
                reason="not_qualified", note="Hồ sơ chưa phù hợp với yêu cầu hiện tại.", ctx=CTX)
        except Exception:  # noqa: BLE001 — reject signature/availability varies; leave under_review
            pass
        return
    order = _ORDER[target]
    await decision_service.review_application(session, principal=actor, application_id=app_id, ctx=CTX)
    if order < _ORDER["interview"]:
        return
    await stage_service.advance_application_stage(
        session, principal=actor, application_id=app_id, idempotency_key=f"rich-adv2-{app_id}", ctx=CTX)
    await interview_service.schedule_interview(
        session, principal=actor, application_id=app_id, mode="online",
        scheduled_at=WIN_END + timedelta(days=RNG.randint(1, 6)), assignee_ids=[actor.user_id],
        duration_minutes=60, meeting_link="https://meet.google.com/rich-interview",
        title="Vòng phỏng vấn", ctx=CTX)
    await scorecard_service.submit_scorecard(
        session, principal=actor, application_id=app_id, recommendation="yes",
        scores=[{"criterion_key": kk, "score": 4} for kk in scorecard_domain.DEFAULT_CRITERION_KEYS],
        comment="Ứng viên thể hiện tốt, phù hợp với vị trí.", ctx=CTX)
    if order < _ORDER["offer_sent"]:
        return
    await stage_service.advance_application_stage(
        session, principal=actor, application_id=app_id, idempotency_key=f"rich-adv3-{app_id}", ctx=CTX)
    offer = await offer_service.create_offer(
        session, principal=actor, application_id=app_id, position_title=job_title,
        expiry_date=WIN_END + timedelta(days=14),
        salary_amount=8_000_000 if "Thực tập" in job_title else 25_000_000,
        salary_currency=offer_domain.DEFAULT_CURRENCY, salary_period=offer_domain.DEFAULT_PERIOD,
        benefits_summary="Thưởng hiệu suất, bảo hiểm sức khỏe, đào tạo.", ctx=CTX)
    offer_id = uuid.UUID(offer["id"])
    await offer_service.submit_offer(session, principal=actor, offer_id=offer_id, ctx=CTX)
    await offer_service.approve_offer(
        session, principal=actor, offer_id=offer_id, decision=offer_domain.APPROVE_DECISION, ctx=CTX)
    await offer_service.send_offer(session, principal=actor, offer_id=offer_id, ctx=CTX)
    if order < _ORDER["offer_accepted"]:
        return
    await offer_service.respond_offer(
        session, principal=student, offer_id=offer_id, decision=offer_domain.RESPOND_ACCEPTED,
        idempotency_key=f"rich-respond-{offer_id}", ctx=CTX)


async def phase_pipeline(Session, entries: list[dict]) -> None:
    print("\n[pipeline] progressing FPT/VCB/MoMo applications")
    async with Session() as session:
        users = await _load_users(session)
        orgs = await _load_orgs(session)
    n = 0
    for e in entries:
        actor_email = _PARTNER_ACTOR_EMAIL.get(e["org_slug"])
        if actor_email is None or actor_email not in users:
            continue
        target = RNG.choice(_TARGETS)
        if target == "applied":
            continue
        org = orgs.get(e["org_slug"])
        actor_user = users[actor_email]
        student_user = next((u for u in users.values() if u.id == e["user_id"]), None)
        if org is None or student_user is None:
            continue
        actor = _partner_principal(actor_user, org)
        student = _student_principal(student_user)
        async with Session() as session:
            try:
                await _progress(session, app_id=e["application_id"], target=target,
                                actor=actor, student=student, job_title=e["job_title"])
                n += 1
            except Exception as exc:  # noqa: BLE001
                print(f"  [pipe] {e['org_slug']} {target}: {type(exc).__name__} {str(exc)[:70]}")
    print(f"[pipeline] progressed {n} applications")


# --------------------------------------------------------------------------- #
# Phase: back-date across the 2-week window                                   #
# --------------------------------------------------------------------------- #

async def phase_backdate() -> None:
    print("\n[backdate] spreading dates 2026-07-01 → 2026-07-11")
    import asyncpg

    dsn = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
    c = await asyncpg.connect(dsn)
    ws, we = WIN_START, WIN_END
    jobs_end = we - timedelta(days=2)
    reg_start = ws - timedelta(days=20)
    # 1) Jobs — publish spread across the window.
    await c.execute(
        """
        update jobs set published_at = $1::timestamptz + random() * ($2::timestamptz - $1::timestamptz)
        where status = 'active' and deleted_at is null
        """, ws, jobs_end)
    await c.execute(
        """
        update jobs set created_at = published_at,
            submitted_at = published_at - interval '2 days',
            approved_at = published_at, updated_at = published_at,
            application_deadline = published_at + interval '30 days' + (random() * interval '30 days')
        where status = 'active' and deleted_at is null and published_at is not null
        """)
    # 2) Applications — applied after the job was published, within the window.
    await c.execute(
        """
        update applications a
        set applied_at = j.published_at + random() * ($1::timestamptz - j.published_at)
        from jobs j
        where a.job_id = j.id and j.published_at is not null and j.published_at < $1::timestamptz
        """, we)
    await c.execute(
        "update applications set created_at = applied_at, last_status_at = applied_at, updated_at = applied_at where applied_at is not null")
    # 3) Students — registered over the last few weeks (some before the window).
    #    Split so email_verified/updated reference the NEWLY-set created_at (and to
    #    avoid the ambiguous `created_at` from the identities join).
    await c.execute(
        """
        update users u set created_at = $1::timestamptz + random() * ($2::timestamptz - $1::timestamptz)
        from identities i
        where i.user_id = u.id and i.persona = 'student'
        """, reg_start, we)
    await c.execute(
        """
        update users set email_verified_at = created_at + interval '11 minutes', updated_at = created_at
        where id in (select user_id from identities where persona = 'student')
        """)
    # 4) Interviews / offers / timeline — a few days after the application.
    await c.execute(
        """
        update interviews iv set created_at = least($1::timestamptz, a.applied_at + (random() * interval '3 days'))
        from applications a where iv.application_id = a.id and a.applied_at is not null
        """, we)
    await c.execute(
        """
        update offers o set created_at = least($1::timestamptz, a.applied_at + interval '4 days' + (random() * interval '3 days'))
        from applications a where o.application_id = a.id and a.applied_at is not null
        """, we)
    await c.execute(
        """
        update application_timeline_events te
        set occurred_at = least($1::timestamptz, a.applied_at + (random() * interval '4 days'))
        from applications a where te.application_id = a.id and a.applied_at is not null
        """, we)
    await c.close()
    print("[backdate] done")


# --------------------------------------------------------------------------- #
# Load helpers for standalone phases                                          #
# --------------------------------------------------------------------------- #

async def _all_student_ids(Session) -> list[uuid.UUID]:
    from app.modules.users.domain.models import Identity
    async with Session() as session:
        rows = (
            await session.execute(
                select(Identity.user_id).where(Identity.persona == "student")
            )
        ).scalars().all()
    return list(dict.fromkeys(rows))


async def _load_cv_selections(Session, student_ids: list[uuid.UUID]) -> dict[str, dict]:
    """Latest ready CV per student → an apply selection."""
    from app.modules.documents.domain.models import CvProfile
    sel: dict[str, dict] = {}
    async with Session() as session:
        for uid in student_ids:
            cv = (
                await session.execute(
                    select(CvProfile).where(
                        CvProfile.user_id == uid, CvProfile.status == "ready",
                        CvProfile.deleted_at.is_(None),
                    ).order_by(CvProfile.updated_at.desc()).limit(1)
                )
            ).scalar_one_or_none()
            if cv is None:
                continue
            user = (await session.execute(select(User).where(User.id == uid))).scalar_one()
            from app.modules.documents.application import cv_service
            detail = await cv_service.get_cv(session, principal=_student_principal(user), cv_id=cv.id)
            if detail.get("current_version_id"):
                sel[uid.hex] = {"type": "builder_cv", "cv_profile_id": detail["id"],
                                "cv_version_id": detail["current_version_id"], "uploaded_document_id": None}
    return sel


# --------------------------------------------------------------------------- #
# Main                                                                         #
# --------------------------------------------------------------------------- #

async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", default="all",
                    help="comma list: students,jobs,cvs,apps,pipeline,backdate  (default all)")
    ap.add_argument("--students", type=int, default=46)
    ap.add_argument("--apps", type=int, default=200)
    ap.add_argument("--cv-students", type=int, default=44)
    args = ap.parse_args()
    phases = {p.strip() for p in args.phase.split(",")} if args.phase != "all" else {
        "students", "jobs", "cvs", "apps", "pipeline", "backdate"}

    engine, Session = make_sessionmaker()
    student_ids: list[uuid.UUID] = []
    cv_selections: dict[str, dict] = {}
    app_entries: list[dict] = []
    try:
        if "students" in phases:
            student_ids = await phase_students(Session, args.students)
        if "jobs" in phases:
            await phase_jobs(Session)
        if "cvs" in phases:
            if not student_ids:
                student_ids = await _all_student_ids(Session)
            cv_selections = await phase_cvs(Session, student_ids, args.cv_students)
        if "apps" in phases:
            if not cv_selections:
                if not student_ids:
                    student_ids = await _all_student_ids(Session)
                cv_selections = await _load_cv_selections(Session, student_ids)
            app_entries = await phase_applications(Session, cv_selections, args.apps)
        if "pipeline" in phases:
            if not app_entries:
                print("[pipeline] no in-memory apps; loading recent submitted from DB")
                async with Session() as session:
                    orgs = {o.id: o.slug for o in (await session.execute(select(Organization))).scalars().all()}
                    from app.modules.recruitment.domain.models import Application
                    rows = (await session.execute(
                        select(Application).where(Application.status == "submitted"))).scalars().all()
                    app_entries = [{"application_id": a.id, "org_slug": orgs.get(a.org_id, ""),
                                    "user_id": a.applicant_id, "job_title": ""} for a in rows]
            await phase_pipeline(Session, app_entries)
        if "backdate" in phases:
            await phase_backdate()
    finally:
        await engine.dispose()

    # Final summary.
    engine2, Session2 = make_sessionmaker()
    async with Session2() as session:
        from app.modules.users.domain.models import Identity
        from app.modules.documents.domain.models import CvProfile
        from app.modules.recruitment.domain.models import Application
        n_students = (await session.execute(select(func.count()).select_from(Identity).where(Identity.persona == "student"))).scalar()
        n_jobs = (await session.execute(select(func.count()).select_from(Job).where(Job.status == "active"))).scalar()
        n_cv = (await session.execute(select(func.count()).select_from(CvProfile).where(CvProfile.status == "ready"))).scalar()
        n_apps = (await session.execute(select(func.count()).select_from(Application))).scalar()
    await engine2.dispose()
    print(f"\n===== TOTALS =====\nstudents(identity)={n_students}  active_jobs={n_jobs}  ready_cvs={n_cv}  applications={n_apps}")


if __name__ == "__main__":
    asyncio.run(main())
