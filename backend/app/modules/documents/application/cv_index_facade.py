"""Documents read seam for the talent-pool CV index.

The ``talent_pool`` module builds a semantic index over consented CVs but must
NOT reach into ``documents.domain.models`` (module-boundary guard,
``docs/ARCHITECTURE.md`` §8). This facade is that seam: it OWNS the CV ORM
(``CvProfile`` / ``CvSection`` / ``CvVersion``) and returns only plain
dataclasses/ids/dicts — the structured CV sections the indexer needs to project
into embedding text, the content version, and the immutable version snapshot id.
No ORM object or ``domain.models`` type ever crosses the boundary.

Read-only. Never surfaces provider/model/token internals (there are none here —
this is deterministic structured content).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.documents.application import cv_lifecycle_service
from app.modules.documents.domain import catalog as cv_catalog
from app.modules.documents.domain.models import CvProfile, CvSection, CvVersion


@dataclass(frozen=True, slots=True)
class IndexableCv:
    """The leak-safe projection the talent-pool indexer consumes for one CV.

    ``sections`` are plain ``{section_type, title, content}`` dicts (resolved from
    the fresh matching snapshot or a live section load) — never ORM rows.
    ``snapshot_id`` is the immutable ``cv_versions`` id the content reflects (or the
    CV id when no version row exists yet; both are bare UUIDs).
    """

    cv_id: uuid.UUID
    user_id: uuid.UUID
    content_version: int
    snapshot_id: uuid.UUID
    sections: list[dict]


async def _resolve_sections(session: AsyncSession, *, cv: CvProfile) -> list[dict]:
    """The structured CV sections, from the fresh matching snapshot or a live load.

    Mirrors ``job_fit_service._build_cv_input``'s fast path: a committed CV carries
    a version-stamped ``matching_json`` that is a byte-identical projection of its
    sections; when it is fresh use it, else rebuild deterministically from the live
    sections (no OCR/AI).
    """

    mj = cv.matching_json
    if (
        isinstance(mj, dict)
        and mj.get("content_version") == cv.version
        and isinstance(mj.get("sections"), list)
    ):
        return [s for s in mj["sections"] if isinstance(s, dict)]

    rows = (
        (
            await session.execute(
                select(CvSection)
                .where(CvSection.cv_id == cv.id)
                .order_by(CvSection.sort_order, CvSection.id)
            )
        )
        .scalars()
        .all()
    )
    rep = cv_lifecycle_service.build_matching_representation(cv, list(rows))
    return [s for s in (rep.get("sections") or []) if isinstance(s, dict)]


async def _latest_snapshot_id(session: AsyncSession, *, cv: CvProfile) -> uuid.UUID:
    latest = (
        await session.execute(
            select(CvVersion.id)
            .where(CvVersion.cv_id == cv.id)
            .order_by(CvVersion.version_number.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return latest if isinstance(latest, uuid.UUID) else cv.id


async def get_indexable_cv(
    session: AsyncSession, *, cv_id: uuid.UUID
) -> IndexableCv | None:
    """Return the indexable projection for a READY CV, or ``None``.

    ``None`` when the CV is missing, soft-deleted, or not committed to the library
    (``status != ready``) — the caller treats that as "remove any stale vector".
    """

    cv = (
        await session.execute(
            select(CvProfile).where(CvProfile.id == cv_id, CvProfile.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if cv is None or cv.status != cv_catalog.CV_READY:
        return None

    sections = await _resolve_sections(session, cv=cv)
    snapshot_id = await _latest_snapshot_id(session, cv=cv)
    return IndexableCv(
        cv_id=cv.id,
        user_id=cv.user_id,
        content_version=cv.version,
        snapshot_id=snapshot_id,
        sections=sections,
    )


async def list_ready_cv_ids_for_users(
    session: AsyncSession, *, user_ids: list[uuid.UUID], limit: int | None = None
) -> list[uuid.UUID]:
    """Ready (library-committed) CV ids owned by the given users, freshest first."""

    if not user_ids:
        return []
    stmt = (
        select(CvProfile.id)
        .where(
            CvProfile.user_id.in_(set(user_ids)),
            CvProfile.deleted_at.is_(None),
            CvProfile.status == cv_catalog.CV_READY,
        )
        .order_by(CvProfile.finalized_at.desc().nullslast())
    )
    if limit is not None:
        stmt = stmt.limit(limit)
    return list((await session.execute(stmt)).scalars().all())
