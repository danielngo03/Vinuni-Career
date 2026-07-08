"""CV builder section mutations: versioned section upsert/create, and restoring a
prior immutable version.

RBAC + ownership are enforced here (students hold ``cv:update``); a CV is only
ever mutated by its owner, and cross-owner access returns ``404``. Every accepted
edit writes a ``cv_versions`` row and an audit entry. Section upserts use the CV
profile ``version`` as the optimistic-concurrency token (``expected_version``):
a stale token returns ``409 CONFLICT {current_version}``.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.application.context import RequestContext
from app.modules.documents.api import presenters
from app.modules.documents.application import _cv_core, _shared
from app.modules.documents.application.errors import (
    CvVersionConflictError,
    InvalidCvFieldError,
)
from app.modules.documents.domain import catalog
from app.modules.documents.domain.models import CvSection, CvVersion
from app.shared.audit import write_audit
from app.shared.exceptions import ResourceNotFoundError
from app.shared.permissions import Principal, permission_checker

_RESOURCE = _shared.RESOURCE


# --------------------------------------------------------------------------- #
# Section upsert (versioned, optimistic)                                      #
# --------------------------------------------------------------------------- #


async def upsert_section(
    session: AsyncSession,
    *,
    principal: Principal,
    cv_id: uuid.UUID,
    section_id: uuid.UUID,
    payload: dict,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    permission_checker.require(principal, _RESOURCE, "update")
    assert principal.user_id is not None
    cv = await _cv_core._load_owned_cv(session, principal=principal, cv_id=cv_id, lock=True)
    # Uploaded CVs are read-only (the student's original document); only
    # TEMPLATE-created CVs are section-editable (owner decision 2026-07-05).
    _cv_core.guard_editable(cv)

    expected = payload.get("expected_version")
    if expected is not None and expected != cv.version:
        raise CvVersionConflictError(current_version=cv.version)

    section_type = payload.get("section_type")
    if section_type is not None and section_type not in catalog.SECTION_TYPES:
        raise InvalidCvFieldError(field="section_type")

    existing = (
        await session.execute(
            select(CvSection).where(CvSection.id == section_id, CvSection.cv_id == cv.id)
        )
    ).scalar_one_or_none()

    if existing is None:
        section = CvSection(
            id=section_id,
            cv_id=cv.id,
            section_type=section_type or "custom",
            title=payload.get("title"),
            sort_order=payload.get("sort_order", 0),
            content_json=payload.get("content") or {},
            is_visible=payload.get("is_visible", True),
        )
        session.add(section)
        action = "cv.section.created"
    else:
        if "title" in payload:
            existing.title = payload["title"]
        if "sort_order" in payload and payload["sort_order"] is not None:
            existing.sort_order = payload["sort_order"]
        if "content" in payload and payload["content"] is not None:
            existing.content_json = payload["content"]
        if "is_visible" in payload and payload["is_visible"] is not None:
            existing.is_visible = payload["is_visible"]
        if section_type is not None:
            existing.section_type = section_type
        section = existing
        action = "cv.section.updated"

    cv.version += 1
    cv.last_edited_at = _shared.now()
    await session.flush()

    await _cv_core._snapshot_version(
        session, cv=cv, change_source="manual",
        change_summary=f"section {section.section_type}", created_by=principal.user_id,
    )
    await write_audit(
        session, action=action, resource_type="cv_section", resource_id=section.id,
        context=_shared.audit_ctx(principal, ctx),
        after={"cv_id": str(cv.id), "section_type": section.section_type},
    )
    await session.commit()
    await session.refresh(cv)
    await session.refresh(section)
    return {
        "section": presenters.section(section),
        "cv_version": cv.version,
    }


# --------------------------------------------------------------------------- #
# Add a new section (versioned)                                                #
# --------------------------------------------------------------------------- #


async def create_section(
    session: AsyncSession,
    *,
    principal: Principal,
    cv_id: uuid.UUID,
    payload: dict,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    """Append a new section to a CV (owner-only), creating a new version snapshot.

    Mirrors the optimistic-concurrency + versioning behavior of ``upsert_section``
    and returns the same ``{section, cv_version}`` shape. When ``sort_order`` is
    omitted the new section is placed after the current last section.
    """

    permission_checker.require(principal, _RESOURCE, "update")
    assert principal.user_id is not None
    cv = await _cv_core._load_owned_cv(session, principal=principal, cv_id=cv_id, lock=True)
    # Uploaded CVs are read-only; only TEMPLATE-created CVs accept new sections.
    _cv_core.guard_editable(cv)

    expected = payload.get("expected_version")
    if expected is not None and expected != cv.version:
        raise CvVersionConflictError(current_version=cv.version)

    section_type = payload.get("section_type")
    if section_type is not None and section_type not in catalog.SECTION_TYPES:
        raise InvalidCvFieldError(field="section_type")

    sort_order = payload.get("sort_order")
    if sort_order is None:
        existing = await _cv_core._load_sections(session, cv_id=cv.id)
        sort_order = max((s.sort_order for s in existing), default=0) + 10

    section = CvSection(
        cv_id=cv.id,
        section_type=section_type or "custom",
        title=payload.get("title"),
        sort_order=sort_order,
        content_json=payload.get("content") or {},
        is_visible=payload.get("is_visible", True),
    )
    session.add(section)
    cv.version += 1
    cv.last_edited_at = _shared.now()
    await session.flush()

    await _cv_core._snapshot_version(
        session, cv=cv, change_source="manual",
        change_summary=f"add section {section.section_type}",
        created_by=principal.user_id,
    )
    await write_audit(
        session, action="cv.section.created", resource_type="cv_section",
        resource_id=section.id, context=_shared.audit_ctx(principal, ctx),
        after={"cv_id": str(cv.id), "section_type": section.section_type},
    )
    await session.commit()
    await session.refresh(cv)
    await session.refresh(section)
    return {
        "section": presenters.section(section),
        "cv_version": cv.version,
    }


# --------------------------------------------------------------------------- #
# Restore a prior version (versioned)                                          #
# --------------------------------------------------------------------------- #


async def restore_version(
    session: AsyncSession,
    *,
    principal: Principal,
    cv_id: uuid.UUID,
    version_id: uuid.UUID,
    payload: dict | None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    """Restore a CV to a prior immutable snapshot (owner-only).

    Restoration is non-destructive to history: it rebuilds the live sections from
    the target snapshot and records the result as a NEW ``cv_versions`` row
    (``change_source = restore``). The prior versions remain intact.
    """

    permission_checker.require(principal, _RESOURCE, "update")
    assert principal.user_id is not None
    cv = await _cv_core._load_owned_cv(session, principal=principal, cv_id=cv_id, lock=True)
    # Uploaded CVs are read-only; version restore is an editor-only action
    # reserved for TEMPLATE-created CVs (an uploaded CV never opens the editor).
    _cv_core.guard_editable(cv)

    expected = (payload or {}).get("expected_version")
    if expected is not None and expected != cv.version:
        raise CvVersionConflictError(current_version=cv.version)

    target = (
        await session.execute(
            select(CvVersion).where(CvVersion.id == version_id, CvVersion.cv_id == cv.id)
        )
    ).scalar_one_or_none()
    if target is None:
        raise ResourceNotFoundError()

    snapshot = target.snapshot_json or {}

    # Restore profile-level fields captured in the snapshot.
    if snapshot.get("title"):
        cv.title = snapshot["title"]
    if snapshot.get("language"):
        cv.language = snapshot["language"]
    cv.template_id = _shared.to_uuid(snapshot.get("template_id"))
    cv.canvas_json = snapshot.get("canvas") or {}

    # Replace live sections with the snapshot's sections (history is preserved).
    for existing in await _cv_core._load_sections(session, cv_id=cv.id):
        await session.delete(existing)
    await session.flush()
    for spec in snapshot.get("sections", []):
        session.add(
            CvSection(
                cv_id=cv.id,
                section_type=spec.get("section_type", "custom"),
                title=spec.get("title"),
                sort_order=spec.get("sort_order", 0),
                content_json=spec.get("content_json") or {},
                is_visible=spec.get("is_visible", True),
            )
        )

    cv.version += 1
    cv.last_edited_at = _shared.now()
    await session.flush()

    await _cv_core._snapshot_version(
        session, cv=cv, change_source="restore",
        change_summary=f"restored v{target.version_number}",
        created_by=principal.user_id,
    )
    await write_audit(
        session, action="cv.version.restored", resource_type="cv",
        resource_id=cv.id, context=_shared.audit_ctx(principal, ctx),
        after={"restored_from_version": target.version_number,
               "restored_from_version_id": str(target.id)},
    )
    await session.commit()
    await session.refresh(cv)
    return await _cv_core._detail_response(session, cv=cv, locale=locale)
