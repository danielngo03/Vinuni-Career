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


async def save_upload_meta(
    *,
    file: UploadFile,
    folder: str,
    allowed_mime: set[str],
    max_bytes: int,
) -> tuple[str, int, str]:
    """Like :func:`save_upload` but also returns ``(key, size_bytes, content_type)``.

    Used by messaging attachments, which need the size for the response + ledger.
    """

    from app.modules.documents.infrastructure.storage import (
        get_storage as get_storage_backend,
    )

    content_type = file.content_type or "application/octet-stream"
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
    if not data:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="file_empty"
        )
    ext = _ext_for_mime(content_type)
    key = f"{folder}/{uuid.uuid4().hex}{ext}"
    get_storage_backend().save(key, data)
    return key, len(data), content_type


def load_file(key: str) -> bytes:
    """Read a stored file by its internal key (never exposes the key/path)."""

    from app.modules.documents.infrastructure.storage import (
        get_storage as get_storage_backend,
    )

    return get_storage_backend().load(key)


def delete_file(key: str) -> None:
    from app.modules.documents.infrastructure.storage import (
        get_storage as get_storage_backend,
    )

    try:
        get_storage_backend().delete(key)
    except Exception:  # noqa: BLE001 - best-effort cleanup
        pass


def _ext_for_mime(mime: str) -> str:
    return {
        "application/pdf": ".pdf",
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "text/plain": ".txt",
        "text/csv": ".csv",
        "application/zip": ".zip",
        "application/msword": ".doc",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
        "application/vnd.ms-excel": ".xls",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
        "application/vnd.ms-powerpoint": ".ppt",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    }.get(mime, "")
