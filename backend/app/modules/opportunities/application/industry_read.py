"""Batch-safe industry-slug resolution for public job projections.

The public job DTO carries a **tokenizable** ``industry_slug`` (e.g.
``"information-technology"``) — never the raw industry UUID — so guest discovery
can emit coarse, privacy-safe interest signals that the ranker tokenizes via
``taxonomy.tokens_of`` and matches against job title/skill tokens. A raw UUID is
useless for that, so we resolve the human slug from the ``industries`` taxonomy
(``Industry.slug``).

Resolution is batched: a page of N jobs costs **one** extra query, never N. The
``Industry`` model lives inside this same ``opportunities`` module, so this is an
own-module read (no cross-module ``domain.models`` reach).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.opportunities.domain.industry_models import Industry


async def resolve_industry_slugs(
    session: AsyncSession, industry_ids: set[uuid.UUID | None]
) -> dict[uuid.UUID, str]:
    """Map each present industry id to its ``slug`` in a single query.

    ``None`` ids are ignored; an empty/all-``None`` input short-circuits without a
    query so guest pages of jobs that never set an industry cost nothing extra.
    """

    ids = {i for i in industry_ids if i is not None}
    if not ids:
        return {}
    rows = (
        await session.execute(
            select(Industry.id, Industry.slug).where(Industry.id.in_(ids))
        )
    ).all()
    return {row.id: row.slug for row in rows}


async def resolve_industry_slug(
    session: AsyncSession, industry_id: uuid.UUID | None
) -> str | None:
    """Single-job convenience over :func:`resolve_industry_slugs` (``None``-safe)."""

    if industry_id is None:
        return None
    slugs = await resolve_industry_slugs(session, {industry_id})
    return slugs.get(industry_id)
