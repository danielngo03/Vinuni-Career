# ruff: noqa: E501
"""Enrich development marketplace data with realistic linked metadata.

This module intentionally runs after the base dev seed.  The base seed keeps the
long-form JD copy and official-logo crawling, while this layer links records to
taxonomy/location tables and adds structured candidate requirements.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from app.modules.opportunities.domain import lifecycle
from app.modules.opportunities.domain.industry_models import Industry
from app.modules.opportunities.domain.models import Job
from app.modules.organization.domain.catalog import slugify
from app.modules.organization.domain.models import Organization
from app.modules.users.domain.models import User
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

NOW = datetime.now(tz=UTC)

PROVINCES: dict[str, tuple[str, str]] = {
    "hanoi": ("01", "Hà Nội"),
    "haiphong": ("05", "Hải Phòng"),
    "danang": ("12", "Đà Nẵng"),
    "hcmc": ("30", "Hồ Chí Minh"),
    "cantho": ("32", "Cần Thơ"),
}

ORG_INDUSTRIES: dict[str, str] = {
    "fpt-software": "software-development",
    "vietcombank": "banking",
    "tiki-corporation": "online-sales",
    "kms-technology": "software-development",
    "momo-payment": "digital-payments",
    "kpmg-vietnam": "management-consulting",
    "vinfast": "ev-technology",
    "vinmec": "hospital-administration",
    "ssi-securities": "equity-research",
    "axon-active": "software-development",
    "vietnam-airlines": "air-freight",
    "the-coffee-house": "food-beverage",
}

JOB_LINKS: dict[str, dict[str, Any]] = {
    "Senior Java Backend Developer": {
        "industry": "backend-development",
        "province": "hanoi",
        "seniority": "senior",
        "requirements": {
            "education": {"mode": "preferred", "values": ["bachelor"]},
            "age": {"mode": "not_required"},
            "gender": {"mode": "not_required"},
            "nationalities": {"mode": "not_required"},
            "languages": [
                {"language": "English", "proficiency": "Working proficiency", "required": True}
            ],
            "work_authorization": {"mode": "required", "values": ["Vietnam"]},
        },
    },
    "React Native Mobile Developer": {
        "industry": "mobile-development",
        "province": "hanoi",
        "seniority": "middle",
    },
    "Software Engineering Intern (Backend / Python)": {
        "industry": "backend-development",
        "province": "hanoi",
        "seniority": "intern",
        "requirements": {
            "education": {"mode": "required", "values": ["final-year student"]},
            "age": {"mode": "not_required"},
            "gender": {"mode": "not_required"},
            "nationalities": {"mode": "not_required"},
        },
    },
    "Business Development Intern — Merchant Partnership": {
        "industry": "partnership-development",
        "province": "hcmc",
        "seniority": "intern",
    },
    "Data & Analytics Manager — Advisory": {
        "industry": "business-intelligence",
        "province": "hanoi",
        "seniority": "manager",
    },
    "Battery Management System (BMS) Software Engineer": {
        "industry": "embedded-systems",
        "province": "haiphong",
        "seniority": "middle",
    },
    "Quantitative Analyst — Derivatives & Structured Products": {
        "industry": "equity-research",
        "province": "hcmc",
        "seniority": "junior",
    },
    "Software Engineer — Platform & Internal Tools": {
        "industry": "backend-development",
        "province": "hcmc",
        "seniority": "middle",
    },
}

ADDITIONAL_JOBS: list[dict[str, Any]] = [
    {
        "org": "vietcombank",
        "title": "Chuyên viên Phân tích Dữ liệu (Data Analyst)",
        "industry": "data-analyst",
        "province": "hanoi",
        "employment_type": "full_time",
        "location_type": "onsite",
        "skills": ["SQL", "Power BI", "Python", "Banking Analytics"],
        "preferred": ["Credit Risk", "ETL", "Data Warehouse"],
        "experience": (1, 3),
        "salary": (18_000_000, 32_000_000, True),
        "seniority": "junior",
        "deadline_days": 28,
        "description": "Phân tích dữ liệu khách hàng, giao dịch và hành vi sử dụng sản phẩm số để hỗ trợ các đơn vị kinh doanh ra quyết định.",
        "requirements": "Có nền tảng thống kê, SQL tốt; ưu tiên ứng viên từng làm dữ liệu trong ngân hàng hoặc fintech.",
        "benefits": "Lương thưởng cạnh tranh, bảo hiểm đầy đủ, lộ trình phát triển trong khối ngân hàng số.",
    },
    {
        "org": "vietnam-airlines",
        "title": "Chuyên viên Hệ thống Bán vé & Đặt chỗ (GDS / NDC)",
        "industry": "business-analyst-it",
        "province": "hanoi",
        "employment_type": "full_time",
        "location_type": "hybrid",
        "skills": ["Business Analysis", "GDS", "API", "SQL"],
        "preferred": ["Airline Retailing", "NDC", "Amadeus"],
        "experience": (2, 5),
        "salary": (20_000_000, 38_000_000, True),
        "seniority": "middle",
        "deadline_days": 35,
        "description": "Làm việc cùng khối thương mại và CNTT để cải tiến hệ thống đặt chỗ, bán vé và tích hợp kênh phân phối.",
        "requirements": "Hiểu quy trình bán vé/đặt chỗ; có khả năng viết tài liệu nghiệp vụ và phối hợp với đội kỹ thuật.",
        "benefits": "Vé ưu đãi nhân viên, môi trường hàng không chuyên nghiệp, cơ hội tham gia dự án chuyển đổi số.",
    },
    {
        "org": "vinmec",
        "title": "Chuyên viên Công nghệ Y tế (Healthcare IT Integration)",
        "industry": "hospital-administration",
        "province": "hanoi",
        "employment_type": "full_time",
        "location_type": "onsite",
        "skills": ["Healthcare IT", "HL7", "SQL", "System Integration"],
        "preferred": ["FHIR", "PACS", "HIS/LIS"],
        "experience": (2, 4),
        "salary": (18_000_000, 35_000_000, True),
        "seniority": "middle",
        "deadline_days": 30,
        "description": "Vận hành và tích hợp các hệ thống bệnh viện số, đảm bảo luồng dữ liệu y tế chính xác giữa HIS, LIS và PACS.",
        "requirements": "Có kinh nghiệm tích hợp hệ thống; ưu tiên hiểu chuẩn dữ liệu y tế.",
        "benefits": "Chế độ Vingroup, bảo hiểm sức khỏe, đào tạo chuyên sâu về công nghệ y tế.",
    },
    {
        "org": "momo-payment",
        "title": "Kỹ sư Backend — Hệ thống Thanh toán (Go/Java)",
        "industry": "backend-development",
        "province": "hcmc",
        "employment_type": "full_time",
        "location_type": "hybrid",
        "skills": ["Go", "Java", "Kafka", "Distributed Systems"],
        "preferred": ["Payment Gateway", "Fraud Detection", "Kubernetes"],
        "experience": (3, 6),
        "salary": (30_000_000, 60_000_000, True),
        "seniority": "senior",
        "deadline_days": 24,
        "description": "Xây dựng dịch vụ thanh toán có độ sẵn sàng cao, xử lý giao dịch thời gian thực cho hàng chục triệu người dùng.",
        "requirements": "Nắm chắc backend performance, event-driven architecture và an toàn giao dịch.",
        "benefits": "ESOP theo chính sách, ngân sách học tập, môi trường fintech tốc độ cao.",
    },
    {
        "org": "tiki-corporation",
        "title": "Product Designer (UX/UI) — Consumer App",
        "industry": "product-management",
        "province": "hcmc",
        "employment_type": "full_time",
        "location_type": "hybrid",
        "skills": ["UX Research", "Figma", "Design Systems", "Mobile UX"],
        "preferred": ["E-commerce", "Experimentation", "Prototyping"],
        "experience": (2, 5),
        "salary": (None, 50_000_000, True),
        "seniority": "middle",
        "deadline_days": 26,
        "description": "Thiết kế trải nghiệm mua sắm trên app, tối ưu funnel tìm kiếm, PDP, checkout và loyalty.",
        "requirements": "Portfolio thể hiện tư duy sản phẩm, khả năng làm việc với PM/Engineer và dữ liệu hành vi.",
        "benefits": "Gói phúc lợi thương mại điện tử, thử nghiệm sản phẩm thật với lượng người dùng lớn.",
    },
    {
        "org": "kpmg-vietnam",
        "title": "Associate Consultant — ESG & Sustainability",
        "industry": "strategy-consulting",
        "province": "hanoi",
        "employment_type": "full_time",
        "location_type": "hybrid",
        "skills": ["ESG", "Research", "Excel", "Stakeholder Management"],
        "preferred": ["GRI", "IFRS S1/S2", "Carbon Accounting"],
        "experience": (0, 2),
        "salary": (None, None, False),
        "seniority": "fresher",
        "deadline_days": 40,
        "description": "Hỗ trợ dự án tư vấn chiến lược ESG, báo cáo bền vững và chuyển đổi vận hành cho khách hàng doanh nghiệp.",
        "requirements": "Tư duy phân tích tốt, viết tiếng Anh tốt; ưu tiên ứng viên quan tâm ESG/Climate.",
        "benefits": "Lộ trình consultant rõ ràng, training quốc tế, exposure với nhiều ngành.",
    },
]


def _base_requirements(spec: dict[str, Any]) -> dict[str, Any]:
    return {
        "education": {"mode": "preferred", "values": ["bachelor"]},
        "nationalities": {"mode": "not_required"},
        "gender": {"mode": "not_required"},
        "age": {"mode": "not_required"},
        "marital_status": {"mode": "not_required"},
        "languages": [
            {"language": "English", "proficiency": "Readable documentation", "required": False}
        ],
        "certifications": [],
        "work_authorization": {"mode": "required", "values": ["Vietnam"]},
        "note": spec.get("requirement_note"),
    }


def _location(province_key: str, location_type: str) -> dict[str, str | None]:
    code, city = PROVINCES[province_key]
    return {
        "type": location_type,
        "province_code": code,
        "ward_code": None,
        "ward_name": None,
        "city": city,
        "country": "Vietnam",
    }


def _province_key_from_city(city: str | None) -> str:
    normalized = (city or "").lower()
    if "hồ chí minh" in normalized or "ho chi minh" in normalized:
        return "hcmc"
    if "hải phòng" in normalized or "hai phong" in normalized:
        return "haiphong"
    if "đà nẵng" in normalized or "da nang" in normalized:
        return "danang"
    if "cần thơ" in normalized or "can tho" in normalized:
        return "cantho"
    return "hanoi"


def _seniority_from_experience(job: Job) -> str:
    minimum = job.experience_min_years or 0
    if job.employment_type == "internship":
        return "intern"
    if minimum <= 1:
        return "fresher"
    if minimum <= 3:
        return "junior"
    if minimum <= 6:
        return "middle"
    return "senior"


async def _industry_map(session: AsyncSession) -> dict[str, Industry]:
    rows = (await session.execute(select(Industry))).scalars().all()
    return {row.slug: row for row in rows}


def _industry_path(row: Industry | None, by_id: dict[uuid.UUID, Industry]) -> list[str]:
    if row is None:
        return []
    chain = [row.slug]
    parent_id = row.parent_id
    while parent_id is not None and parent_id in by_id:
        parent = by_id[parent_id]
        chain.append(parent.slug)
        parent_id = parent.parent_id
    return list(reversed(chain))


async def enrich_marketplace_seed(
    session: AsyncSession,
    *,
    orgs: dict[str, Organization],
    users: dict[str, User],
) -> None:
    industries = await _industry_map(session)
    industries_by_id = {row.id: row for row in industries.values()}

    print("\n[marketplace links]")
    for org_slug, industry_slug in ORG_INDUSTRIES.items():
        org = orgs.get(org_slug)
        industry = industries.get(industry_slug)
        if org is None or industry is None:
            continue
        org.industry_id = industry.id
        org.industry = industry.slug
        org.settings = {
            **(org.settings or {}),
            "industry_path": _industry_path(industry, industries_by_id),
            "seed_source": "official-site-catalog",
        }
    await session.flush()
    print("  [link] organizations -> industry taxonomy")

    existing_jobs = (
        await session.execute(select(Job).where(Job.deleted_at.is_(None)))
    ).scalars().all()
    org_by_id = {org.id: org for org in orgs.values()}
    for job in existing_jobs:
        spec = JOB_LINKS.get(job.title)
        industry: Industry | None = None
        if spec is not None:
            industry = industries.get(spec["industry"])
        if industry is None:
            org = org_by_id.get(job.org_id)
            industry = industries_by_id.get(org.industry_id) if org else None
        if industry is not None:
            job.industry_id = industry.id
        province_key = (
            spec["province"] if spec is not None else _province_key_from_city(job.location_city)
        )
        loc = _location(province_key, job.location_type)
        job.location_city = loc["city"]
        job.location_country = "Vietnam"
        job.locations = [loc]
        job.seniority_level = (
            spec.get("seniority") if spec is not None else _seniority_from_experience(job)
        )
        job.candidate_requirements = {
            **_base_requirements(spec or {}),
            **((spec or {}).get("requirements", {})),
        }
        job.settings = {
            **(job.settings or {}),
            "industry_path": _industry_path(industry, industries_by_id),
            "seed_enriched": True,
        }
    await session.flush()
    print("  [link] existing jobs -> industries, locations, requirements")

    await _seed_additional_jobs(
        session,
        orgs=orgs,
        users=users,
        industries=industries,
        industries_by_id=industries_by_id,
    )


async def _seed_additional_jobs(
    session: AsyncSession,
    *,
    orgs: dict[str, Organization],
    users: dict[str, User],
    industries: dict[str, Industry],
    industries_by_id: dict[uuid.UUID, Industry],
) -> None:
    poster = users.get("admin") or next(iter(users.values()))
    existing_pairs = set((await session.execute(select(Job.title, Job.org_id))).all())
    created = 0
    for spec in ADDITIONAL_JOBS:
        org = orgs.get(spec["org"])
        if org is None or (spec["title"], org.id) in existing_pairs:
            continue
        industry = industries.get(spec["industry"])
        salary_min, salary_max, salary_disclosed = spec["salary"]
        min_exp, max_exp = spec["experience"]
        loc = _location(spec["province"], spec["location_type"])
        job = Job(
            id=uuid.uuid4(),
            org_id=org.id,
            posted_by=poster.id,
            title=spec["title"],
            slug=slugify(f"{org.slug}-{spec['title']}")[:280],
            description=spec["description"],
            requirements=spec["requirements"],
            benefits=spec["benefits"],
            employment_type=spec["employment_type"],
            location_type=spec["location_type"],
            location_city=loc["city"],
            location_country="Vietnam",
            locations=[loc],
            required_skills=spec["skills"],
            preferred_skills=spec["preferred"],
            experience_min_years=min_exp,
            experience_max_years=max_exp,
            industry_id=industry.id if industry is not None else None,
            degree_required="bachelor",
            seniority_level=spec["seniority"],
            candidate_requirements=_base_requirements(spec),
            salary_min=salary_min,
            salary_max=salary_max,
            salary_currency="VND",
            salary_is_disclosed=salary_disclosed,
            headcount=1,
            application_deadline=NOW + timedelta(days=spec["deadline_days"]),
            visibility=lifecycle.PUBLIC,
            status=lifecycle.ACTIVE,
            moderation_status=lifecycle.MOD_APPROVED,
            approved_by=poster.id,
            approved_at=NOW,
            submitted_at=NOW - timedelta(days=2),
            published_at=NOW - timedelta(days=1),
            is_featured=spec["title"].startswith("Kỹ sư Backend"),
            is_sponsored=spec["org"] in {"momo-payment", "tiki-corporation"},
            settings={
                "industry_path": _industry_path(industry, industries_by_id),
                "seed_enriched": True,
                "marketplace_badges": ["verified_partner"],
            },
            language_code="vi",
        )
        session.add(job)
        created += 1
    await session.flush()
    print(f"  [create] {created} additional linked marketplace jobs")
