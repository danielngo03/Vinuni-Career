"""Idempotent CV template seeder.

Seeds the university-approved CV templates from ``domain.catalog.TEMPLATE_SEEDS``.
Safe to run repeatedly: an existing template for the same ``key`` is left
untouched. Used by migration ``0005`` (Postgres) and by tests that need templates
present on the metadata-created SQLite schema. Does not commit — the caller owns
the transaction.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.documents.domain.catalog import TEMPLATE_SEEDS
from app.modules.documents.domain.models import CvTemplate


async def ensure_default_templates(session: AsyncSession) -> int:
    """Insert any missing default CV templates. Returns rows created."""

    created = 0
    for spec in TEMPLATE_SEEDS:
        exists = (
            await session.execute(
                select(CvTemplate.id).where(CvTemplate.key == spec["key"])
            )
        ).first()
        if exists is not None:
            continue
        session.add(
            CvTemplate(
                key=spec["key"],
                name_vi=spec["name_vi"],
                name_en=spec["name_en"],
                category=spec["category"],
                layout_schema=spec["layout_schema"],
                is_premium=spec["is_premium"],
                is_active=True,
            )
        )
        created += 1
    if created:
        await session.flush()
    return created
