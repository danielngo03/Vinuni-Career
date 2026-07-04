"""Shared internal CV-builder helpers (documents module, PRIVATE).

Extracted from the former monolithic ``cv_service.py`` so the active-CV quota
gate, ownership loading, version snapshotting, and section seeding have exactly
ONE implementation shared by ``cv_service`` (read/update), ``cv_creation_service``
(create/duplicate), ``cv_section_service`` (section + restore mutations), and the
cross-service callers ``cv_ai_service`` / ``job_fit_service``.

Everything here is an implementation detail of the CV builder — NOT a public
application-service API. Callers outside ``documents.application`` must never
import this module; use the public functions on ``cv_service`` /
``cv_creation_service`` / ``cv_section_service`` instead.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.documents.api import presenters
from app.modules.documents.application import _shared
from app.modules.documents.application.errors import CvQuotaReachedError
from app.modules.documents.domain import catalog
from app.modules.documents.domain.models import CvProfile, CvSection, CvVersion
from app.shared.exceptions import ResourceNotFoundError
from app.shared.permissions import Principal

# --------------------------------------------------------------------------- #
# Active-CV library quota (single source of truth)                            #
# --------------------------------------------------------------------------- #
#
# "Active" CV library items = owner's CVs that are NOT soft-deleted and NOT
# archived. Archived CVs and immutable application snapshots do not count, so
# archiving a CV frees a slot (docs/CV_STUDIO_SPEC.md §5, docs/BUSINESS_LOGIC.md
# §4B.4). The count predicate is defined ONCE here and reused by create_cv,
# duplicate_cv, and count_cvs so they cannot drift.


def _active_cv_count_stmt(user_id: uuid.UUID):
    return (
        select(func.count())
        .select_from(CvProfile)
        .where(
            CvProfile.user_id == user_id,
            CvProfile.deleted_at.is_(None),
            CvProfile.status != catalog.CV_ARCHIVED,
        )
    )


async def _active_cv_count(session: AsyncSession, *, user_id: uuid.UUID) -> int:
    return (await session.execute(_active_cv_count_stmt(user_id))).scalar_one()


def _active_cv_limit() -> int:
    # The PLATFORM DEFAULT active-CV cap (no subscription). Kept zero-arg so it is
    # the single source of the baseline and the default the subscription facade
    # falls back to. The per-tier override is resolved in ``_resolve_active_cv_limit``
    # below via the one-way ``documents -> billing`` limit-resolution seam.
    return get_settings().student_active_cv_quota


async def _resolve_active_cv_limit(
    session: AsyncSession, *, principal: Principal
) -> tuple[int, str]:
    """Resolve the owner's effective active-CV cap + its source (ADR-0010 §3).

    Reads the ``cv_active_quota`` limit from the principal's ACTIVE paid
    subscription's plan through the billing limit facade, falling back to the
    platform default (``_active_cv_limit()``) when there is no active paid
    subscription. The ``documents -> billing`` import is LAZY (and one-way: billing
    never imports documents), mirroring the ``advertising -> opportunities``
    ``sponsorship_facade`` seam. Returns ``(limit, quota_source)`` where
    ``quota_source`` is ``"subscription"`` when a paid tier overrode the default,
    else ``"student_tier"`` (the platform default).
    """

    from app.modules.billing.application import limit_facade  # lazy: one-way seam

    default = _active_cv_limit()
    limit = await limit_facade.resolve_limit(
        session, principal, key="cv_active_quota", default=default
    )
    source = "subscription" if limit != default else "student_tier"
    return int(limit), source


async def _enforce_active_cv_quota(
    session: AsyncSession, *, principal: Principal
) -> None:
    """Raise ``CvQuotaReachedError`` (409 QUOTA_EXCEEDED) when the owner is at or
    over the active CV library limit. Called at the service layer BEFORE any new
    CvProfile insert. The limit resolves through the subscription facade (a paid
    tier overrides the platform default)."""

    assert principal.user_id is not None
    limit, _source = await _resolve_active_cv_limit(session, principal=principal)
    current = await _active_cv_count(session, user_id=principal.user_id)
    if current >= limit:
        raise CvQuotaReachedError(current=current, limit=limit)


# --------------------------------------------------------------------------- #
# Loading / ownership                                                         #
# --------------------------------------------------------------------------- #


async def _load_owned_cv(
    session: AsyncSession, *, principal: Principal, cv_id: uuid.UUID, lock: bool = False
) -> CvProfile:
    stmt = select(CvProfile).where(CvProfile.id == cv_id, CvProfile.deleted_at.is_(None))
    if lock and _shared.use_for_update():
        stmt = stmt.with_for_update()
    cv = (await session.execute(stmt)).scalar_one_or_none()
    if cv is None or cv.user_id != principal.user_id:
        raise ResourceNotFoundError()
    return cv


async def _load_sections(session: AsyncSession, *, cv_id: uuid.UUID) -> list[CvSection]:
    return list(
        (
            await session.execute(
                select(CvSection)
                .where(CvSection.cv_id == cv_id)
                .order_by(CvSection.sort_order, CvSection.id)
            )
        ).scalars().all()
    )


async def _load_versions(session: AsyncSession, *, cv_id: uuid.UUID) -> list[CvVersion]:
    """All immutable snapshots for a CV, newest-first (head == current)."""

    return list(
        (
            await session.execute(
                select(CvVersion)
                .where(CvVersion.cv_id == cv_id)
                .order_by(CvVersion.version_number.desc(), CvVersion.id.desc())
            )
        ).scalars().all()
    )


async def _detail_response(
    session: AsyncSession, *, cv: CvProfile, locale: str
) -> dict:
    """Build the full CV detail (sections + version history + current_version_id)."""

    sections = await _load_sections(session, cv_id=cv.id)
    versions = await _load_versions(session, cv_id=cv.id)
    return presenters.cv_detail(cv, sections=sections, versions=versions, locale=locale)


async def _snapshot_version(
    session: AsyncSession,
    *,
    cv: CvProfile,
    change_source: str,
    change_summary: str | None,
    created_by: uuid.UUID,
) -> CvVersion:
    sections = await _load_sections(session, cv_id=cv.id)
    version = CvVersion(
        cv_id=cv.id,
        version_number=await _shared.next_version_number(session, cv_id=cv.id),
        snapshot_json=_shared.build_snapshot(cv, sections),
        change_source=change_source,
        change_summary=change_summary,
        created_by=created_by,
    )
    session.add(version)
    await session.flush()
    return version


async def _seed_sections(
    session: AsyncSession, *, cv_id: uuid.UUID, sections: list[dict]
) -> None:
    for spec in sections:
        session.add(
            CvSection(
                cv_id=cv_id,
                section_type=spec["section_type"],
                title=spec.get("title"),
                sort_order=spec.get("sort_order", 0),
                content_json=spec.get("content_json") or {},
                is_visible=spec.get("is_visible", True),
            )
        )
    await session.flush()
