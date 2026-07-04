"""Cross-module interface: structured profile data for CV ``profile_import``.

The ``documents`` module's ``creation_mode=profile_import`` builds a CV from the
student's structured profile. To respect module boundaries (no cross-module
implementation imports), ``documents`` calls THIS application function, which
returns plain CV-section specs in the exact shape the documents seeder consumes
(``section_type`` / ``title`` / ``sort_order`` / ``content_json={'items': [...]}``).

Returns ``None`` when the user has no profile yet, so the documents module can
fall back to its minimal name/email seed.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.student_profiles.application import _shared, loaders


def _iso(value) -> str | None:
    return value.isoformat() if value else None


async def build_cv_import_sections(
    session: AsyncSession, *, user_id: uuid.UUID, notes: str | None = None
) -> list[dict] | None:
    """Build populated CV section specs from the user's structured profile."""

    profile = await _shared.load_profile_by_user(session, user_id=user_id)
    if profile is None:
        return None

    educations = await loaders.load_education(session, student_id=profile.id)
    experiences = await loaders.load_experience(session, student_id=profile.id)
    skills = await loaders.load_skills(session, student_id=profile.id)

    summary_items: list[dict] = []
    if profile.headline:
        summary_items.append({"text": profile.headline})
    if profile.summary:
        summary_items.append({"text": profile.summary})
    if notes:
        summary_items.append({"text": notes})

    education_items = [
        {
            "institution": e.institution,
            "degree": e.degree,
            "field_of_study": e.field_of_study,
            "start_date": _iso(e.start_date),
            "end_date": _iso(e.end_date),
            "is_current": e.is_current,
            "description": e.description,
        }
        for e in educations
    ]
    experience_items = [
        {
            "company_name": x.company_name,
            "title": x.title,
            "employment_type": x.employment_type,
            "location": x.location,
            "start_date": _iso(x.start_date),
            "end_date": _iso(x.end_date),
            "is_current": x.is_current,
            "description": x.description,
            "skills_used": list(x.skills_used or []),
        }
        for x in experiences
    ]
    skill_items = [
        {"name": s.name, "category": s.category, "proficiency": s.proficiency}
        for s in skills
    ]

    return [
        {
            "section_type": "summary",
            "title": "Summary",
            "sort_order": 10,
            "content_json": {"items": summary_items},
            "is_visible": True,
        },
        {
            "section_type": "education",
            "title": "Education",
            "sort_order": 20,
            "content_json": {"items": education_items},
            "is_visible": True,
        },
        {
            "section_type": "experience",
            "title": "Experience",
            "sort_order": 30,
            "content_json": {"items": experience_items},
            "is_visible": True,
        },
        {
            "section_type": "skills",
            "title": "Skills",
            "sort_order": 50,
            "content_json": {"items": skill_items},
            "is_visible": True,
        },
    ]
