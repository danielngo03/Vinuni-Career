"""CV Studio profile-photo replace/crop/remove (``docs/CV_STUDIO_SPEC.md``
"Photo placeholder support: upload, replace, crop, remove, and fit-to-shape").

The uploaded image is stored exactly like any other owner-scoped file (a
``documents`` row, ``doc_type="cv_photo"``, via the existing storage/signed-token
conventions — ``storage_path`` never leaves this layer) and bound to the CV
canvas at ``cv_profiles.canvas_json["photo"]`` with a normalized crop rectangle
(fractions of the image, ``0..1``) and a display shape. This never touches
``blocks``/``page`` (owned by ``cv_canvas_service``). Non-destructive to CV
facts: every change writes a new ``cv_versions`` snapshot + audit, same as every
other canvas/section mutation.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.extraction import cv_validation
from app.core.config import get_settings
from app.modules.auth.application.context import RequestContext
from app.modules.documents.application import _cv_core, _shared
from app.modules.documents.application.errors import (
    CvVersionConflictError,
    InvalidCropRectError,
    InvalidPhotoFileError,
)
from app.modules.documents.domain.models import Document
from app.modules.documents.infrastructure import storage
from app.shared.audit import write_audit
from app.shared.permissions import permission_checker

_RESOURCE = _shared.RESOURCE

_ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp"}
_EXT_BY_TYPE = {"image/png": ".png", "image/webp": ".webp"}
_MAX_PHOTO_BYTES = 8 * 1024 * 1024  # a profile photo, not a full document
_ALLOWED_SHAPES = frozenset({"circle", "square", "rounded"})
_DEFAULT_SHAPE = "square"
_EPSILON = 1e-6


def _validate_crop(crop: dict | None) -> dict:
    """Normalize + bounds-check a crop rectangle (fractions of the image, 0..1).

    Rejects missing/non-numeric/negative/oversized rectangles rather than
    silently clamping into something the student never asked for.
    """

    crop = crop or {}
    try:
        x = float(crop.get("x", 0))
        y = float(crop.get("y", 0))
        width = float(crop.get("width", 1))
        height = float(crop.get("height", 1))
    except (TypeError, ValueError) as exc:
        raise InvalidCropRectError() from exc

    if not (-_EPSILON <= x <= 1 + _EPSILON) or not (-_EPSILON <= y <= 1 + _EPSILON):
        raise InvalidCropRectError()
    if width <= 0 or height <= 0:
        raise InvalidCropRectError()
    if x + width > 1 + _EPSILON or y + height > 1 + _EPSILON:
        raise InvalidCropRectError()

    return {
        "x": round(max(0.0, min(1.0, x)), 4),
        "y": round(max(0.0, min(1.0, y)), 4),
        "width": round(max(0.0, min(1.0, width)), 4),
        "height": round(max(0.0, min(1.0, height)), 4),
    }


async def update_photo(
    session: AsyncSession,
    *,
    principal,
    cv_id: uuid.UUID,
    data: bytes,
    content_type: str | None,
    filename: str,
    crop: dict | None,
    shape: str | None,
    expected_version: int | None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    permission_checker.require(principal, _RESOURCE, "update")
    assert principal.user_id is not None
    cv = await _cv_core._load_owned_cv(session, principal=principal, cv_id=cv_id, lock=True)

    if expected_version is not None and expected_version != cv.version:
        raise CvVersionConflictError(current_version=cv.version)

    settings = get_settings()
    if not data:
        raise InvalidPhotoFileError()
    if len(data) > min(_MAX_PHOTO_BYTES, settings.max_upload_bytes):
        raise InvalidPhotoFileError()

    normalized_type = (content_type or "").split(";")[0].strip().lower()
    if normalized_type not in _ALLOWED_IMAGE_TYPES:
        raise InvalidPhotoFileError()

    crop_rect = _validate_crop(crop)
    photo_shape = shape if shape in _ALLOWED_SHAPES else _DEFAULT_SHAPE

    document_id = uuid.uuid4()
    ext = _EXT_BY_TYPE.get(normalized_type, ".jpg")
    storage_key = f"cv-photos/{principal.user_id}/{document_id}{ext}"
    storage.get_storage().save(storage_key, data)

    document = Document(
        id=document_id,
        user_id=principal.user_id,
        doc_type="cv_photo",
        original_name=(filename or "photo")[:500],
        storage_path=storage_key,
        mime_type=normalized_type,
        file_size_bytes=len(data),
        checksum_sha256=cv_validation.compute_checksum(data),
        virus_scan_status="clean",
        virus_scan_at=_shared.now(),
    )
    session.add(document)
    await session.flush()

    canvas = dict(cv.canvas_json or {})
    old_photo = canvas.get("photo") if isinstance(canvas.get("photo"), dict) else None
    canvas["photo"] = {
        "document_id": str(document.id),
        "crop": crop_rect,
        "shape": photo_shape,
    }
    cv.canvas_json = canvas
    cv.version += 1
    cv.last_edited_at = _shared.now()
    await session.flush()

    await _cv_core._snapshot_version(
        session, cv=cv, change_source="manual",
        change_summary="photo updated", created_by=principal.user_id,
    )
    await write_audit(
        session,
        action="cv.photo.updated",
        resource_type="cv",
        resource_id=cv.id,
        context=_shared.audit_ctx(principal, ctx),
        before={"document_id": old_photo.get("document_id")} if old_photo else None,
        after={"cv_id": str(cv.id), "document_id": str(document.id), "shape": photo_shape},
    )
    await session.commit()
    await session.refresh(cv)
    return await _cv_core._detail_response(session, cv=cv, locale=locale)


async def remove_photo(
    session: AsyncSession,
    *,
    principal,
    cv_id: uuid.UUID,
    expected_version: int | None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    permission_checker.require(principal, _RESOURCE, "update")
    assert principal.user_id is not None
    cv = await _cv_core._load_owned_cv(session, principal=principal, cv_id=cv_id, lock=True)

    if expected_version is not None and expected_version != cv.version:
        raise CvVersionConflictError(current_version=cv.version)

    canvas = dict(cv.canvas_json or {})
    removed = canvas.pop("photo", None)
    cv.canvas_json = canvas
    cv.version += 1
    cv.last_edited_at = _shared.now()
    await session.flush()

    await _cv_core._snapshot_version(
        session, cv=cv, change_source="manual",
        change_summary="photo removed", created_by=principal.user_id,
    )
    await write_audit(
        session,
        action="cv.photo.removed",
        resource_type="cv",
        resource_id=cv.id,
        context=_shared.audit_ctx(principal, ctx),
        before={"document_id": (removed or {}).get("document_id")} if removed else None,
        after={"cv_id": str(cv.id)},
    )
    await session.commit()
    await session.refresh(cv)
    return await _cv_core._detail_response(session, cv=cv, locale=locale)
