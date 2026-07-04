# ruff: noqa: C408, E501
"""Development seed script — realistic VinUni career platform data.

Usage:
    cd backend
    source .venv/bin/activate
    uv run python scripts/seed_dev.py

Creates:
- 16 user accounts across student, alumni, university, partner, finance, recruiter roles
- VinUniversity organisation
- 12 realistic Vietnamese companies with industries
- Real company logos fetched from official company websites into configured storage
- 24 realistic JDs in mixed Vietnamese/English, language_code set correctly
- Org-member links + RBAC permissions so seeded accounts can use real screens

All passwords: 123456  (Argon2id hashed)
Run is idempotent: existing rows are skipped by email/slug uniqueness.
"""

from __future__ import annotations

import asyncio
import re
import sys
import uuid
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

# Ensure backend package is importable when run from repo root or scripts dir
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import get_settings
from app.modules.auth.infrastructure.passwords import hash_password
from app.modules.documents.infrastructure import storage as storage_backend
from app.modules.opportunities.domain.models import Job
from app.modules.organization.domain.catalog import ADMIN_WILDCARD
from app.modules.organization.domain.models import (
    Membership,
    MembershipRole,
    Organization,
    Permission,
    Role,
)
from app.modules.organization.infrastructure import logo_media
from app.modules.users.domain.models import Identity, User, UserPreference
from scripts.seeds.dev_marketplace_seed import enrich_marketplace_seed
from scripts.seeds.onboarding_seed import seed_onboarding_state
from scripts.seeds.seed_industries import seed_into_session as seed_industries_into_session
from scripts.seeds.seed_locations import seed_into_session as seed_locations_into_session
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NOW = datetime.now(tz=UTC)
HTTP_TIMEOUT_SECONDS = 12
MAX_LOGO_DOWNLOAD_BYTES = 4 * 1024 * 1024

ROLE_GRANTS: dict[str, tuple[str, ...]] = {
    "Admin": (ADMIN_WILDCARD,),
    "Recruiter": (
        "organizations:read",
        "jobs:read",
        "jobs:create",
        "jobs:update",
        "jobs:submit",
        "applications:read",
        "events:read",
        "events:create",
        "events:update",
        "events:submit",
        "members:read",
        "advertising:view",
        "advertising:create",
        "advertising:edit",
        "advertising:submit",
        "billing:view",
    ),
    "Hiring Manager": (
        "organizations:read",
        "jobs:read",
        "applications:read",
        "events:read",
        "members:read",
    ),
    "Finance": (
        "organizations:read",
        "billing:view",
        "billing:subscribe",
        "advertising:view",
    ),
    "Career Center Admin": (ADMIN_WILDCARD,),
    "Career Coach": (
        "organizations:read",
        "partners:read",
        "jobs:read",
        "jobs:moderate",
        "events:read",
        "events:moderate",
        "applications:read",
        "reviews:moderate",
        "cv_templates:read",
    ),
    "Moderation Officer": (
        "organizations:read",
        "partners:read",
        "partners:approve",
        "partners:reject",
        "jobs:read",
        "jobs:moderate",
        "events:read",
        "events:moderate",
        "advertising:view",
        "advertising:moderate",
        "reviews:moderate",
    ),
    "AI Ops": (
        "organizations:read",
        "ai_settings:read",
        "ai_settings:manage",
        "billing:view",
        "billing:manage",
        "cv_templates:read",
        "cv_templates:create",
        "cv_templates:update",
    ),
}

