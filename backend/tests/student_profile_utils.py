"""Shared helpers for identity-only student-profile tests."""

from __future__ import annotations

import uuid

from app.modules.student_profiles.application import profile_service
from app.shared.permissions import Principal
from sqlalchemy.ext.asyncio import AsyncSession


async def get_profile_id(session: AsyncSession, *, principal: Principal) -> uuid.UUID:
    me = await profile_service.get_my_profile(session, principal=principal)
    return uuid.UUID(me["id"])
