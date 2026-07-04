"""Repository for the singleton ``platform_settings`` platform row."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.platform_settings.domain.models import PLATFORM_SCOPE, PlatformSettings


async def get_platform(session: AsyncSession) -> PlatformSettings | None:
    return (
        await session.execute(
            select(PlatformSettings).where(PlatformSettings.scope == PLATFORM_SCOPE)
        )
    ).scalar_one_or_none()


async def get_or_create_platform(session: AsyncSession) -> PlatformSettings:
    row = await get_platform(session)
    if row is not None:
        return row
    row = PlatformSettings(scope=PLATFORM_SCOPE)
    session.add(row)
    await session.flush()
    return row
