"""Child-collection loaders + completion recompute (shared by the services).

Kept separate from the request-handling services so both the core profile service
and the section CRUD service refresh the completion cache through one code path.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.student_profiles.domain import completion
from app.modules.student_profiles.domain.models import (
    StudentEducation,
    StudentExperience,
    StudentLink,
    StudentProfile,
    StudentSkill,
)


async def load_education(
    session: AsyncSession, *, student_id: uuid.UUID
) -> list[StudentEducation]:
    return list(
        (
            await session.execute(
                select(StudentEducation)
                .where(
                    StudentEducation.student_id == student_id,
                    StudentEducation.deleted_at.is_(None),
                )
                .order_by(StudentEducation.sort_order, StudentEducation.created_at)
            )
        ).scalars().all()
    )


async def load_experience(
    session: AsyncSession, *, student_id: uuid.UUID
) -> list[StudentExperience]:
    return list(
        (
            await session.execute(
                select(StudentExperience)
                .where(
                    StudentExperience.student_id == student_id,
                    StudentExperience.deleted_at.is_(None),
                )
                .order_by(StudentExperience.sort_order, StudentExperience.created_at)
            )
        ).scalars().all()
    )


async def load_skills(
    session: AsyncSession, *, student_id: uuid.UUID
) -> list[StudentSkill]:
    return list(
        (
            await session.execute(
                select(StudentSkill)
                .where(
                    StudentSkill.student_id == student_id,
                    StudentSkill.deleted_at.is_(None),
                )
                .order_by(StudentSkill.sort_order, StudentSkill.name)
            )
        ).scalars().all()
    )


async def load_links(
    session: AsyncSession, *, student_id: uuid.UUID
) -> list[StudentLink]:
    return list(
        (
            await session.execute(
                select(StudentLink)
                .where(
                    StudentLink.student_id == student_id,
                    StudentLink.deleted_at.is_(None),
                )
                .order_by(StudentLink.sort_order, StudentLink.created_at)
            )
        ).scalars().all()
    )


async def _count(session: AsyncSession, model, student_id: uuid.UUID) -> int:
    return (
        await session.execute(
            select(func.count())
            .select_from(model)
            .where(model.student_id == student_id, model.deleted_at.is_(None))
        )
    ).scalar_one()


async def recompute_completion(
    session: AsyncSession, *, profile: StudentProfile
) -> int:
    """Recompute and persist the completion cache; returns the new value."""

    edu = await _count(session, StudentEducation, profile.id)
    exp = await _count(session, StudentExperience, profile.id)
    skills = await _count(session, StudentSkill, profile.id)
    links = await _count(session, StudentLink, profile.id)

    inputs = completion.CompletionInputs(
        has_headline=bool(profile.headline and profile.headline.strip()),
        has_summary=bool(profile.summary and profile.summary.strip()),
        education_count=edu,
        experience_count=exp,
        skill_count=skills,
        link_count=links,
        open_to_work_configured=bool(
            profile.is_open_to_work and (profile.open_to_work_types or [])
        ),
    )
    profile.profile_completion = completion.compute(inputs)
    return profile.profile_completion
