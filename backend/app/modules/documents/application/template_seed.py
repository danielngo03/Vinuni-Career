"""Idempotent CV template seeder.

Seeds the university-approved CV templates from ``domain.catalog.TEMPLATE_SEEDS``.
Each template carries a full visual theme (``domain.themes``) and is seeded as
``status='published'``, ``version=1`` with a matching immutable
``cv_template_versions`` snapshot so publishing history exists from day one.

Safe to run repeatedly: an existing template for the same ``key`` is left
untouched (and its version row is backfilled if missing). Used by migration
``0005``/``0065`` (Postgres) and by tests that need templates present on the
metadata-created SQLite schema. Does not commit — the caller owns the transaction.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.documents.domain.catalog import TEMPLATE_SEEDS
from app.modules.documents.domain.models import CvTemplate, CvTemplateVersion


async def ensure_default_templates(session: AsyncSession) -> int:
    """Insert any missing default CV templates. Returns rows created.

    Also backfills a ``cv_template_versions`` row for the template's current
    ``version`` when one is missing (idempotent publish history).
    """

    created = 0
    for spec in TEMPLATE_SEEDS:
        template = (
            await session.execute(select(CvTemplate).where(CvTemplate.key == spec["key"]))
        ).scalar_one_or_none()
        if template is None:
            template = CvTemplate(
                key=spec["key"],
                name_vi=spec["name_vi"],
                name_en=spec["name_en"],
                category=spec["category"],
                layout_schema=spec["layout_schema"],
                is_active=True,
                status="published",
                version=1,
                published_at=datetime.now(UTC),
            )
            session.add(template)
            await session.flush()
            created += 1
        await _ensure_current_version_row(session, template)
    if created:
        await session.flush()
    return created


async def _ensure_current_version_row(session: AsyncSession, template: CvTemplate) -> None:
    """Insert the immutable version snapshot for ``template``'s current version
    if it does not already exist (idempotent)."""

    exists = (
        await session.execute(
            select(CvTemplateVersion.id).where(
                CvTemplateVersion.template_id == template.id,
                CvTemplateVersion.version_number == template.version,
            )
        )
    ).first()
    if exists is not None:
        return
    session.add(
        CvTemplateVersion(
            template_id=template.id,
            version_number=template.version,
            design_json=template.layout_schema or {},
            preview_image=template.preview_image,
            created_by=None,
        )
    )
    await session.flush()
