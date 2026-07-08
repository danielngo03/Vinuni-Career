"""CV builder core service: templates, read (get/list/versions/quota), and
metadata update.

RBAC + ownership are enforced here (students hold ``cv:*``); a CV is only ever
accessed by its owner, and cross-owner access returns ``404``. Every accepted
edit writes a ``cv_versions`` row and an audit entry. Metadata updates use the
CV profile ``version`` as the optimistic-concurrency token (``expected_version``):
a stale token returns ``409 CONFLICT {current_version}``.

Creation (``create_cv``, ``create_cv_from_sections``, ``duplicate_cv``) lives in
``cv_creation_service``; section mutations and version restore live in
``cv_section_service``. Shared ownership/quota/snapshot helpers live in the
private ``_cv_core`` module.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.application.context import RequestContext
from app.modules.documents.api import presenters
from app.modules.documents.application import _cv_core, _shared
from app.modules.documents.application.errors import (
    CvVersionConflictError,
    InvalidCvFieldError,
)
from app.modules.documents.domain import catalog
from app.modules.documents.domain.models import CvProfile, CvTemplate
from app.shared.audit import write_audit
from app.shared.pagination import build_cursor_page, clamp_limit, decode_cursor
from app.shared.permissions import Principal, permission_checker

_RESOURCE = _shared.RESOURCE


# --------------------------------------------------------------------------- #
# Templates                                                                   #
# --------------------------------------------------------------------------- #


async def list_templates(session: AsyncSession, *, locale: str = "vi") -> list[dict]:
    """Public template catalogue: only published + active templates are offered.

    Draft/archived templates are back-office states and never reach students.
    """

    rows = (
        await session.execute(
            select(CvTemplate)
            .where(
                CvTemplate.is_active.is_(True),
                CvTemplate.status == "published",
            )
            .order_by(CvTemplate.key)
        )
    ).scalars().all()
    return [presenters.template(t, locale=locale) for t in rows]


# --------------------------------------------------------------------------- #
# Read                                                                        #
# --------------------------------------------------------------------------- #


async def get_cv(
    session: AsyncSession, *, principal: Principal, cv_id: uuid.UUID, locale: str = "vi"
) -> dict:
    permission_checker.require(principal, _RESOURCE, "read")
    cv = await _cv_core._load_owned_cv(session, principal=principal, cv_id=cv_id)
    return await _cv_core._detail_response(session, cv=cv, locale=locale)


async def list_versions(
    session: AsyncSession,
    *,
    principal: Principal,
    cv_id: uuid.UUID,
    locale: str = "vi",
) -> list[dict]:
    """Owner-only CV version history, newest-first (head == current)."""

    permission_checker.require(principal, _RESOURCE, "read")
    cv = await _cv_core._load_owned_cv(session, principal=principal, cv_id=cv_id)
    versions = await _cv_core._load_versions(session, cv_id=cv.id)
    current_id = str(versions[0].id) if versions else None
    return [
        presenters.cv_version_summary(
            v, is_current=(str(v.id) == current_id), locale=locale
        )
        for v in versions
    ]


async def count_cvs(session: AsyncSession, *, principal: Principal) -> int:
    """Number of the owner's LIBRARY CVs (``ready``, not soft-deleted).

    Shares ``_active_cv_count`` with the quota gate so the dashboard read model
    and the finalize/upload-import enforcement can never disagree on what counts
    against the 5-cap. Unlimited scratch drafts and archived CVs are excluded.
    """

    permission_checker.require(principal, _RESOURCE, "read")
    assert principal.user_id is not None
    return await _cv_core._active_cv_count(session, user_id=principal.user_id)


async def cv_library_quota(session: AsyncSession, *, principal: Principal) -> dict:
    """Active-CV library quota state for the CV list ``meta`` block.

    Shape matches docs/API_CONTRACTS.md "CV Library And Quota": the UI uses this to
    render the live "x/5" library counter and to disable **finalize / upload import**
    when ``can_create`` is false (creating/duplicating drafts stays unlimited).
    ``active_cv_used`` counts only ``ready`` library CVs. ``quota_reset_at`` is null
    because the active-CV limit is a standing cap, not a periodic allowance.
    ``quota_source`` is ``subscription`` when an active paid tier overrides the
    platform default (ADR-0010 §3), else ``student_tier``.
    """

    permission_checker.require(principal, _RESOURCE, "read")
    assert principal.user_id is not None
    limit, source = await _cv_core._resolve_active_cv_limit(session, principal=principal)
    used = await _cv_core._active_cv_count(session, user_id=principal.user_id)
    return {
        "active_cv_limit": limit,
        "active_cv_used": used,
        "can_create": used < limit,
        "quota_reset_at": None,
        "quota_source": source,
    }


async def list_cvs(
    session: AsyncSession,
    *,
    principal: Principal,
    cursor: str | None = None,
    limit: int | None = None,
    locale: str = "vi",
) -> tuple[list[dict], str | None, int]:
    permission_checker.require(principal, _RESOURCE, "read")
    page_limit = clamp_limit(limit)
    stmt = select(CvProfile).where(
        CvProfile.user_id == principal.user_id, CvProfile.deleted_at.is_(None)
    )
    decoded = decode_cursor(cursor)
    if decoded is not None:
        anchor_created = datetime.fromisoformat(decoded["created_at"])
        anchor_id = uuid.UUID(decoded["id"])
        stmt = stmt.where(
            or_(
                CvProfile.created_at < anchor_created,
                (CvProfile.created_at == anchor_created) & (CvProfile.id < anchor_id),
            )
        )
    stmt = stmt.order_by(CvProfile.created_at.desc(), CvProfile.id.desc()).limit(page_limit + 1)
    rows = list((await session.execute(stmt)).scalars().all())
    page = build_cursor_page(
        rows, limit=page_limit,
        cursor_builder=lambda p: {"created_at": p.created_at.isoformat(), "id": str(p.id)},
    )
    items = [presenters.cv_summary(p, locale=locale) for p in page.items]
    return items, page.next_cursor, page.limit


# --------------------------------------------------------------------------- #
# Update metadata                                                             #
# --------------------------------------------------------------------------- #

_UPDATABLE_META = {"title", "language", "status", "template_id"}


async def update_cv(
    session: AsyncSession,
    *,
    principal: Principal,
    cv_id: uuid.UUID,
    payload: dict,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    permission_checker.require(principal, _RESOURCE, "update")
    cv = await _cv_core._load_owned_cv(session, principal=principal, cv_id=cv_id, lock=True)

    expected = payload.pop("expected_version", None)
    if expected is not None and expected != cv.version:
        raise CvVersionConflictError(current_version=cv.version)

    if "status" in payload and payload["status"] not in catalog.CV_STATUSES:
        raise InvalidCvFieldError(field="status")
    if payload.get("template_id") is not None:
        payload["template_id"] = _shared.to_uuid(payload["template_id"])
        tpl = (
            await session.execute(
                select(CvTemplate).where(CvTemplate.id == payload["template_id"])
            )
        ).scalar_one_or_none()
        if tpl is None or not tpl.is_active:
            raise InvalidCvFieldError(field="template_id")

    changed: dict[str, object] = {}
    for field in _UPDATABLE_META:
        if field in payload and payload[field] is not None:
            setattr(cv, field, payload[field])
            changed[field] = True

    if changed:
        cv.version += 1
        cv.last_edited_at = _shared.now()
    await session.flush()

    await write_audit(
        session, action="cv.updated", resource_type="cv", resource_id=cv.id,
        context=_shared.audit_ctx(principal, ctx),
        after={"fields": sorted(changed.keys())},
    )
    await session.commit()
    await session.refresh(cv)
    return await _cv_core._detail_response(session, cv=cv, locale=locale)


async def delete_cv(
    session: AsyncSession,
    *,
    principal: Principal,
    cv_id: uuid.UUID,
    ctx: RequestContext,
    expected_version: int | None = None,
) -> None:
    """Soft-delete the owner's CV — it disappears from the library and stops
    counting against the active-CV quota. Snapshots referenced by submitted
    applications are preserved (immutable), so this is safe. Owner-only; the write
    is audited. Re-deleting a missing/already-deleted CV raises 404.
    """

    permission_checker.require(principal, _RESOURCE, "update")
    cv = await _cv_core._load_owned_cv(session, principal=principal, cv_id=cv_id, lock=True)
    if expected_version is not None and expected_version != cv.version:
        raise CvVersionConflictError(current_version=cv.version)
    cv.deleted_at = _shared.now()
    cv.version += 1
    await session.flush()
    await write_audit(
        session, action="cv.deleted", resource_type="cv", resource_id=cv.id,
        context=_shared.audit_ctx(principal, ctx),
    )
    await session.commit()


# --------------------------------------------------------------------------- #
# Backward-compatible re-exports                                             #
# --------------------------------------------------------------------------- #
#
# ``create_cv``/``create_cv_from_sections``/``duplicate_cv`` now live in
# ``cv_creation_service``; ``upsert_section``/``create_section``/``restore_version``
# now live in ``cv_section_service``. Re-exported here (module-level names, not
# thin wrappers) so existing callers/tests that reach ``cv_service.<name>`` keep
# working unchanged; new call sites should import the owning module directly.

from app.modules.documents.application import cv_creation_service as _creation  # noqa: E402
from app.modules.documents.application import cv_section_service as _sections  # noqa: E402

create_cv = _creation.create_cv
create_cv_from_sections = _creation.create_cv_from_sections
duplicate_cv = _creation.duplicate_cv
create_section = _sections.create_section
restore_version = _sections.restore_version
upsert_section = _sections.upsert_section

# A handful of tests reach into the quota internals directly.
_active_cv_limit = _cv_core._active_cv_limit
_resolve_active_cv_limit = _cv_core._resolve_active_cv_limit
_active_cv_count = _cv_core._active_cv_count
