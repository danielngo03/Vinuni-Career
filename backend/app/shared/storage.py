"""Shared file upload helper.

Wraps the documents module ``LocalStorageBackend`` so any module can save
uploaded files through the same storage abstraction without depending on the
documents module internals.
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException, UploadFile, status


async def save_upload(
    *,
    file: UploadFile,
    folder: str,
    allowed_mime: set[str],
    max_bytes: int,
) -> str:
    """Validate and persist an uploaded file.

    Returns the internal storage key (never exposed in API responses).
    Raises ``HTTPException(422)`` for invalid MIME or size; storage errors
    propagate as-is.
    """
    from app.modules.documents.infrastructure.storage import get_storage as get_storage_backend

    content_type = file.content_type or ""
    if content_type not in allowed_mime:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"file_type_not_allowed:{content_type}",
        )

    data = await file.read()
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"file_too_large:max_{max_bytes // 1024}kb",
        )

    ext = _ext_for_mime(content_type)
    key = f"{folder}/{uuid.uuid4().hex}{ext}"
    backend = get_storage_backend()
    backend.save(key, data)
    return key


def _ext_for_mime(mime: str) -> str:
    return {
        "application/pdf": ".pdf",
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
    }.get(mime, "")
