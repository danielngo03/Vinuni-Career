"""CV builder creation service: create (from template), create-from-sections, and
duplicate.

Supported CV creation paths (owner cleanup 2026-07-05):
  - ``create_cv`` (``creation_mode=blank_template``): create a CV from a (free)
    template. This is the ONLY mode the generic create dispatcher accepts.
  - ``duplicate_cv``: duplicate an existing CV.
  - ``create_cv_from_sections``: the ingestion -> upload-import path.
AI is an in-builder ASSIST (suggestion / ai-edit-command), NOT a creation mode.
The retired ``profile_import`` / ``notes_import`` / ``ai_assisted_draft`` modes
were removed.

RBAC + ownership are enforced here (students hold ``cv:*``); a CV is only ever
accessed by its owner, and cross-owner access returns ``404``. Every accepted
creation writes an initial ``cv_versions`` row and an audit entry.

CV library lifecycle (design spec 2026-07-05, owner-approved): ``create_cv`` and
``duplicate_cv`` produce unlimited scratch DRAFTS (``status='draft'``) and are NOT
quota-gated — a student designs freely and only pays a library slot when they
commit a CV via ``cv_lifecycle_service.finalize_cv``. The ONE exception here is
``create_cv_from_sections``: its only caller is the upload-import path, and an
uploaded CV is already extracted/analyzed, so it lands directly in the library
(``status='ready'`` + ``finalized_at``) and KEEPS its quota gate.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.application.context import RequestContext
from app.modules.documents.application import _cv_core, _shared
from app.modules.documents.application.errors import InvalidCvFieldError
from app.modules.documents.domain import catalog
from app.modules.documents.domain.models import (
    CvProfile,
    CvSection,
    CvTemplate,
)
from app.shared.audit import write_audit
from app.shared.permissions import Principal, permission_checker

_RESOURCE = _shared.RESOURCE


# --------------------------------------------------------------------------- #
# Create                                                                      #
# --------------------------------------------------------------------------- #


async def create_cv(
    session: AsyncSession,
    *,
    principal: Principal,
    payload: dict,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    permission_checker.require(principal, _RESOURCE, "create")
    assert principal.user_id is not None

    # No quota gate here. A newly created CV is an unlimited scratch DRAFT (design
    # spec 2026-07-05): the 5-cap is enforced only when the student commits a CV to
    # their library via ``POST /cvs/{id}/finalize`` (or upload import). Designing
    # freely from a template costs nothing.
    #
    # The generic create dispatcher accepts ONLY ``blank_template`` (create from a
    # free template). Duplicate goes through ``duplicate_cv``; upload-import goes
    # through ``create_cv_from_sections`` (ingestion). AI is an in-builder assist,
    # not a creation mode. Any other/removed mode is rejected.
    mode = payload.get("creation_mode", catalog.CREATION_BLANK)
    if mode != catalog.CREATION_BLANK:
        raise InvalidCvFieldError(field="creation_mode")

    language = payload.get("language") or "vi"
    title = payload.get("title") or "Untitled CV"
    template_id = _shared.to_uuid(payload.get("template_id"))

    template: CvTemplate | None = None
    if template_id is not None:
        template = (
            await session.execute(select(CvTemplate).where(CvTemplate.id == template_id))
        ).scalar_one_or_none()
        if template is None or not template.is_active:
            raise InvalidCvFieldError(field="template_id")

    cv = CvProfile(
        user_id=principal.user_id,
        title=title,
        source_type=catalog.SOURCE_TYPE_FOR_MODE[catalog.CREATION_BLANK],
        template_id=template.id if template else None,
        language=language,
        status=catalog.CV_DRAFT,
    )
    session.add(cv)
    await session.flush()

    await _cv_core._seed_sections(session, cv_id=cv.id, sections=catalog.DEFAULT_SECTIONS)

    await _cv_core._snapshot_version(
        session, cv=cv, change_source="manual",
        change_summary="initial", created_by=principal.user_id,
    )
    await write_audit(
        session, action="cv.created", resource_type="cv", resource_id=cv.id,
        context=_shared.audit_ctx(principal, ctx),
        after={"source_type": cv.source_type, "creation_mode": catalog.CREATION_BLANK},
    )
    await session.commit()
    await session.refresh(cv)
    return await _cv_core._detail_response(session, cv=cv, locale=locale)


async def create_cv_from_sections(
    session: AsyncSession,
    *,
    principal: Principal,
    title: str,
    language: str,
    template_id: uuid.UUID | None,
    sections: list[dict],
    source_type: str,
    change_source: str,
    ctx: RequestContext,
    audit_action: str = "cv.created",
    audit_extra: dict | None = None,
    locale: str = "vi",
) -> dict:
    """Create a NEW versioned LIBRARY CV from a prepared section set (owner-only).

    The sole caller is the upload-import path (``ingestion_service``): an uploaded
    CV has already gone through the (token-expensive) extraction cascade, so it IS
    an analyzed library CV — it lands directly ``status='ready'`` + ``finalized_at``
    and counts against the 5-cap. The quota gate (``409 QUOTA_EXCEEDED``), the
    initial immutable ``cv_versions`` snapshot, and the audit write are enforced in
    exactly one place. Never mutates an existing CV.
    """

    permission_checker.require(principal, _RESOURCE, "create")
    assert principal.user_id is not None
    await _cv_core._enforce_active_cv_quota(session, principal=principal)

    template_uuid = _shared.to_uuid(template_id)
    if template_uuid is not None:
        tpl = (
            await session.execute(select(CvTemplate).where(CvTemplate.id == template_uuid))
        ).scalar_one_or_none()
        if tpl is None or not tpl.is_active:
            raise InvalidCvFieldError(field="template_id")

    now = _shared.now()
    cv = CvProfile(
        user_id=principal.user_id,
        title=title or "Untitled CV",
        source_type=source_type,
        template_id=template_uuid,
        language=language or "vi",
        # Uploaded/analyzed CV -> straight into the library (ready), not a draft.
        status=catalog.CV_READY,
        finalized_at=now,
        # Set last_edited_at explicitly (not via server_default) so the stored
        # matching snapshot's ``last_activity_at`` matches the persisted value.
        last_edited_at=now,
    )
    session.add(cv)
    await session.flush()

    await _cv_core._seed_sections(session, cv_id=cv.id, sections=sections)

    # Store the version-stamped matching snapshot so CV-JD scoring can reuse it as a
    # fast path (an uploaded CV is already extracted/analyzed — it lands
    # matching-ready, exactly like a finalized template CV; B-596). The seeded
    # sections are loaded in canonical (sort_order, id) order so the projection
    # matches a live section load byte-for-byte and never changes the score.
    from app.modules.documents.application.cv_lifecycle_service import (
        build_matching_representation,
    )

    seeded = await _cv_core._load_sections(session, cv_id=cv.id)
    cv.matching_json = build_matching_representation(cv, seeded)

    await _cv_core._snapshot_version(
        session, cv=cv, change_source=change_source,
        change_summary="initial", created_by=principal.user_id,
    )
    after = {"source_type": cv.source_type}
    if audit_extra:
        after.update(audit_extra)
    await write_audit(
        session, action=audit_action, resource_type="cv", resource_id=cv.id,
        context=_shared.audit_ctx(principal, ctx), after=after,
    )
    await session.commit()
    await session.refresh(cv)
    return await _cv_core._detail_response(session, cv=cv, locale=locale)


# --------------------------------------------------------------------------- #
# Duplicate                                                                   #
# --------------------------------------------------------------------------- #


async def duplicate_cv(
    session: AsyncSession,
    *,
    principal: Principal,
    cv_id: uuid.UUID,
    payload: dict,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    permission_checker.require(principal, _RESOURCE, "create")
    assert principal.user_id is not None

    idempotency_key = payload.get("idempotency_key")
    if idempotency_key:
        existing = (
            await session.execute(
                select(CvProfile).where(
                    CvProfile.user_id == principal.user_id,
                    CvProfile.idempotency_key == idempotency_key,
                    CvProfile.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return await _cv_core._detail_response(session, cv=existing, locale=locale)

    # No quota gate: a duplicate is a new scratch DRAFT (design spec 2026-07-05).
    # The student commits it to their library later via finalize; duplicating to
    # explore variants is unlimited and free.
    source = await _cv_core._load_owned_cv(session, principal=principal, cv_id=cv_id)
    template_id = _shared.to_uuid(payload.get("template_id")) or source.template_id

    new_cv = CvProfile(
        user_id=principal.user_id,
        title=payload.get("title") or f"{source.title} (copy)",
        source_type=catalog.SOURCE_TYPE_FOR_MODE[catalog.CREATION_DUPLICATE],
        template_id=template_id,
        language=source.language,
        status=catalog.CV_DRAFT,
        idempotency_key=idempotency_key,
    )
    session.add(new_cv)
    await session.flush()

    # Copy sections from the source (source is never mutated).
    src_sections = await _cv_core._load_sections(session, cv_id=source.id)
    for s in src_sections:
        session.add(
            CvSection(
                cv_id=new_cv.id,
                section_type=s.section_type,
                title=s.title,
                sort_order=s.sort_order,
                content_json=dict(s.content_json or {}),
                is_visible=s.is_visible,
            )
        )
    await session.flush()

    await _cv_core._snapshot_version(
        session, cv=new_cv, change_source="import",
        change_summary=f"duplicate of {source.id}", created_by=principal.user_id,
    )
    await write_audit(
        session, action="cv.duplicated", resource_type="cv", resource_id=new_cv.id,
        context=_shared.audit_ctx(principal, ctx),
        after={"source_cv_id": str(source.id)},
    )
    await session.commit()
    await session.refresh(new_cv)
    return await _cv_core._detail_response(session, cv=new_cv, locale=locale)
