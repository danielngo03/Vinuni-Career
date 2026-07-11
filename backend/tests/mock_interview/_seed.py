"""Shared seeding helpers for mock-interview integration tests.

Reuses the existing documents / opportunities / org factories rather than
inventing new seeding: a verified STUDENT, a PUBLIC (approved) job, and a READY
CV with real, JD-matching section content so grounding has a selectable CV.
"""

from __future__ import annotations

import uuid

from app.modules.documents.domain.models import CvProfile, CvSection
from app.modules.opportunities.application import job_service, moderation_service
from app.shared.permissions import Principal
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.auth_utils import CTX
from tests.documents_utils import make_ready_cv
from tests.org_utils import make_org_with_admin


def job_payload(**over: object) -> dict:
    base: dict = {
        "title": "Backend Intern",
        "description": "We are hiring a backend intern to build REST APIs.",
        "requirements": "Experience with Python and FastAPI is required.",
        "benefits": None,
        "employment_type": "internship",
        "location_type": "onsite",
        "location_city": "Hanoi",
        "location_country": "Vietnam",
        "required_skills": ["Python", "FastAPI"],
        "preferred_skills": ["PostgreSQL"],
        "experience_min_years": None,
        "experience_max_years": None,
        "degree_required": None,
        "salary_min": None,
        "salary_max": None,
        "salary_currency": "VND",
        "salary_is_disclosed": False,
        "headcount": 1,
        "application_deadline": None,
        "visibility": "public",
    }
    base.update(over)
    return base


async def make_public_job(db: AsyncSession, *, publish: bool = True, **over: object) -> uuid.UUID:
    """Create a partner job and (by default) approve it into public visibility."""

    _u, _org, admin = await make_org_with_admin(db)
    _uu, _uorg, uni = await make_org_with_admin(db, org_type="university")
    created = await job_service.create_job(
        db, principal=admin, payload=job_payload(**over), ctx=CTX
    )
    jid = uuid.UUID(created["id"])
    if publish:
        await job_service.submit_job(db, principal=admin, job_id=jid, ctx=CTX)
        await moderation_service.approve_job(db, principal=uni, job_id=jid, ctx=CTX)
    return jid


async def _seed_section(db: AsyncSession, cv_id: str, section_type: str, items: list[dict]) -> None:
    cv = (
        await db.execute(select(CvProfile).where(CvProfile.id == uuid.UUID(cv_id)))
    ).scalar_one()
    sections = (
        (await db.execute(select(CvSection).where(CvSection.cv_id == uuid.UUID(cv_id))))
        .scalars()
        .all()
    )
    target = next(s for s in sections if s.section_type == section_type)
    target.content_json = {"items": items}
    cv.version += 1
    await db.commit()


async def make_strong_cv(db: AsyncSession, student: Principal, *, title: str = "Strong CV") -> str:
    """A finalized, ready CV whose content matches the seeded job's JD."""

    cv = await make_ready_cv(db, student=student, title=title)
    await _seed_section(
        db, cv["id"], "skills", [{"text": "Python, FastAPI, PostgreSQL, SQL"}]
    )
    await _seed_section(
        db,
        cv["id"],
        "experience",
        [{"text": "Built REST APIs with Python and FastAPI at a startup."}],
    )
    await _seed_section(db, cv["id"], "summary", [{"text": "Backend engineering intern."}])
    await _seed_section(
        db, cv["id"], "education", [{"text": "BSc Computer Science, VinUniversity."}]
    )
    return str(cv["id"])
