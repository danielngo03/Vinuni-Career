"""Cross-module read facade: a student's safe avatar URL by ``user_id``.

Recruitment (and any other cross-module partner surface) needs the applicant's
identifying photo as a SAFE serve pointer — never the raw ``avatar_path`` storage
key. This facade batch-resolves ``{user_id: avatar_url}`` from ``student_profiles``
so the caller stays decoupled from the profile ORM and the storage layout. A user
with no profile or no uploaded avatar is simply absent from the result.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.student_profiles.domain.models import StudentProfile


def _avatar_url(profile_id: uuid.UUID, version: int) -> str:
    base = get_settings().app_url.rstrip("/")
    return f"{base}/api/v1/students/{profile_id}/avatar?v={version}"


async def avatar_urls_for(
    session: AsyncSession, user_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, str]:
    """Batch-resolve ``{user_id: avatar_url}`` (only for users with an avatar)."""

    ids = {i for i in user_ids if i is not None}
    if not ids:
        return {}
    rows = (
        await session.execute(
            select(
                StudentProfile.user_id,
                StudentProfile.id,
                StudentProfile.version,
                StudentProfile.avatar_path,
            ).where(
                StudentProfile.user_id.in_(ids),
                StudentProfile.deleted_at.is_(None),
            )
        )
    ).all()
    out: dict[uuid.UUID, str] = {}
    for user_id, profile_id, version, avatar_path in rows:
        if avatar_path:
            out[user_id] = _avatar_url(profile_id, version)
    return out