COMPANY_LOGO_HINTS: dict[str, tuple[str, ...]] = {
    "vinuniversity": ("https://vinuni.edu.vn/",),
    "fpt-software": ("https://fptsoftware.com/",),
    "vietcombank": ("https://www.vietcombank.com.vn/",),
    "tiki-corporation": ("https://tiki.vn/",),
    "kms-technology": ("https://kms-technology.com/",),
    "momo-payment": ("https://momo.vn/",),
    "kpmg-vietnam": ("https://kpmg.com/vn/en/home.html",),
    "vinfast": ("https://vinfastauto.com/vn_vi", "https://vinfast.vn/"),
    "vinmec": ("https://www.vinmec.com/",),
    "ssi-securities": ("https://www.ssi.com.vn/",),
    "axon-active": ("https://www.axonactive.com/",),
    "vietnam-airlines": ("https://www.vietnamairlines.com/",),
    "the-coffee-house": ("https://thecoffeehouse.com/",),
}


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class _IconParser(HTMLParser):
    """Collect official image/icon hints from a company's own website."""

    def __init__(self) -> None:
        super().__init__()
        self.urls: list[tuple[int, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        data = {k.lower(): (v or "") for k, v in attrs}
        if tag.lower() == "meta":
            prop = (data.get("property") or data.get("name") or "").lower()
            if prop in {"og:image", "og:image:secure_url", "twitter:image"}:
                self._add(10, data.get("content"))
        if tag.lower() == "link":
            rel = data.get("rel", "").lower()
            href = data.get("href")
            if "apple-touch-icon" in rel:
                self._add(20, href)
            elif "icon" in rel:
                self._add(30, href)
        if tag.lower() == "img":
            src = data.get("src") or data.get("data-src") or data.get("data-lazy-src")
            hint = " ".join(
                [
                    data.get("src", ""),
                    data.get("alt", ""),
                    data.get("class", ""),
                    data.get("id", ""),
                ]
            ).lower()
            if "logo" in hint:
                self._add(15, src)

    def _add(self, priority: int, url: str | None) -> None:
        if url and url not in [existing for _p, existing in self.urls]:
            self.urls.append((priority, url))


def _same_origin(url: str, base: str) -> bool:
    parsed = urlparse(url)
    base_parsed = urlparse(base)
    return parsed.netloc == base_parsed.netloc or parsed.netloc.endswith(
        f".{base_parsed.netloc}"
    )


def _http_get(url: str, *, accept: str) -> tuple[bytes, str | None]:
    req = Request(
        url,
        headers={
            "Accept": accept,
            "User-Agent": (
                "Mozilla/5.0 (compatible; VinUniCareerSeed/1.0; "
                "+https://vinuni.edu.vn)"
            ),
        },
    )
    with urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as resp:  # noqa: S310 - dev seed allowlist
        content_type = resp.headers.get("Content-Type")
        data = resp.read(MAX_LOGO_DOWNLOAD_BYTES + 1)
    if len(data) > MAX_LOGO_DOWNLOAD_BYTES:
        raise ValueError("logo candidate too large")
    return data, content_type


def _official_logo_candidates(homepage_url: str) -> list[str]:
    try:
        html, _ct = _http_get(
            homepage_url,
            accept="text/html,application/xhtml+xml,image/avif,image/webp,*/*;q=0.8",
        )
    except (OSError, ValueError, URLError) as exc:
        print(f"  [logo] cannot inspect {homepage_url}: {exc}")
        return []

    parser = _IconParser()
    try:
        parser.feed(html[:800_000].decode("utf-8", errors="ignore"))
    except Exception as exc:  # noqa: BLE001 - malformed marketing HTML
        print(f"  [logo] cannot parse {homepage_url}: {exc}")
        return []

    seen: set[str] = set()
    candidates: list[str] = []
    parser.urls.extend(
        [
            (40, "/apple-touch-icon.png"),
            (41, "/favicon-32x32.png"),
            (42, "/favicon.png"),
        ]
    )
    for _priority, raw in sorted(parser.urls, key=lambda item: item[0]):
        candidate = urljoin(homepage_url, raw)
        if candidate in seen:
            continue
        if candidate.startswith("https://") or _same_origin(candidate, homepage_url):
            seen.add(candidate)
            candidates.append(candidate)
    return candidates


def _download_official_logo(homepage_url: str) -> tuple[bytes, logo_media.LogoMedia] | None:
    for candidate in _official_logo_candidates(homepage_url):
        try:
            data, content_type = _http_get(candidate, accept="image/png,image/jpeg,image/webp,*/*;q=0.8")
            declared_type = (content_type or "").split(";")[0].strip().lower()
            safe_content_type = (
                declared_type if declared_type in logo_media.ALLOWED_CONTENT_TYPES else None
            )
            media = logo_media.validate_logo(
                data,
                safe_content_type,
                max_bytes=get_settings().org_logo_max_bytes,
            )
            return data, media
        except Exception as exc:  # noqa: BLE001 - try the next official candidate
            reason = getattr(exc, "reason", str(exc))
            print(f"  [logo] skip {candidate}: {reason}")
    return None


def _apply_real_logo(org: Organization, homepage_urls: tuple[str, ...]) -> None:
    """Fetch a real logo from official website metadata and store via storage backend."""

    storage = storage_backend.get_storage()
    if org.logo_path and storage.exists(org.logo_path):
        return
    for homepage_url in homepage_urls:
        result = _download_official_logo(homepage_url)
        if result is None:
            continue
        data, media = result
        asset_id = uuid.uuid4()
        key = logo_media.storage_key_for(org.id, asset_id, media.extension)
        storage.save(key, data)
        org.logo_path = key
        print(f"  [logo] {org.slug} <- {homepage_url}")
        return
    print(f"  [logo] warning: no valid PNG/JPEG/WebP logo found for {org.slug}")


async def _get_or_create_user(
    session: AsyncSession,
    *,
    email: str,
    full_name: str,
    is_superadmin: bool = False,
    preferred_language: str = "vi",
) -> User:
    row = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if row is not None:
        print(f"  [skip] user {email} already exists")
        return row
    row = User(
        id=_uuid(),
        email=email,
        full_name=full_name,
        password_hash=hash_password("123456"),
        is_active=True,
        is_superadmin=is_superadmin,
        preferred_language=preferred_language,
        email_verified_at=NOW,
    )
    session.add(row)
    await session.flush()
    pref = UserPreference(user_id=row.id, locale=preferred_language)
    session.add(pref)
    print(f"  [create] user {email}")
    return row


async def _get_or_create_identity(
    session: AsyncSession,
    *,
    user: User,
    persona: str,
    org_id: uuid.UUID | None = None,
    is_primary: bool = True,
) -> Identity:
    q = select(Identity).where(
        Identity.user_id == user.id,
        Identity.persona == persona,
        Identity.org_id == org_id,
    )
    row = (await session.execute(q)).scalar_one_or_none()
    if row is not None:
        return row
    row = Identity(id=_uuid(), user_id=user.id, persona=persona, org_id=org_id, is_primary=is_primary)
    session.add(row)
    await session.flush()
    return row


def _slugify(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[àáảãạăắằẳẵặâấầẩẫậ]", "a", s)
    s = re.sub(r"[èéẻẽẹêếềểễệ]", "e", s)
    s = re.sub(r"[ìíỉĩị]", "i", s)
    s = re.sub(r"[òóỏõọôốồổỗộơớờởỡợ]", "o", s)
    s = re.sub(r"[ùúủũụưứừửữự]", "u", s)
    s = re.sub(r"[ỳýỷỹỵ]", "y", s)
    s = re.sub(r"[đ]", "d", s)
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    return s


async def _get_or_create_org(
    session: AsyncSession,
    *,
    slug: str,
    display_name: str,
    org_type: str,
    description: str = "",
    industry: str | None = None,
    website_url: str | None = None,
    company_size: str | None = None,
    founded_year: int | None = None,
    headquarters_city: str = "Hà Nội",
    is_verified: bool = True,
    subscription_tier: str = "premium",
    status: str = "active",
) -> Organization:
    row = (await session.execute(select(Organization).where(Organization.slug == slug))).scalar_one_or_none()
    if row is not None:
        print(f"  [skip] org {slug} already exists")
        return row
    row = Organization(
        id=_uuid(),
        slug=slug,
        display_name=display_name,
        org_type=org_type,
        description=description,
        industry=industry,
        website_url=website_url,
        company_size=company_size,
        founded_year=founded_year,
        headquarters_city=headquarters_city,
        is_verified=is_verified,
        verified_at=NOW if is_verified else None,
        status=status,
        subscription_tier=subscription_tier,
    )
    session.add(row)
    await session.flush()
    print(f"  [create] org {slug}")
    return row


async def _add_org_member(
    session: AsyncSession,
    *,
    user: User,
    org: Organization,
    identity: Identity,
    role_name: str = "Admin",
    grants: tuple[str, ...] | None = None,
) -> None:
    """Create Membership + Role + MembershipRole for a user in an org."""
    # Ensure a system role exists for this org
    role_q = select(Role).where(Role.org_id == org.id, Role.name == role_name)
    role = (await session.execute(role_q)).scalar_one_or_none()
    if role is None:
        role = Role(id=_uuid(), org_id=org.id, name=role_name, is_system=True)
        session.add(role)
        await session.flush()
    await _ensure_role_permissions(session, role=role, grants=grants or ROLE_GRANTS.get(role_name, ()))

    member_q = select(Membership).where(
        Membership.user_id == user.id, Membership.org_id == org.id
    )
    membership = (await session.execute(member_q)).scalar_one_or_none()
    if membership is None:
        membership = Membership(
            id=_uuid(),
            org_id=org.id,
            user_id=user.id,
            identity_id=identity.id,
            status="active",
        )
        session.add(membership)
        await session.flush()

    # Assign role via MembershipRole
    mr_q = select(MembershipRole).where(
        MembershipRole.membership_id == membership.id,
        MembershipRole.role_id == role.id,
    )
    if (await session.execute(mr_q)).scalar_one_or_none() is None:
        session.add(MembershipRole(membership_id=membership.id, role_id=role.id))
        await session.flush()


async def _ensure_role_permissions(
    session: AsyncSession, *, role: Role, grants: tuple[str, ...]
) -> None:
    for grant in grants:
        if ":" not in grant:
            continue
        resource, action = grant.split(":", 1)
        exists = (
            await session.execute(
                select(Permission.id).where(
                    Permission.role_id == role.id,
                    Permission.resource_type == resource,
                    Permission.action == action,
                )
            )
        ).scalar_one_or_none()
        if exists is None:
            session.add(
                Permission(role_id=role.id, resource_type=resource, action=action)
            )
    await session.flush()


async def _create_job(
    session: AsyncSession,
    *,
    org: Organization,
    posted_by: User,
    title: str,
    description: str,
    requirements: str | None = None,
    benefits: str | None = None,
    employment_type: str = "full_time",
    location_type: str = "onsite",
    location_city: str = "Hà Nội",
    required_skills: list[str] | None = None,
    preferred_skills: list[str] | None = None,
    experience_min_years: int | None = None,
    salary_min: int | None = None,
    salary_max: int | None = None,
    salary_currency: str = "VND",
    salary_is_disclosed: bool = True,
    language_code: str = "vi",
    deadline_days: int = 30,
) -> Job:
    slug_base = _slugify(title) + "-" + org.slug
    # Make unique
    slug_candidate = slug_base
    counter = 1
    while (await session.execute(select(Job.id).where(Job.slug == slug_candidate))).scalar_one_or_none() is not None:
        slug_candidate = f"{slug_base}-{counter}"
        counter += 1

    job = Job(
        id=_uuid(),
        org_id=org.id,
        posted_by=posted_by.id,
        title=title,
        slug=slug_candidate,
        description=description,
        requirements=requirements,
        benefits=benefits,
        employment_type=employment_type,
        location_type=location_type,
        location_city=location_city,
        location_country="Vietnam",
        locations=[{"type": location_type, "city": location_city, "country": "Vietnam"}],
        required_skills=required_skills or [],
        preferred_skills=preferred_skills or [],
        experience_min_years=experience_min_years,
        salary_min=salary_min,
        salary_max=salary_max,
        salary_currency=salary_currency,
        salary_is_disclosed=salary_is_disclosed,
        headcount=1,
        application_deadline=NOW + timedelta(days=deadline_days),
        visibility="public",
        status="active",
        moderation_status="approved",
        approved_at=NOW,
        submitted_at=NOW - timedelta(days=2),
        published_at=NOW - timedelta(days=1),
        language_code=language_code,
        is_featured=False,
        is_sponsored=False,
    )
    session.add(job)
    await session.flush()
    return job


# ---------------------------------------------------------------------------
# Seed functions
# ---------------------------------------------------------------------------

async def seed_users(session: AsyncSession) -> dict[str, User]:
    print("\n[users]")
    specs = {
        "vinuni_student": ("student@vinuni.edu.vn", "Nguyễn Minh Anh", "vi", False),
        "vinuni_student_data": ("data.student@vinuni.edu.vn", "Lê Gia Hân", "vi", False),
        "vinuni_student_business": ("business.student@vinuni.edu.vn", "Đỗ Minh Quân", "vi", False),
        "external_student": ("student@gmail.com", "Trần Hữu Đức", "vi", False),
        "alumni": ("alumni@vinuni.edu.vn", "Phạm Hoàng Nam", "en", False),
        "partner": ("partner@gmail.com", "Phạm Thị Lan", "vi", False),
        "fpt_recruiter": ("recruiter.fpt@example.com", "Nguyễn Thu Trang", "vi", False),
        "fpt_hiring_manager": ("hiring.fpt@example.com", "Michael Nguyen", "en", False),
        "fpt_finance": ("finance.fpt@example.com", "Lê Quốc Bảo", "vi", False),
        "vcb_recruiter": ("recruiter.vcb@example.com", "Hoàng Thanh Mai", "vi", False),
        "momo_recruiter": ("recruiter.momo@example.com", "Đặng Anh Khoa", "vi", False),
        "career_admin": ("career.admin@vinuni.edu.vn", "VinUni Career Admin", "vi", False),
        "career_coach": ("career.coach@vinuni.edu.vn", "Dr. Sarah Tran", "en", False),
        "moderator": ("moderator@vinuni.edu.vn", "Ngô Bảo Châu", "vi", False),
        "ai_ops": ("ai.ops@vinuni.edu.vn", "AI Operations", "en", False),
        "admin": ("admin@vinuni.com", "Platform Superadmin", "vi", True),
    }
    users: dict[str, User] = {}
    for key, (email, name, locale, is_superadmin) in specs.items():
        users[key] = await _get_or_create_user(
            session,
            email=email,
            full_name=name,
            is_superadmin=is_superadmin,
            preferred_language=locale,
        )

    for key in (
        "vinuni_student",
        "vinuni_student_data",
        "vinuni_student_business",
        "external_student",
    ):
        await _get_or_create_identity(session, user=users[key], persona="student")
    await _get_or_create_identity(session, user=users["alumni"], persona="alumni")
    await _get_or_create_identity(
        session, user=users["admin"], persona="university_staff"
    )

    return users


async def seed_organisations(session: AsyncSession, users: dict[str, User]) -> dict[str, Organization]:
    print("\n[organisations]")
    orgs: dict[str, Organization] = {}

    # VinUniversity (university type)
    orgs["vinuni"] = await _get_or_create_org(
        session,
        slug="vinuniversity",
        display_name="VinUniversity",
        org_type="university",
        description="VinUniversity là trường đại học theo mô hình nghiên cứu ứng dụng, tập trung vào đào tạo nhân tài công nghệ và quản trị kinh doanh.",
        industry="education",
        website_url="https://vinuni.edu.vn",
        company_size="201-500",
        founded_year=2019,
        headquarters_city="Hà Nội",
        subscription_tier="enterprise",
    )
    orgs["vinuniversity"] = orgs["vinuni"]
    superadmin_identity = await _get_or_create_identity(
        session,
        user=users["admin"],
        persona="university_staff",
        org_id=orgs["vinuni"].id,
        is_primary=False,
    )
    await _add_org_member(
        session,
        user=users["admin"],
        org=orgs["vinuni"],
        identity=superadmin_identity,
        role_name="Career Center Admin",
    )

    university_staff_roles = {
        "career_admin": "Career Center Admin",
        "career_coach": "Career Coach",
        "moderator": "Moderation Officer",
        "ai_ops": "AI Ops",
    }
    for user_key, role_name in university_staff_roles.items():
        identity = await _get_or_create_identity(
            session,
            user=users[user_key],
            persona="university_staff",
            org_id=orgs["vinuni"].id,
            is_primary=True,
        )
        await _add_org_member(
            session,
            user=users[user_key],
            org=orgs["vinuni"],
            identity=identity,
            role_name=role_name,
        )

    # Partner companies
    companies = [
        dict(
            slug="fpt-software",
            display_name="FPT Software",
            org_type="partner",
            description="FPT Software là một trong những tập đoàn công nghệ thông tin lớn nhất Việt Nam, cung cấp dịch vụ phần mềm và chuyển đổi số toàn cầu.",
            industry="information_technology",
            website_url="https://fptsoftware.com",
            company_size="10001+",
            founded_year=1999,
            headquarters_city="Hà Nội",
        ),
        dict(
            slug="vietcombank",
            display_name="Vietcombank",
            org_type="partner",
            description="Ngân hàng TMCP Ngoại thương Việt Nam (Vietcombank) — ngân hàng thương mại lớn nhất Việt Nam với hơn 60 năm lịch sử.",
            industry="banking_finance",
            website_url="https://vietcombank.com.vn",
            company_size="10001+",
            founded_year=1963,
            headquarters_city="Hà Nội",
        ),
        dict(
            slug="tiki-corporation",
            display_name="Tiki Corporation",
            org_type="partner",
            description="Tiki là nền tảng thương mại điện tử hàng đầu Việt Nam, kết hợp công nghệ và logistics để mang đến trải nghiệm mua sắm nhanh nhất.",
            industry="e_commerce",
            website_url="https://tiki.vn",
            company_size="1001-5000",
            founded_year=2010,
            headquarters_city="Hồ Chí Minh",
        ),
        dict(
            slug="kms-technology",
            display_name="KMS Technology",
            org_type="partner",
            description="KMS Technology is a US-based software engineering company with development centers in Vietnam, specializing in Agile software development and QA services.",
            industry="information_technology",
            website_url="https://kms-technology.com",
            company_size="1001-5000",
            founded_year=2009,
            headquarters_city="Hồ Chí Minh",
        ),
        dict(
            slug="momo-payment",
            display_name="MoMo",
            org_type="partner",
            description="MoMo là ví điện tử và nền tảng thanh toán số hàng đầu Việt Nam với hơn 30 triệu người dùng, tiên phong trong hệ sinh thái fintech.",
            industry="fintech",
            website_url="https://momo.vn",
            company_size="1001-5000",
            founded_year=2010,
            headquarters_city="Hồ Chí Minh",
        ),
        dict(
            slug="kpmg-vietnam",
            display_name="KPMG Vietnam",
            org_type="partner",
            description="KPMG Vietnam provides audit, tax, and advisory services to leading businesses across Vietnam with the global expertise of the KPMG network.",
            industry="professional_services",
            website_url="https://kpmg.com/vn",
            company_size="501-1000",
            founded_year=1994,
            headquarters_city="Hồ Chí Minh",
        ),
        dict(
            slug="vinfast",
            display_name="VinFast",
            org_type="partner",
            description="VinFast là thương hiệu xe điện toàn cầu của Tập đoàn Vingroup, đang mở rộng thị trường tại Bắc Mỹ, châu Âu và Đông Nam Á.",
            industry="automotive_manufacturing",
            website_url="https://vinfast.vn",
            company_size="10001+",
            founded_year=2017,
            headquarters_city="Hải Phòng",
        ),
        dict(
            slug="vinmec",
            display_name="Vinmec International Hospital",
            org_type="partner",
            description="Vinmec là hệ thống bệnh viện đa khoa quốc tế chuẩn JCI đầu tiên tại Việt Nam, thuộc Tập đoàn Vingroup.",
            industry="healthcare",
            website_url="https://vinmec.com",
            company_size="5001-10000",
            founded_year=2012,
            headquarters_city="Hà Nội",
        ),
        dict(
            slug="ssi-securities",
            display_name="SSI Securities Corporation",
            org_type="partner",
            description="SSI là công ty chứng khoán lớn nhất Việt Nam theo vốn điều lệ, cung cấp dịch vụ môi giới, đầu tư và tư vấn tài chính.",
            industry="investment_securities",
            website_url="https://ssi.com.vn",
            company_size="501-1000",
            founded_year=1999,
            headquarters_city="Hồ Chí Minh",
        ),
        dict(
            slug="axon-active",
            display_name="Axon Active",
            org_type="partner",
            description="Axon Active is a Swiss-Vietnamese software development company delivering Agile and Scrum-based solutions for enterprise clients in Europe and the US.",
            industry="information_technology",
            website_url="https://axonactive.com",
            company_size="501-1000",
            founded_year=2007,
            headquarters_city="Hồ Chí Minh",
        ),
        dict(
            slug="vietnam-airlines",
            display_name="Vietnam Airlines",
            org_type="partner",
            description="Vietnam Airlines là hãng hàng không quốc gia Việt Nam với mạng lưới đường bay tới hơn 54 điểm đến trong nước và quốc tế.",
            industry="aviation_logistics",
            website_url="https://vietnamairlines.com",
            company_size="10001+",
            founded_year=1956,
            headquarters_city="Hà Nội",
        ),
        dict(
            slug="the-coffee-house",
            display_name="The Coffee House",
            org_type="partner",
            description="The Coffee House là chuỗi cà phê công nghệ hàng đầu Việt Nam với hơn 160 cửa hàng, kết hợp trải nghiệm tốt và nền tảng số hiện đại.",
            industry="food_beverage_technology",
            website_url="https://thecoffeehouse.com",
            company_size="1001-5000",
            founded_year=2014,
            headquarters_city="Hồ Chí Minh",
        ),
    ]

    for c in companies:
        orgs[c["slug"]] = await _get_or_create_org(session, **c)  # type: ignore[arg-type]

    for slug, urls in COMPANY_LOGO_HINTS.items():
        org = orgs.get(slug)
        if org is not None:
            _apply_real_logo(org, urls)

    partner_members = [
        ("partner", "fpt-software", "Admin"),
        ("fpt_recruiter", "fpt-software", "Recruiter"),
        ("fpt_hiring_manager", "fpt-software", "Hiring Manager"),
        ("fpt_finance", "fpt-software", "Finance"),
        ("vcb_recruiter", "vietcombank", "Recruiter"),
        ("momo_recruiter", "momo-payment", "Recruiter"),
    ]
    for user_key, org_key, role_name in partner_members:
        identity = await _get_or_create_identity(
            session,
            user=users[user_key],
            persona="partner_member",
            org_id=orgs[org_key].id,
            is_primary=True,
        )
        await _add_org_member(
            session,
            user=users[user_key],
            org=orgs[org_key],
            identity=identity,
            role_name=role_name,
        )

    return orgs


async def seed_jobs(session: AsyncSession, orgs: dict[str, Organization], users: dict[str, User]) -> None:
    print("\n[jobs]")
    partner = users["partner"]
    admin = users["admin"]

    # Check if jobs already exist for FPT to avoid re-seeding
    existing = (await session.execute(
        select(Job.id).where(Job.org_id == orgs["fpt-software"].id).limit(1)
    )).scalar_one_or_none()
    if existing is not None:
        print("  [skip] jobs already seeded")
        return

    # ---- FPT Software (IT, mostly English JDs) ----
    fpt = orgs["fpt-software"]
    await _create_job(session, org=fpt, posted_by=partner,
        title="Senior Java Backend Developer",
        language_code="en",
        location_city="Hà Nội",
        employment_type="full_time",
        required_skills=["Java", "Spring Boot", "Microservices", "PostgreSQL", "Docker"],
        preferred_skills=["Kubernetes", "Kafka", "Redis", "AWS"],
        experience_min_years=4,
        salary_min=35_000_000, salary_max=60_000_000,
        description="""## About the Role

FPT Software is looking for a **Senior Java Backend Developer** to join our Digital Transformation team serving clients in the banking and insurance sector.

You will architect and build high-throughput microservices that process millions of transactions daily. This is a senior IC role with ownership over design decisions and mentoring of mid-level engineers.

## What you'll do

- Design and implement RESTful APIs and event-driven microservices using Spring Boot 3.x
- Optimize database schemas and query performance in PostgreSQL / Oracle environments
- Lead code reviews and drive engineering best practices across the squad
- Collaborate with solution architects on system design for new client projects
- Write comprehensive unit and integration tests (JUnit 5, Mockito)
- Participate in client-facing technical workshops (English required)

## Tech stack

Java 21 · Spring Boot 3 · Kafka · PostgreSQL · Redis · Docker · Kubernetes · GitHub Actions""",
        requirements="""- 4+ years of professional Java development experience
- Strong understanding of Spring Boot, Spring Security, and JPA/Hibernate
- Hands-on experience with microservices architecture and REST API design
- Proficiency with SQL and experience tuning queries in PostgreSQL or Oracle
- Familiarity with Docker containerization and CI/CD pipelines
- Good communication skills in English (reading/writing; spoken is a plus)""",
        benefits="""- Competitive salary: 35–60M VND/month depending on experience
- 13th-month bonus + annual performance review
- Premium PVI health insurance for employee and family
- Flexible working hours (core hours 9am–4pm)
- 16 days annual leave + Vietnamese public holidays
- FPT Learning platform & overseas training opportunities
- Modern office in FPT Cầu Giấy campus""",
        deadline_days=45,
    )

    await _create_job(session, org=fpt, posted_by=partner,
        title="React Native Mobile Developer",
        language_code="en",
        location_city="Hà Nội",
        employment_type="full_time",
        required_skills=["React Native", "TypeScript", "Redux", "REST APIs"],
        preferred_skills=["Expo", "Firebase", "Jest", "Detox"],
        experience_min_years=2,
        salary_min=25_000_000, salary_max=45_000_000,
        description="""## Role Overview

Join FPT Software's Mobile Center of Excellence to build cross-platform apps for our enterprise clients in retail, logistics, and healthcare.

You'll work in cross-functional product squads alongside product managers and UX designers, shipping to both the App Store and Google Play.

## Responsibilities

- Build and maintain React Native applications targeting iOS and Android
- Implement complex UI animations and custom native modules when needed
- Integrate with RESTful backends and GraphQL APIs
- Write unit tests with Jest and E2E tests with Detox
- Participate in sprint planning and agile ceremonies

## Stack

React Native · TypeScript · Redux Toolkit · React Query · Firebase · Fastlane · GitHub Actions""",
        requirements="""- 2+ years building production React Native apps
- Strong TypeScript and modern React (hooks, context) skills
- Experience integrating with REST and/or GraphQL APIs
- Familiarity with state management (Redux Toolkit or Zustand)
- Understanding of iOS and Android deployment pipelines
- English proficiency to work with offshore product owners""",
        benefits="""- Salary 25–45M VND/month
- Flexible hybrid work (3 days office, 2 days remote)
- 13th month + performance bonus
- Full training budget for certifications (AWS, Google)
- Team offsites and hackathons""",
        deadline_days=30,
    )

    await _create_job(session, org=fpt, posted_by=partner,
        title="Kỹ sư QA Automation (Selenium/Playwright)",
        language_code="vi",
        location_city="Hồ Chí Minh",
        employment_type="full_time",
        required_skills=["Selenium", "Python", "TestNG", "API Testing"],
        preferred_skills=["Playwright", "Postman", "Jenkins", "JIRA"],
        experience_min_years=2,
        salary_min=20_000_000, salary_max=38_000_000,
        description="""## Mô tả công việc

FPT Software đang tìm kiếm **Kỹ sư QA Automation** tham gia đội kiểm thử dự án xuất khẩu phần mềm cho khách hàng Nhật Bản và Mỹ.

Bạn sẽ là cầu nối giữa nhóm phát triển và nhóm đảm bảo chất lượng, tự động hóa các kịch bản kiểm thử quan trọng và xây dựng framework test bền vững.

## Nhiệm vụ chính

- Xây dựng và duy trì test suite tự động cho web application (Selenium/Playwright)
- Viết API test sử dụng Postman/RestAssured tích hợp CI/CD pipeline
- Phân tích yêu cầu và thiết kế test case từ tài liệu đặc tả
- Báo cáo lỗi chi tiết và theo dõi tiến độ fix bug
- Hỗ trợ performance testing khi cần (JMeter)
- Tham gia Agile/Scrum sprint review và retrospective""",
        requirements="""- Tối thiểu 2 năm kinh nghiệm QA Automation
- Thành thạo Selenium WebDriver với Java hoặc Python
- Hiểu biết về REST API testing và công cụ Postman
- Có kinh nghiệm CI/CD (Jenkins, GitLab CI, hoặc GitHub Actions)
- Đọc hiểu tài liệu tiếng Anh
- Kỹ năng phân tích vấn đề và báo cáo rõ ràng""",
        benefits="""- Lương thỏa thuận: 20-38 triệu VNĐ/tháng
- Thưởng tháng 13 + đánh giá lương hàng năm
- Bảo hiểm sức khỏe cao cấp PVI cho toàn gia đình
- 16 ngày phép + nghỉ lễ theo quy định nhà nước
- Môi trường quốc tế, tiếng Anh là ngôn ngữ làm việc thứ hai
- Cơ hội đào tạo chứng chỉ ISTQB, AWS""",
        deadline_days=25,
    )

    # ---- Vietcombank (banking, mixed language) ----
    vcb = orgs["vietcombank"]
    await _create_job(session, org=vcb, posted_by=admin,
        title="Chuyên viên Phân tích Dữ liệu (Data Analyst)",
        language_code="vi",
        location_city="Hà Nội",
        employment_type="full_time",
        required_skills=["SQL", "Python", "Power BI", "Data Analysis"],
        preferred_skills=["Tableau", "Machine Learning", "Spark"],
        experience_min_years=2,
        salary_min=18_000_000, salary_max=32_000_000,
        description="""## Vị trí: Chuyên viên Phân tích Dữ liệu

Trung tâm Dữ liệu và Công nghệ Vietcombank tuyển dụng **Chuyên viên Phân tích Dữ liệu** tham gia đội Data Analytics phục vụ mảng ngân hàng bán lẻ.

### Mô tả công việc

Bạn sẽ trực tiếp làm việc với dữ liệu giao dịch, hành vi khách hàng và hiệu quả chiến dịch marketing để đưa ra insight giúp các phòng ban ra quyết định dựa trên dữ liệu.

**Các nhiệm vụ hàng ngày:**
- Truy vấn, xử lý và phân tích dữ liệu lớn từ hệ thống ngân hàng lõi (core banking)
- Xây dựng báo cáo và dashboard trực quan trên Power BI / Tableau
- Phối hợp với Product Owner và Business Analyst xác định KPI và chỉ số theo dõi
- Viết script Python để tự động hóa quy trình ETL và báo cáo định kỳ
- Hỗ trợ xây dựng mô hình dự báo cơ bản (customer churn, credit scoring)

### Yêu cầu học vấn

Tốt nghiệp đại học chuyên ngành Toán thống kê, Công nghệ thông tin, Kinh tế lượng hoặc các ngành liên quan.""",
        requirements="""**Bắt buộc:**
- Tối thiểu 2 năm kinh nghiệm phân tích dữ liệu trong môi trường tài chính/ngân hàng
- Thành thạo SQL (Oracle SQL hoặc MS SQL Server)
- Có kinh nghiệm dùng Python cho phân tích dữ liệu (pandas, numpy, matplotlib)
- Biết sử dụng công cụ BI (Power BI ưu tiên, hoặc Tableau)
- Kỹ năng tư duy phân tích và trình bày kết quả rõ ràng

**Là lợi thế:**
- Có kinh nghiệm với Big Data (Hadoop, Spark, Hive)
- Hiểu biết về quy trình nghiệp vụ ngân hàng (tín dụng, tiết kiệm, thanh toán)
- Chứng chỉ Data Analytics (Google, IBM) hoặc CFA level 1""",
        benefits="""- Lương hấp dẫn theo thỏa thuận (18–32 triệu VNĐ/tháng)
- Thưởng hiệu suất hàng quý và thưởng cuối năm
- Bảo hiểm xã hội, y tế, thất nghiệp đầy đủ + bảo hiểm sức khỏe nội trú Bảo Việt
- Cơ hội được cử đi đào tạo nước ngoài về AI/Data Science
- Môi trường làm việc chuyên nghiệp tại trụ sở Hoàn Kiếm, Hà Nội
- Văn phòng hiện đại, canteen nội bộ""",
        deadline_days=20,
    )

    await _create_job(session, org=vcb, posted_by=admin,
        title="Senior DevSecOps Engineer",
        language_code="en",
        location_city="Hà Nội",
        employment_type="full_time",
        required_skills=["Kubernetes", "Terraform", "CI/CD", "Security", "AWS"],
        preferred_skills=["Vault", "OPA", "Falco", "Istio"],
        experience_min_years=5,
        salary_min=45_000_000, salary_max=80_000_000,
        description="""## Senior DevSecOps Engineer — Vietcombank Digital

Vietcombank's Cloud Infrastructure team is building the next generation of secure cloud-native banking infrastructure. We are looking for a **Senior DevSecOps Engineer** to embed security into every layer of our CI/CD and runtime stack.

### What you will own

- Design and maintain Kubernetes clusters (EKS) running critical banking workloads
- Implement policy-as-code with OPA/Gatekeeper and runtime threat detection with Falco
- Build and maintain secure CI/CD pipelines with automated SAST/DAST gates
- Manage secrets and PKI with HashiCorp Vault and AWS KMS
- Lead security incident response for cloud infrastructure events
- Drive SOC 2 Type II and ISO 27001 controls for cloud environments
- Mentor junior engineers on security best practices

### Environment

AWS EKS · Terraform · GitHub Actions · ArgoCD · HashiCorp Vault · Istio · Falco · Trivy · Datadog""",
        requirements="""- 5+ years in DevOps/Platform Engineering roles; 2+ years in DevSecOps
- Deep expertise in Kubernetes (CKA/CKAD preferred)
- Hands-on Terraform experience managing production AWS infrastructure
- Strong understanding of network security, mTLS, and zero-trust architecture
- Experience implementing SAST (SonarQube, Semgrep) and DAST (OWASP ZAP) in CI/CD
- Familiarity with financial sector security standards (PCI-DSS, ISO 27001)
- Excellent English communication for cross-team and vendor discussions""",
        benefits="""- Salary: 45–80M VND/month (commensurate with experience)
- Annual performance bonus (up to 4 months)
- Premium healthcare (Bảo Việt Gold) for self and immediate family
- Full study leave + budget for certifications (CKS, AWS Security Specialty, CISSP)
- Relocation support within Vietnam
- Flexible working arrangement: 2 days WFH per week
- Vietcombank employee banking benefits""",
        deadline_days=35,
    )

    # ---- Tiki (e-commerce) ----
    tiki = orgs["tiki-corporation"]
    await _create_job(session, org=tiki, posted_by=admin,
        title="Product Manager — Logistics & Last Mile",
        language_code="en",
        location_city="Hồ Chí Minh",
        employment_type="full_time",
        required_skills=["Product Management", "Agile", "Data Analysis", "Stakeholder Management"],
        preferred_skills=["SQL", "Logistics", "OKR", "A/B Testing"],
        experience_min_years=3,
        salary_min=40_000_000, salary_max=70_000_000,
        description="""## Product Manager — Logistics & Last Mile Delivery

Tiki is Vietnam's fastest-delivery e-commerce platform. Our promise of **2-hour delivery** in major cities is powered by a proprietary logistics network that we continue to extend. We're looking for a **Product Manager** to own the last-mile delivery product — from real-time routing algorithms to customer communication.

### Your mission

Make Tiki's last-mile experience the most reliable and transparent in Southeast Asia.

### What you'll work on

- Define and own the product roadmap for last-mile delivery features (driver app, tracking, ETA, notifications)
- Partner with the logistics operations team to identify and instrument operational bottlenecks
- Define success metrics, instrument dashboards, and run A/B experiments
- Write sharp PRDs and collaborate with engineering squads across Hanoi and HCM
- Prioritize a fast-moving backlog while balancing tech debt and new capabilities
- Present roadmap updates to C-level stakeholders quarterly

### Team & culture

You'll report to the VP of Logistics Product and work in a squad of 2 engineers, 1 data analyst, and 1 designer. Tiki runs OKRs company-wide and ships weekly.""",
        requirements="""- 3+ years as a Product Manager in a consumer internet or logistics company
- Strong analytical mindset: comfortable with SQL for self-service data analysis
- Experience running A/B tests and interpreting statistical results
- Excellent written and verbal communication in English
- Ability to influence without direct authority across engineering, ops, and business
- Bonus: prior experience with real-time systems (routing, tracking, maps APIs)""",
        benefits="""- Competitive salary 40–70M VND/month + equity options
- 20 days annual leave + flexible hybrid policy (HCM office)
- Premium healthcare insurance (PTI)
- Annual learning budget 10M VND for courses, conferences
- 20% of time for internal innovation projects
- Canteen + free snacks at office""",
        deadline_days=30,
    )

    await _create_job(session, org=tiki, posted_by=admin,
        title="Machine Learning Engineer — Recommendation",
        language_code="en",
        location_city="Hồ Chí Minh",
        employment_type="full_time",
        required_skills=["Python", "Machine Learning", "PyTorch", "Recommendation Systems"],
        preferred_skills=["Spark", "Airflow", "Kubernetes", "A/B Testing"],
        experience_min_years=3,
        salary_min=50_000_000, salary_max=90_000_000,
        description="""## Machine Learning Engineer — Personalization & Recommendation

Tiki's AI Lab is building the recommendation and personalization engine that powers what 20M+ users see when they open the app. We are hiring **ML Engineers** to design, train, and ship production recommendation models at scale.

### Impact

Every percentage-point improvement in recommendation CTR translates to tens of billions of VND in annual GMV.

### Core responsibilities

- Build and iterate on two-tower retrieval and ranking models using PyTorch
- Own the end-to-end MLOps lifecycle: feature engineering → training → evaluation → serving
- Implement online A/B experiments and interpret results with statistical rigor
- Maintain and improve real-time feature serving pipelines (Redis + Flink)
- Collaborate with data engineers on feature store design (Feast)
- Publish internal technical reports and mentor junior ML engineers

### Our current stack

PyTorch · TorchServe · Apache Spark · Apache Flink · Feast · Airflow · MLflow · Kubernetes (GKE)""",
        requirements="""- 3+ years experience in applied ML, preferably recommendation or ranking
- Strong Python skills; comfortable writing production-quality code
- Deep understanding of collaborative filtering, two-tower models, and LTR
- Experience with distributed training and large-scale data pipelines
- Familiarity with online experimentation and causal inference
- Strong communication skills in English; Vietnamese is a bonus""",
        benefits="""- Salary 50–90M VND/month (negotiable for exceptional candidates)
- Research time: 1 day per week for self-directed ML exploration
- Conference budget for NeurIPS, RecSys, KDD
- GPU cluster access for training large models
- Tiki employee shopping credits monthly""",
        deadline_days=40,
    )

    # ---- KMS Technology ----
    kms = orgs["kms-technology"]
    await _create_job(session, org=kms, posted_by=admin,
        title="Senior Software Engineer (.NET / C#)",
        language_code="en",
        location_city="Hồ Chí Minh",
        employment_type="full_time",
        required_skills=[".NET", "C#", "SQL Server", "REST APIs", "Azure"],
        preferred_skills=["Entity Framework", "CQRS", "Microservices", "Docker"],
        experience_min_years=4,
        salary_min=35_000_000, salary_max=60_000_000,
        description="""## Senior Software Engineer — .NET

KMS Technology builds software for US and European SaaS companies from its development centers in Vietnam. Our engineers work directly with US-based clients in fast-paced Agile environments.

We are looking for a **Senior .NET Engineer** to join a squad delivering a healthcare data management platform used by major US hospital networks.

### Your responsibilities

- Design, implement, and own backend services in .NET 8 and C# 12
- Build RESTful and event-driven APIs consumed by web and mobile clients
- Write clean, testable code with comprehensive unit and integration tests (xUnit)
- Participate in sprint planning, estimation, and cross-timezone standups with US clients
- Conduct thorough code reviews and enforce engineering standards
- Contribute to CI/CD improvements and Azure DevOps pipeline management

### Codebase & environment

.NET 8 · ASP.NET Core · Entity Framework Core 8 · Azure Service Bus · SQL Server 2022 · Docker · Azure Kubernetes Service · GitHub Actions""",
        requirements="""- 4+ years of professional .NET / C# development
- Solid understanding of object-oriented design and SOLID principles
- Experience with EF Core, database migrations, and SQL query optimization
- Familiarity with event-driven patterns (pub/sub, outbox, Saga)
- Comfortable working in UTC+7 timezone with daily US-client touchpoints
- English proficiency: fluent written; conversational spoken""",
        benefits="""- Salary 35–60M VND/month
- 100% work from office initially; hybrid after probation
- Quarterly performance review and salary adjustment
- PVI healthcare for employee and 1 dependent
- Annual tech conference attendance (internal sponsorship)
- English club, soft-skill training, Toastmasters chapter on-site""",
        deadline_days=28,
    )

    # ---- MoMo ----
    momo = orgs["momo-payment"]
    await _create_job(session, org=momo, posted_by=admin,
        title="Kỹ sư Backend — Hệ thống Thanh toán (Go/Java)",
        language_code="vi",
        location_city="Hồ Chí Minh",
        employment_type="full_time",
        required_skills=["Go", "Java", "Microservices", "Kafka", "PostgreSQL"],
        preferred_skills=["Redis", "Kubernetes", "gRPC", "Prometheus"],
        experience_min_years=3,
        salary_min=30_000_000, salary_max=60_000_000,
        description="""## Kỹ sư Backend — Hệ thống Thanh toán Core

MoMo đang xây dựng hạ tầng thanh toán thế hệ tiếp theo xử lý hàng triệu giao dịch mỗi ngày, hỗ trợ hơn 30 triệu người dùng trên toàn Việt Nam.

Chúng tôi tìm kiếm **Kỹ sư Backend** tham gia đội Core Payments Platform — nhóm kỹ thuật xây dựng trái tim của hệ sinh thái MoMo.

### Bạn sẽ làm gì?

- Thiết kế và phát triển microservices xử lý giao dịch tài chính với yêu cầu độ tin cậy 99.99%
- Xây dựng pipeline xử lý sự kiện thời gian thực trên Apache Kafka
- Thiết kế schema PostgreSQL tối ưu cho khối lượng giao dịch lớn
- Implement distributed locking và idempotency patterns để đảm bảo tính toàn vẹn giao dịch
- Phân tích và giải quyết các vấn đề về performance và bottleneck
- Viết tài liệu kỹ thuật và hướng dẫn tích hợp cho partner

### Stack kỹ thuật

Go 1.22 · Java 21 · Apache Kafka · PostgreSQL 16 · Redis Cluster · gRPC · Kubernetes (EKS) · Prometheus/Grafana · Jaeger""",
        requirements="""**Bắt buộc:**
- Tối thiểu 3 năm kinh nghiệm lập trình backend (Go hoặc Java)
- Hiểu sâu về microservices architecture và distributed systems
- Kinh nghiệm với message broker (Kafka, RabbitMQ, hoặc tương đương)
- Thành thạo SQL và thiết kế schema cho PostgreSQL
- Hiểu biết về concurrency, race conditions, và transactional guarantees

**Ưu tiên:**
- Kinh nghiệm trong lĩnh vực fintech, thanh toán điện tử, hoặc ngân hàng số
- Có kiến thức về PCI-DSS hoặc tiêu chuẩn bảo mật thanh toán
- Đã từng xử lý hệ thống throughput cao (>10k TPS)""",
        benefits="""- Lương thỏa thuận: 30–60 triệu VNĐ/tháng + thưởng hiệu suất
- Stock option cho nhân viên dài hạn
- Bảo hiểm sức khỏe cao cấp Bảo Việt cho cả gia đình
- Flexible working: WFH 2 ngày/tuần sau thử việc
- Budget học tập 15 triệu VNĐ/năm cho khóa học và hội nghị
- Văn phòng GreenPark, Q.10 — canteen, gym, yoga studio nội bộ
- MoMo voucher hàng tháng cho nhân viên""",
        deadline_days=20,
    )

    await _create_job(session, org=momo, posted_by=admin,
        title="Product Designer (UX/UI) — Consumer App",
        language_code="vi",
        location_city="Hồ Chí Minh",
        employment_type="full_time",
        required_skills=["Figma", "UX Research", "UI Design", "Prototyping"],
        preferred_skills=["Motion Design", "Design System", "Lottie", "Usability Testing"],
        experience_min_years=3,
        salary_min=25_000_000, salary_max=50_000_000,
        description="""## Product Designer (UX/UI) — Ứng dụng tiêu dùng MoMo

Đội Design MoMo đang tìm **Product Designer** có đam mê tạo ra trải nghiệm người dùng tuyệt vời cho ứng dụng ví điện tử được sử dụng nhiều nhất Việt Nam.

### Trách nhiệm

- Thiết kế trải nghiệm end-to-end cho các tính năng mới trên iOS và Android
- Thực hiện user research: phỏng vấn người dùng, usability testing, phân tích heatmap
- Tạo wireframe, mockup, và prototype chất lượng cao trên Figma
- Duy trì và mở rộng Design System của MoMo (component library)
- Phối hợp chặt với Product Manager và Engineering để đảm bảo thiết kế được implement đúng
- Tham gia design critique và critique của team

### Môi trường

Figma · FigJam · Lottie · Zeroheight · Hotjar · Maze · Amplitude""",
        requirements="""- Tối thiểu 3 năm kinh nghiệm Product Design cho mobile app (iOS/Android)
- Portfolio mạnh thể hiện quy trình UX từ research đến delivery
- Thành thạo Figma (auto layout, variants, prototyping)
- Hiểu biết về Material Design và Apple HIG
- Kỹ năng tư duy hệ thống: có thể thiết kế tái sử dụng và nhất quán
- Giao tiếp rõ ràng, có khả năng thuyết phục stakeholder bằng data""",
        benefits="""- Lương 25–50 triệu VNĐ/tháng
- Thiết bị cao cấp: MacBook Pro, màn hình 4K
- Budget thiết kế: Figma, Adobe CC, Maze license
- Conference: Awwwards, Design+Research, UX Festival
- WFH 2 ngày/tuần
- Cơ hội mentoring trực tiếp từ Design Lead có 10+ năm kinh nghiệm""",
        deadline_days=25,
    )

    # ---- KPMG Vietnam ----
    kpmg = orgs["kpmg-vietnam"]
    await _create_job(session, org=kpmg, posted_by=admin,
        title="Senior Associate — Transaction Advisory Services",
        language_code="en",
        location_city="Hồ Chí Minh",
        employment_type="full_time",
        required_skills=["Financial Modeling", "Due Diligence", "M&A", "Excel", "PowerPoint"],
        preferred_skills=["CFA", "ACCA", "Bloomberg", "Valuation"],
        experience_min_years=3,
        salary_min=35_000_000, salary_max=60_000_000,
        description="""## Senior Associate — Transaction Advisory Services (TAS)

KPMG Vietnam's Transaction Advisory Services practice advises leading private equity firms, strategic acquirers, and corporates on M&A transactions across Vietnam and the broader Southeast Asia region.

We are looking for a **Senior Associate** to join our growing TAS team in Ho Chi Minh City.

### What you will do

- Lead financial due diligence workstreams on buy-side and sell-side mandates
- Build and review detailed LBO, DCF, and comparable company analysis models
- Prepare and present transaction reports and management presentations
- Project-manage junior associates and coordinate with legal, tax, and commercial advisors
- Develop client relationships and contribute to pitch preparation
- Stay current on M&A market developments across target sectors: tech, healthcare, consumer, real estate

### Deal exposure

You'll work on live deals ranging from $10M to $500M+ enterprise value, with exposure to cross-border transactions involving PE sponsors and strategic acquirers from Japan, Singapore, and the US.""",
        requirements="""- 3–5 years of experience in investment banking, TAS, corporate finance, or Big 4 advisory
- Strong financial modelling skills (LBO, DCF, trading comps, accretion/dilution)
- CFA Level 1 or above preferred; ACCA/CPA also valued
- Excellent command of English (written and spoken; client-facing)
- High attention to detail and ability to manage multiple workstreams under tight deadlines
- Proficiency in Excel and PowerPoint; Bloomberg/Capital IQ is a plus""",
        benefits="""- Competitive salary 35–60M VND/month + deal bonus
- Global exposure through KPMG's international deal network
- Structured CFA/ACCA exam support and study leave
- Fast-track promotion path to Manager within 18–24 months for top performers
- KPMG global mobility opportunities (Singapore, Hong Kong, US secondments)
- Premium health and life insurance""",
        deadline_days=30,
    )

    await _create_job(session, org=kpmg, posted_by=admin,
        title="Data & Analytics Manager — Advisory",
        language_code="en",
        location_city="Hà Nội",
        employment_type="full_time",
        required_skills=["Data Analytics", "Python", "Power BI", "SQL", "Consulting"],
        preferred_skills=["Azure", "Databricks", "Statistics", "Digital Transformation"],
        experience_min_years=5,
        salary_min=60_000_000, salary_max=100_000_000,
        description="""## Manager, Data & Analytics — Advisory Practice

KPMG Vietnam's Advisory practice is expanding its Data & Analytics capability to meet increasing demand from large corporations and state-owned enterprises undergoing digital transformation.

As **Manager**, you will lead client engagements, develop practice methodology, and grow a team of analysts.

### Responsibilities

- Lead end-to-end analytics transformation engagements: strategy, architecture, implementation
- Design data governance frameworks and operating models for client organizations
- Oversee dashboard and reporting solution delivery (Power BI, Tableau)
- Contribute to business development: write proposals, present at pitches
- Hire, coach, and develop a team of 3–5 senior associates and analysts
- Build KPMG's data analytics thought leadership (articles, client events)

### Practice focus sectors

Banking & Capital Markets · Consumer & Retail · Healthcare · Energy & Natural Resources""",
        requirements="""- 5+ years in data analytics, BI, or data consulting; minimum 2 years at manager level
- Strong project management skills: capable of managing multiple client engagements simultaneously
- Technical depth in SQL, Python, and at least one BI tool (Power BI preferred)
- Cloud analytics exposure (Azure Synapse, Databricks, or AWS Redshift)
- Excellent English and Vietnamese communication; executive-level presentation skills
- Prior consulting or Big 4 experience preferred""",
        benefits="""- Salary 60–100M VND/month (Manager grade)
- Structured career path: Senior Manager, then Director within 3–4 years
- KPMG Learning & Development: in-house trainings, LinkedIn Learning, cloud certifications
- International assignment opportunities through KPMG Global Mobility
- Premium healthcare (Bảo Việt Platinum)
- Generous leave: 18 days annual leave + study leave""",
        deadline_days=45,
    )

    # ---- VinFast ----
    vinfast = orgs["vinfast"]
    await _create_job(session, org=vinfast, posted_by=admin,
        title="Kỹ sư Phần mềm Nhúng — Hệ thống ADAS",
        language_code="vi",
        location_city="Hải Phòng",
        employment_type="full_time",
        required_skills=["C", "C++", "Embedded Systems", "AUTOSAR", "CAN Bus"],
        preferred_skills=["MISRA-C", "FreeRTOS", "Simulink", "Python"],
        experience_min_years=3,
        salary_min=30_000_000, salary_max=60_000_000,
        description="""## Kỹ sư Phần mềm Nhúng — Hệ thống ADAS (Advanced Driver Assistance Systems)

VinFast đang xây dựng đội ngũ kỹ thuật ô tô điện đẳng cấp thế giới tại Việt Nam. Chúng tôi tìm kiếm **Kỹ sư Phần mềm Nhúng** tham gia dự án phát triển hệ thống ADAS cho dòng xe điện xuất khẩu thị trường Mỹ và châu Âu.

### Vai trò và trách nhiệm

- Phát triển và tích hợp phần mềm nhúng cho ECU (Electronic Control Unit) hệ thống ADAS
- Implement phần mềm giao tiếp qua giao thức CAN/CAN-FD, LIN, và Ethernet Automotive
- Tích hợp và test phần mềm theo tiêu chuẩn AUTOSAR Classic Platform
- Thực hiện kiểm thử HIL (Hardware-in-the-Loop) và SIL (Software-in-the-Loop)
- Phân tích và xử lý lỗi phát sinh từ field testing và validation
- Phối hợp với đội kỹ thuật quốc tế (Đức, Mỹ, Hàn Quốc)

### Yêu cầu môi trường phát triển

C/C++17 · AUTOSAR Classic · Vector CANoe · CANdb++ · MATLAB/Simulink · Jenkins · Git""",
        requirements="""**Bắt buộc:**
- Tối thiểu 3 năm kinh nghiệm lập trình nhúng (embedded C/C++)
- Hiểu biết về giao thức truyền thông automotive (CAN, CAN-FD, LIN)
- Kinh nghiệm với AUTOSAR Classic hoặc Adaptive Platform
- Kỹ năng debug phần cứng/phần mềm (oscilloscope, logic analyzer)

**Ưu tiên:**
- Kinh nghiệm với MISRA-C/C++ coding standard
- Hiểu biết về ISO 26262 (Functional Safety)
- Sử dụng được tiếng Anh kỹ thuật (đọc/viết tài liệu đặc tả)
- Kinh nghiệm với Simulink model-based design""",
        benefits="""- Lương cạnh tranh: 30–60 triệu VNĐ/tháng theo kinh nghiệm
- Thưởng hiệu suất hàng năm và thưởng dự án
- Bảo hiểm toàn diện: y tế, tai nạn, nhân thọ
- Hỗ trợ nhà ở và đi lại tại Hải Phòng (shuttle bus từ Hà Nội)
- Đào tạo và chứng chỉ AUTOSAR, ISO 26262 tại Đức
- Cơ hội công tác nước ngoài: Đức, Mỹ, Hàn Quốc
- Xe điện VinFast với giá ưu đãi cho CBNV""",
        deadline_days=35,
    )

    await _create_job(session, org=vinfast, posted_by=admin,
        title="Battery Management System (BMS) Software Engineer",
        language_code="en",
        location_city="Hải Phòng",
        employment_type="full_time",
        required_skills=["C", "C++", "Battery Systems", "Embedded Linux", "MATLAB"],
        preferred_skills=["Python", "ISO 26262", "CAN", "Simulink"],
        experience_min_years=2,
        salary_min=28_000_000, salary_max=55_000_000,
        description="""## BMS Software Engineer

VinFast's powertrain team is developing next-generation Battery Management System software for our VF 6, VF 8, and upcoming VF 9 models. Join us to build software that directly impacts range, safety, and charging performance for EVs on the road in the US and Europe.

### What you'll build

- BMS algorithms: State of Charge (SoC), State of Health (SoH), thermal management
- Cell balancing logic (passive and active) in embedded C on ARM Cortex-M7
- High-voltage safety interlocks and fault management routines
- CAN communication layer between BMS ECU and vehicle control module
- Automated test harnesses for HIL regression testing

### Tools & standards

C17 · ARM Cortex-M · FreeRTOS · MATLAB Simulink · Vector CANoe · ETAS INCA · ISO 26262 ASIL-B""",
        requirements="""- 2+ years experience in embedded software (C/C++) for automotive or industrial systems
- Understanding of battery electrochemistry and BMS architecture is a strong plus
- Comfortable writing safety-critical code with MISRA-C guidelines
- Experience with HIL/SIL testing frameworks
- English proficiency for working with international engineering teams (Bosch, LG Energy, CATL partners)""",
        benefits="""- Salary: 28–55M VND/month + annual bonus
- Overseas training at partner labs in Germany and South Korea
- Technical certification support (functional safety, AUTOSAR)
- Housing support + shuttle bus from Hanoi (90 min)
- VinFast EV purchase discount program""",
        deadline_days=30,
    )

    # ---- Vinmec ----
    vinmec = orgs["vinmec"]
    await _create_job(session, org=vinmec, posted_by=admin,
        title="Chuyên viên Công nghệ Y tế (Healthcare IT Specialist)",
        language_code="vi",
        location_city="Hà Nội",
        employment_type="full_time",
        required_skills=["HL7 FHIR", "SQL", "Python", "Hospital Information System"],
        preferred_skills=["AWS HealthLake", "Epic", "DICOM", "Power BI"],
        experience_min_years=2,
        salary_min=18_000_000, salary_max=35_000_000,
        description="""## Chuyên viên Công nghệ Y tế — Bộ phận Chuyển đổi Số

Vinmec International Hospital đang đẩy mạnh chiến lược số hóa vận hành bệnh viện và nâng cao trải nghiệm bệnh nhân. Chúng tôi cần **Chuyên viên Công nghệ Y tế** để triển khai và tích hợp các hệ thống HIS, LIS, và dữ liệu sức khỏe theo chuẩn quốc tế.

### Nhiệm vụ

- Quản lý và tích hợp dữ liệu giữa các hệ thống HIS (Hospital Information System), LIS, PACS
- Triển khai và vận hành chuẩn HL7 FHIR cho trao đổi dữ liệu y tế
- Xây dựng dashboard theo dõi chất lượng dịch vụ và KPI bệnh viện
- Phối hợp với bác sĩ, điều dưỡng, và kế toán để số hóa quy trình vận hành
- Hỗ trợ triển khai app chăm sóc sức khỏe cho bệnh nhân
- Đảm bảo tuân thủ quy định bảo mật dữ liệu y tế (HIPAA-aligned)

### Môi trường

Oracle HIS · HL7 FHIR R4 · Python · PostgreSQL · Power BI · AWS HealthLake""",
        requirements="""- Tốt nghiệp đại học chuyên ngành Công nghệ thông tin Y tế, CNTT, Điện tử Y sinh
- Tối thiểu 2 năm kinh nghiệm làm việc tại môi trường bệnh viện hoặc cơ sở y tế
- Có kiến thức về chuẩn HL7 FHIR, ICD-10, hoặc DICOM
- Thành thạo SQL; có kinh nghiệm Python là lợi thế
- Giao tiếp tốt với đội ngũ y khoa và kỹ thuật
- Đọc hiểu tài liệu chuyên môn bằng tiếng Anh""",
        benefits="""- Lương 18–35 triệu VNĐ/tháng
- Khám chữa bệnh miễn phí và ưu đãi cho thân nhân tại Vinmec
- Bảo hiểm sức khỏe toàn diện
- Môi trường bệnh viện quốc tế JCI, cơ sở vật chất hiện đại
- Cơ hội đào tạo tại bệnh viện đối tác Mỹ (Mayo Clinic, Partners HealthCare)
- Tham gia hội nghị y tế quốc tế hàng năm""",
        deadline_days=20,
    )

    # ---- SSI Securities ----
    ssi = orgs["ssi-securities"]
    await _create_job(session, org=ssi, posted_by=admin,
        title="Quantitative Analyst — Derivatives & Structured Products",
        language_code="en",
        location_city="Hồ Chí Minh",
        employment_type="full_time",
        required_skills=["Python", "Quantitative Finance", "Statistics", "Derivatives", "Excel VBA"],
        preferred_skills=["R", "MATLAB", "Bloomberg", "CFA", "FRM"],
        experience_min_years=2,
        salary_min=35_000_000, salary_max=70_000_000,
        description="""## Quantitative Analyst — Derivatives & Structured Products

SSI Securities Corporation is Vietnam's leading brokerage by charter capital. Our Derivatives & Structured Products desk is building quantitative capabilities to serve institutional and high-net-worth clients as Vietnam's derivatives market expands.

### What you will work on

- Develop and backtest pricing models for equity-linked structured notes, covered warrants, and VN30F futures strategies
- Build automated risk management tools: Greeks calculation, scenario analysis, VaR
- Analyze market microstructure and liquidity patterns in the Vietnamese stock market
- Produce quantitative research notes for institutional clients
- Support new product development for SSI's fund management affiliate (SSI AM)

### Data environment

Bloomberg Terminal · Python (pandas, scipy, statsmodels, cvxpy) · Excel/VBA · SSI proprietary trading data""",
        requirements="""- 2+ years experience in quantitative finance, risk management, or derivatives pricing
- Strong mathematical background: probability, stochastic calculus, statistics
- Solid Python skills for data analysis and model implementation
- Understanding of options pricing (Black-Scholes, Monte Carlo, binomial trees)
- CFA Level 1 or FRM Part 1 completed; further progress is a plus
- Bloomberg Terminal proficiency
- Excellent English for research writing and institutional client communication""",
        benefits="""- Salary 35–70M VND/month + annual performance bonus
- Access to Bloomberg Terminal and premium data providers
- SSI Securities' employee trading account with reduced commissions
- CFA/FRM exam sponsorship and study leave
- Structured mentoring from senior traders and portfolio managers
- Annual overseas training at partner institutions (Singapore, Hong Kong)""",
        deadline_days=30,
    )

    # ---- Axon Active ----
    axon = orgs["axon-active"]
    await _create_job(session, org=axon, posted_by=admin,
        title="Agile Coach / Scrum Master (Senior)",
        language_code="en",
        location_city="Hồ Chí Minh",
        employment_type="full_time",
        required_skills=["Agile", "Scrum", "Coaching", "Facilitation", "Kanban"],
        preferred_skills=["SAFe", "LeSS", "OKR", "DevOps"],
        experience_min_years=4,
        salary_min=35_000_000, salary_max=65_000_000,
        description="""## Senior Agile Coach / Scrum Master

Axon Active is a Swiss software company running Agile development centers in Vietnam. We are looking for a **Senior Agile Coach** to help our engineering squads and Swiss clients achieve high performance through genuine Agile mastery — not Agile theater.

### About the role

You'll work with 3–4 product squads simultaneously, coaching teams and embedding Agile principles in the culture, not just the ceremonies.

### Day-to-day responsibilities

- Facilitate sprint planning, daily standups, reviews, and retrospectives across multiple squads
- Coach product owners in effective backlog management and story mapping
- Support the leadership team in adopting portfolio-level Agile (OKRs, PI Planning)
- Identify and remove systemic impediments through servant leadership
- Train new Scrum Masters and junior agile practitioners
- Partner with Swiss clients on remote ceremony facilitation (in German or English)
- Evaluate and introduce relevant practices: Shape Up, Kanban, dual-track discovery

### Team

You'll report to the VP of Engineering and work alongside our Center of Excellence for Agile Practices.""",
        requirements="""- 4+ years as a Scrum Master or Agile Coach in a software development environment
- Certified Scrum Master (CSM, PSM I) required; PSM II, CSP, or ICP-ACC preferred
- Experience coaching distributed or cross-cultural teams
- Facilitation skills: able to run effective workshops for 30+ people
- Comfortable using Jira, Confluence, and Miro
- Excellent English; German is a significant plus (Swiss client-facing)
- Track record of measurable improvement in team delivery metrics""",
        benefits="""- Salary 35–65M VND/month
- Annual performance bonus
- Paid certification: PSM II, ICP-ACC, SAFe SPC
- 10 days dedicated personal development time per year
- Annual company trip (Europe rotation)
- English + German language courses sponsored""",
        deadline_days=35,
    )

    await _create_job(session, org=axon, posted_by=admin,
        title="iOS Developer (Swift / SwiftUI)",
        language_code="en",
        location_city="Hồ Chí Minh",
        employment_type="full_time",
        required_skills=["Swift", "SwiftUI", "UIKit", "Xcode", "REST APIs"],
        preferred_skills=["Combine", "Core Data", "ARKit", "WidgetKit"],
        experience_min_years=3,
        salary_min=30_000_000, salary_max=55_000_000,
        description="""## iOS Developer — Swiss Client Squad

Axon Active's Ho Chi Minh City office is building iOS applications for Swiss enterprise clients in healthcare, logistics, and insurance. You'll work in a co-located squad of 5–6 engineers collaborating daily with a Swiss product owner via video call.

### Tech responsibilities

- Build feature-rich iOS apps using Swift and SwiftUI; maintain legacy UIKit screens
- Implement offline-first sync using Core Data / CloudKit
- Integrate with RESTful backends and push notification services (APNs, Firebase)
- Submit and manage apps through App Store Connect, handle review processes
- Write unit and snapshot tests with XCTest and Quick/Nimble

### Notable project

You'll join the squad delivering a field-operations app used by Swiss railway engineers for real-time infrastructure inspection (30,000+ MAU).""",
        requirements="""- 3+ years professional iOS development with Swift
- Strong SwiftUI fundamentals (declarative layouts, animations, NavigationStack)
- Familiarity with Combine or async/await for reactive data flows
- Understanding of iOS memory management, performance profiling (Instruments)
- English fluency for daily collaboration with Swiss stakeholders
- Clean code habits and unit testing discipline""",
        benefits="""- Salary 30–55M VND/month
- MacBook Pro + iPhone (latest) provided
- Annual performance review with 10–15% salary increments
- WWDC livestream access and Apple Developer Program subscription
- 15 days annual leave + company retreat abroad""",
        deadline_days=25,
    )

    # ---- Vietnam Airlines ----
    vna = orgs["vietnam-airlines"]
    await _create_job(session, org=vna, posted_by=admin,
        title="Chuyên viên Hệ thống Bán vé & Đặt chỗ (GDS Systems)",
        language_code="vi",
        location_city="Hà Nội",
        employment_type="full_time",
        required_skills=["Amadeus", "SQL", "API Integration", "Airline Systems"],
        preferred_skills=["Python", "NDC", "IATA standards", "Sabre"],
        experience_min_years=2,
        salary_min=20_000_000, salary_max=38_000_000,
        description="""## Chuyên viên Hệ thống Bán vé & Đặt chỗ (GDS/PSS)

Vietnam Airlines tuyển dụng **Chuyên viên Hệ thống** tham gia đội phụ trách vận hành và tích hợp hệ thống bán vé qua GDS (Amadeus Altéa) và kênh trực tiếp (NDC API).

### Mô tả công việc

- Vận hành và hỗ trợ kỹ thuật cho hệ thống đặt chỗ Amadeus Altéa PSS
- Phân tích và xử lý các vấn đề kỹ thuật liên quan đến đặt chỗ, xuất vé, reissue, refund
- Xây dựng và kiểm thử tích hợp API với các đại lý OTA (Booking.com, Expedia, Klook)
- Hỗ trợ triển khai tiêu chuẩn IATA NDC cho kênh phân phối trực tiếp
- Viết tài liệu kỹ thuật và hướng dẫn nghiệp vụ bằng tiếng Anh
- Phối hợp với Amadeus và IATA trong các dự án nâng cấp hệ thống""",
        requirements="""- Tốt nghiệp đại học chuyên ngành Công nghệ thông tin, Quản trị hàng không, hoặc liên quan
- Có kinh nghiệm 2+ năm với hệ thống GDS (Amadeus, Sabre, hoặc Galileo)
- Hiểu biết về quy trình bán vé, đặt chỗ, xuất vé hàng không (IATA standard)
- Thành thạo SQL để truy vấn và xử lý dữ liệu đặt chỗ
- Giao tiếp tiếng Anh tốt (làm việc với đối tác quốc tế)
- Tư duy phân tích và xử lý sự cố nhanh chóng""",
        benefits="""- Lương 20–38 triệu VNĐ/tháng + thưởng hiệu suất
- Quyền lợi nhân viên hàng không: vé máy bay ưu đãi cho bản thân và gia đình
- Bảo hiểm sức khỏe toàn diện
- Đào tạo Amadeus certification tại Singapore hoặc Pháp
- Môi trường làm việc quốc tế tại trụ sở 200 Nguyễn Sơn, Hà Nội
- Cơ hội thăng tiến lên Chuyên viên Chính / Trưởng nhóm sau 3–5 năm""",
        deadline_days=30,
    )

    # ---- The Coffee House ----
    tch = orgs["the-coffee-house"]
    await _create_job(session, org=tch, posted_by=admin,
        title="Software Engineer — Platform & Internal Tools",
        language_code="en",
        location_city="Hồ Chí Minh",
        employment_type="full_time",
        required_skills=["Node.js", "TypeScript", "PostgreSQL", "REST APIs", "React"],
        preferred_skills=["GraphQL", "Redis", "Docker", "Kafka"],
        experience_min_years=2,
        salary_min=22_000_000, salary_max=40_000_000,
        description="""## Software Engineer — Platform & Internal Tools

The Coffee House is Vietnam's leading tech-forward coffee chain. Our engineering team builds the systems that power ordering, loyalty, inventory, and supply chain across 160+ stores.

We're looking for a **Software Engineer** to join the Platform team building internal tools and integrations that keep the business running smoothly.

### What you'll build

- Internal admin portal for store operations, promotions, and inventory management
- Integrations with POS systems (PAX), payment gateways (VNPAY, VNPay QR), and food delivery platforms (GrabFood, ShopeeFood)
- Event-driven microservices for real-time inventory updates and order routing
- Public APIs consumed by our iOS and Android apps (2M+ downloads)
- Internal analytics tooling powered by our data lakehouse

### Stack

Node.js (Fastify) · TypeScript · PostgreSQL · Redis · Kafka · React (internal admin) · Docker · Kubernetes · Datadog""",
        requirements="""- 2+ years professional experience with Node.js and TypeScript
- Solid PostgreSQL skills; experience with query optimization
- Familiarity with event-driven architectures and message queues
- Experience building and consuming REST APIs
- Good understanding of software design principles (SOLID, DRY, YAGNI)
- English proficiency for code reviews and technical documentation""",
        benefits="""- Salary 22–40M VND/month
- The Coffee House allowance: 300K VND/month drinks credit
- Flexible work: 2 days WFH per week
- MacBook for all engineers
- Annual performance bonus
- Exposure to interesting scale: 100k+ orders per day, millions of loyalty points""",
        deadline_days=28,
    )

    await _create_job(session, org=tch, posted_by=admin,
        title="Chuyên viên Phân tích Kinh doanh (Business Analyst)",
        language_code="vi",
        location_city="Hồ Chí Minh",
        employment_type="full_time",
        required_skills=["Business Analysis", "SQL", "Agile", "Requirements", "Wireframing"],
        preferred_skills=["Figma", "BPMN", "Python", "Data Analysis"],
        experience_min_years=2,
        salary_min=18_000_000, salary_max=30_000_000,
        description="""## Chuyên viên Phân tích Kinh doanh (BA) — The Coffee House Tech

Đội Công nghệ của The Coffee House tìm kiếm **Business Analyst** để cầu nối giữa business stakeholders và đội phát triển sản phẩm.

### Công việc cụ thể

- Thu thập và phân tích yêu cầu nghiệp vụ từ các phòng ban: Operations, Marketing, Finance
- Viết User Stories rõ ràng, Acceptance Criteria, và Process Flow diagram
- Tham gia sprint planning, refinement session với đội engineering
- Phân tích dữ liệu vận hành để xác định điểm nghẽn và cơ hội cải thiện
- Hỗ trợ UAT (User Acceptance Testing) và training người dùng cuối
- Theo dõi KPI sau triển khai và đề xuất cải tiến

### Môi trường sản phẩm

Bạn sẽ làm việc trực tiếp trên hệ sinh thái sản phẩm: mobile app đặt hàng, hệ thống POS, chương trình loyalty Stars, và dashboard vận hành chuỗi cửa hàng.""",
        requirements="""- Tối thiểu 2 năm kinh nghiệm BA trong môi trường tech/startup/F&B
- Thành thạo SQL để tự truy vấn dữ liệu khi cần phân tích
- Có kinh nghiệm viết User Stories và vẽ process flow (BPMN, Lucidchart, Figma)
- Kỹ năng giao tiếp và thuyết phục tốt với cả technical và non-technical stakeholder
- Quen thuộc với Agile Scrum và JIRA
- Đọc hiểu tài liệu kỹ thuật bằng tiếng Anh""",
        benefits="""- Lương 18–30 triệu VNĐ/tháng
- The Coffee House drink allowance 300K/tháng
- Hybrid: 3 ngày office, 2 ngày remote
- Đào tạo chứng chỉ BA: IIBA CBAP, PMI-PBA
- Startup culture: move fast, own your work
- Canteen nội bộ và snack miễn phí""",
        deadline_days=20,
    )

    # ---- Additional intern/entry-level roles for student appeal ----

    await _create_job(session, org=fpt, posted_by=partner,
        title="Software Engineering Intern (Backend / Python)",
        language_code="en",
        location_city="Hà Nội",
        employment_type="internship",
        location_type="onsite",
        required_skills=["Python", "REST APIs", "SQL", "Git"],
        preferred_skills=["FastAPI", "Docker", "PostgreSQL"],
        experience_min_years=0,
        salary_min=4_000_000, salary_max=8_000_000,
        description="""## Software Engineering Intern — Backend (Python)

FPT Software offers a structured internship program for final-year students interested in backend development. Interns work on real production features alongside experienced engineers, not just internal tools.

### What you'll do during 3–6 months

- Build and test REST API endpoints in Python (FastAPI/Django REST)
- Write SQL queries and basic database design under mentorship
- Participate in daily standups and sprint ceremonies
- Contribute to 1–2 real product features shipped to production
- Attend bi-weekly technical talks by senior engineers

### Perfect for

Final-year students in Computer Science, Software Engineering, or Information Technology. We prefer candidates who have built at least one personal project.""",
        requirements="""- Currently enrolled in a Bachelor's program (graduating 2025–2026)
- Solid Python fundamentals (functions, OOP, standard library)
- Basic SQL knowledge (SELECT, JOIN, GROUP BY)
- Familiarity with Git version control
- Curiosity to learn and willingness to ask questions
- Can commit to at least 4 days/week for the internship period""",
        benefits="""- Allowance: 4–8M VND/month (based on academic year and skills)
- Mentoring from a dedicated senior engineer
- FPT Learning Platform access during internship
- Return offer for top performers (full-time position)
- Certificate of completion and LinkedIn reference letter
- Free shuttle from Cầu Giấy metro station to campus""",
        deadline_days=15,
    )

    await _create_job(session, org=momo, posted_by=admin,
        title="Business Development Intern — Merchant Partnership",
        language_code="vi",
        location_city="Hồ Chí Minh",
        employment_type="internship",
        location_type="onsite",
        required_skills=["Communication", "Excel", "Market Research", "Business Development"],
        preferred_skills=["PowerPoint", "CRM", "Sales", "Data Analysis"],
        experience_min_years=0,
        salary_min=4_000_000, salary_max=6_000_000,
        description="""## Thực tập sinh Business Development — Merchant Partnership

MoMo tuyển **Thực tập sinh BD** tham gia đội phát triển đối tác thương nhân — nhóm chịu trách nhiệm mở rộng mạng lưới điểm thanh toán MoMo trên toàn quốc.

### Bạn sẽ làm gì?

- Nghiên cứu thị trường và xác định merchant tiềm năng trong các lĩnh vực: F&B, bán lẻ, giáo dục
- Hỗ trợ team trong cold-calling, pitch deck preparation, và follow-up với merchant
- Tracking pipeline deals trên CRM và báo cáo tiến độ hàng tuần
- Phân tích dữ liệu GMV theo ngành và đề xuất chiến lược tiếp cận
- Tham gia các buổi partner event và demo MoMo cho merchant

### Đây là internship dành cho ai?

Sinh viên năm 3–4 các ngành Quản trị Kinh doanh, Marketing, Kinh tế, hoặc bất kỳ ngành nào có niềm đam mê với sales và startup fintech.""",
        requirements="""- Sinh viên đại học (năm 3 trở lên), tốt nghiệp trước tháng 12/2026
- Giao tiếp tự tin, không ngại cold outreach và gặp gỡ khách hàng
- Thành thạo Excel cơ bản (pivot table, VLOOKUP)
- Đọc hiểu tiếng Anh ở mức cơ bản
- Cam kết 5 ngày/tuần trong ít nhất 3 tháng""",
        benefits="""- Phụ cấp 4–6 triệu VNĐ/tháng
- MoMo voucher hàng tháng
- Mentoring trực tiếp từ BD Manager có 5+ năm kinh nghiệm fintech
- Trải nghiệm môi trường startup tốc độ cao
- Return offer cho thực tập sinh xuất sắc
- Văn phòng đẹp tại GreenPark, Q.10""",
        deadline_days=15,
    )

    await _create_job(session, org=ssi, posted_by=admin,
        title="Internship — Investment Research (Equity)",
        language_code="en",
        location_city="Hà Nội",
        employment_type="internship",
        location_type="onsite",
        required_skills=["Financial Analysis", "Excel", "Research", "Accounting"],
        preferred_skills=["Bloomberg", "Python", "CFA Level 1", "Valuation"],
        experience_min_years=0,
        salary_min=5_000_000, salary_max=8_000_000,
        description="""## Internship — Equity Research

SSI Securities' Research Division is offering a structured 3-month internship for high-caliber undergraduates interested in equity research and financial markets.

### Program structure

**Month 1:** Foundation — financial statement analysis, sector mapping, Bloomberg Terminal training

**Month 2:** Deep-dive — build a financial model for one coverage company under analyst supervision

**Month 3:** Output — co-author one sector initiation note published to institutional clients

### Who this internship is for

Final-year students in Finance, Accounting, Economics, or Business who want to break into the sell-side research career track.""",
        requirements="""- Strong academic record (GPA ≥ 3.0/4.0 or equivalent)
- Solid accounting and financial statement analysis skills
- Excel proficiency (financial modelling basics is a plus)
- CFA Level 1 registered or passed is a strong differentiator
- English proficiency: research notes are written in English
- Available full-time (5 days/week) for 3 months""",
        benefits="""- Allowance: 5–8M VND/month
- Bloomberg Terminal training certificate
- Co-authorship credit on published research note
- Priority consideration for full-time analyst roles
- Mentoring by CFA charterholder research analysts""",
        deadline_days=20,
    )

    print("  [create] jobs seeded across all companies")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False, pool_pre_ping=True)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)  # type: ignore[call-overload]

    async with async_session() as session:
        async with session.begin():
            await seed_locations_into_session(session)
            await seed_industries_into_session(session)
            users = await seed_users(session)
            orgs = await seed_organisations(session, users)
            await seed_onboarding_state(session, users=users, orgs=orgs)
            await seed_jobs(session, orgs, users)
            await enrich_marketplace_seed(session, orgs=orgs, users=users)

    await engine.dispose()
    print("\n[done] Seed completed successfully.")
    print("\nTest accounts (password: 123456):")
    print("  student@vinuni.edu.vn          — Student VinUni")
    print("  data.student@vinuni.edu.vn     — Student VinUni / data profile")
    print("  business.student@vinuni.edu.vn — Student VinUni / business profile")
    print("  student@gmail.com              — External student")
    print("  alumni@vinuni.edu.vn           — Alumni")
    print("  partner@gmail.com              — FPT partner Admin")
    print("  recruiter.fpt@example.com      — FPT Recruiter")
    print("  hiring.fpt@example.com         — FPT Hiring Manager")
    print("  finance.fpt@example.com        — FPT Finance")
    print("  recruiter.vcb@example.com      — Vietcombank Recruiter")
    print("  recruiter.momo@example.com     — MoMo Recruiter")
    print("  career.admin@vinuni.edu.vn     — University Career Center Admin")
    print("  career.coach@vinuni.edu.vn     — University Career Coach")
    print("  moderator@vinuni.edu.vn        — University Moderation Officer")
    print("  ai.ops@vinuni.edu.vn           — University AI/Billing Ops")
    print("  admin@vinuni.com               — Platform Superadmin")


if __name__ == "__main__":
    asyncio.run(main())
