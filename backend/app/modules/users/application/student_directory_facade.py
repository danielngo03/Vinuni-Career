"""Display-only user identity facade for cross-module surfaces.

`reviews` resolves a non-anonymous review author's display name through this seam
instead of importing the `User` ORM. Returns display name only — never email,
phone, or any other PII. A deactivated/missing user resolves to a neutral masked
label so a surface never crashes on an orphaned author reference.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users.domain.models import User

# Shown when the author is deactivated or the row is gone (retention-safe mask).
DEPARTED_LABEL = {"vi": "Người dùng đã rời nền tảng", "en": "Former user"}
_FALLBACK = "VinUni"


async def display_for(
    session: AsyncSession, user_ids: Iterable[uuid.UUID], *, locale: str = "vi"
) -> dict[uuid.UUID, str]:
    """Batch-resolve ``{user_id: display_name}`` (display only, no PII)."""

    ids = {i for i in user_ids if i is not None}
    if not ids:
        return {}
    rows = (
        await session.execute(
            select(User.id, User.full_name, User.is_active).where(User.id.in_(ids))
        )
    ).all()
    out: dict[uuid.UUID, str] = {}
    for row in rows:
        if not row.is_active:
            out[row.id] = DEPARTED_LABEL.get(locale, DEPARTED_LABEL["en"])
        else:
            out[row.id] = row.full_name or _FALLBACK
    return out
