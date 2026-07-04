"""CV Studio visual canvas layout mutations (``docs/CV_STUDIO_SPEC.md`` "Visual
Canvas Editor Contract").

``cv_profiles.canvas_json`` is PRESENTATION/LAYOUT metadata only: block
ordering/position/visibility overrides (keyed by a stable client-generated
``block.id``, optionally bound to an existing ``cv_sections`` row) plus page
settings. It never duplicates or overrides CV FACTS — those stay in
``cv_sections.content_json`` and are mutated only through
``cv_section_service``. The profile-photo binding is a sibling key
(``canvas_json["photo"]``) managed exclusively by ``cv_photo_service`` — a
canvas update here only ever replaces the ``blocks``/``page`` keys it was given,
so it can never silently drop the photo.

RBAC + ownership mirror every other CV mutation: owner-only (404 on cross-owner
access), versioned (bumps ``cv.version`` + writes a ``cv_versions`` snapshot),
audited, and optimistic-concurrency gated via ``expected_version``.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.application.context import RequestContext
from app.modules.documents.application import _cv_core, _shared
from app.modules.documents.application.errors import (
    CvVersionConflictError,
    InvalidCvFieldError,
)
from app.shared.audit import write_audit
from app.shared.permissions import permission_checker

_RESOURCE = _shared.RESOURCE

# Block types the visual canvas editor supports in this slice. Kept as an
# allowlist so a malformed/foreign client payload can never inject an unknown
# renderer directive (``docs/CV_STUDIO_SPEC.md`` "canvas elements").
_BLOCK_TYPES = frozenset(
    {"text", "list", "heading", "image", "divider", "spacer", "custom"}
)
_MAX_BLOCKS = 300


def _validate_blocks(blocks_in: object, *, valid_section_ids: set[str]) -> list[dict]:
    if not isinstance(blocks_in, list) or len(blocks_in) > _MAX_BLOCKS:
        raise InvalidCvFieldError(field="canvas.blocks")

    seen_ids: set[str] = set()
    out: list[dict] = []
    for raw in blocks_in:
        if not isinstance(raw, dict):
            raise InvalidCvFieldError(field="canvas.blocks")
        block_id = raw.get("id")
        if not isinstance(block_id, str) or not block_id.strip() or block_id in seen_ids:
            raise InvalidCvFieldError(field="canvas.blocks.id")
        seen_ids.add(block_id)

        block_type = raw.get("type")
        if block_type not in _BLOCK_TYPES:
            raise InvalidCvFieldError(field="canvas.blocks.type")

        section_id = raw.get("section_id")
        if section_id is not None and str(section_id) not in valid_section_ids:
            # A block may reference a section that no longer exists (deleted
            # concurrently) or one outside this CV — reject rather than silently
            # orphan the binding.
            raise InvalidCvFieldError(field="canvas.blocks.section_id")

        order = raw.get("order", 0)
        if not isinstance(order, int) or isinstance(order, bool) or order < 0:
            raise InvalidCvFieldError(field="canvas.blocks.order")

        style = raw.get("style")
        out.append(
            {
                "id": block_id,
                "type": block_type,
                "section_id": str(section_id) if section_id else None,
                "order": order,
                "visible": bool(raw.get("visible", True)),
                "style": style if isinstance(style, dict) else {},
            }
        )
    return out


async def update_canvas(
    session: AsyncSession,
    *,
    principal,
    cv_id: uuid.UUID,
    payload: dict,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    permission_checker.require(principal, _RESOURCE, "update")
    assert principal.user_id is not None
    cv = await _cv_core._load_owned_cv(session, principal=principal, cv_id=cv_id, lock=True)

    expected = payload.get("expected_version")
    if expected is not None and expected != cv.version:
        raise CvVersionConflictError(current_version=cv.version)

    canvas = dict(cv.canvas_json or {})

    if "blocks" in payload and payload["blocks"] is not None:
        sections = await _cv_core._load_sections(session, cv_id=cv.id)
        valid_section_ids = {str(s.id) for s in sections}
        canvas["blocks"] = _validate_blocks(
            payload["blocks"], valid_section_ids=valid_section_ids
        )

    if "page" in payload and payload["page"] is not None:
        if not isinstance(payload["page"], dict):
            raise InvalidCvFieldError(field="canvas.page")
        canvas["page"] = payload["page"]

    cv.canvas_json = canvas
    cv.version += 1
    cv.last_edited_at = _shared.now()
    await session.flush()

    await _cv_core._snapshot_version(
        session,
        cv=cv,
        change_source="manual",
        change_summary="canvas layout updated",
        created_by=principal.user_id,
    )
    await write_audit(
        session,
        action="cv.canvas.updated",
        resource_type="cv",
        resource_id=cv.id,
        context=_shared.audit_ctx(principal, ctx),
        after={"cv_id": str(cv.id), "block_count": len(canvas.get("blocks", []))},
    )
    await session.commit()
    await session.refresh(cv)
    return await _cv_core._detail_response(session, cv=cv, locale=locale)
