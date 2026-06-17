from __future__ import annotations

from uuid import uuid4

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.infra.database.models import File
from app.infra.storage import get_storage


async def store_upload(
    db: Session,
    *,
    uploader_id: str,
    upload: UploadFile,
    is_public: bool,
) -> File:
    content = await upload.read()
    max_bytes = settings.max_upload_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds {settings.max_upload_mb} MB",
        )
    content_type = upload.content_type or "application/octet-stream"
    key = f"{uploader_id}/{uuid4()}-{upload.filename or 'upload.bin'}"
    stored = get_storage().put_bytes(key, content, content_type)
    file = File(
        uploader_id=uploader_id,
        file_name=upload.filename or stored.key,
        file_url=stored.url,
        is_public=is_public,
        file_type=content_type,
    )
    db.add(file)
    db.commit()
    db.refresh(file)
    return file


def signed_file_url(key: str) -> str:
    return get_storage().signed_url(key, settings.signed_url_ttl_seconds)
