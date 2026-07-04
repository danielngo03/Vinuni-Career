"""Shared helpers for student-profile tests."""

from __future__ import annotations

import uuid

from app.modules.student_profiles.application import profile_service, section_service
from app.shared.permissions import Principal
from sqlalchemy.ext.asyncio import AsyncSession

from tests.auth_utils import CTX


async def add_education(
    session: AsyncSession, *, principal: Principal, institution: str = "VinUniversity"
) -> dict:
    return await section_service.create_item(
        session,
        kind="education",
        principal=principal,
        payload={
            "institution": institution,
            "degree": "BSc Computer Science",
            "field_of_study": "CS",
            "start_date": "2022-09-01",
            "end_date": "2026-06-01",
        },
        ctx=CTX,
    )


async def add_experience(
    session: AsyncSession, *, principal: Principal, company: str = "Example Tech"
) -> dict:
    return await section_service.create_item(
        session,
        kind="experience",
        principal=principal,
        payload={
            "company_name": company,
            "title": "Software Intern",
            "employment_type": "internship",
            "start_date": "2024-06-01",
        },
        ctx=CTX,
    )


async def add_skill(session: AsyncSession, *, principal: Principal, name: str) -> dict:
    return await section_service.create_item(
        session,
        kind="skill",
        principal=principal,
        payload={"name": name, "category": "technical", "proficiency": 4},
        ctx=CTX,
    )


async def add_link(
    session: AsyncSession, *, principal: Principal, url: str = "https://github.com/me"
) -> dict:
    return await section_service.create_item(
        session,
        kind="link",
        principal=principal,
        payload={"label": "GitHub", "url": url},
        ctx=CTX,
    )


async def get_profile_id(session: AsyncSession, *, principal: Principal) -> uuid.UUID:
    me = await profile_service.get_my_profile(session, principal=principal)
    return uuid.UUID(me["id"])
