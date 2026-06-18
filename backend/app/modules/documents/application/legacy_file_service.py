from __future__ import annotations

from uuid import uuid4

from sqlalchemy.orm import Session

from app.platform.database.models import File
from app.platform.storage import get_storage
from app.shared.config import settings
from app.shared.errors import AppError, ErrorCode


def store_upload(
    db: Session,
    *,
    uploader_id: str,
    file_name: str,
    content_type: str,
    content: bytes,
    is_public: bool,
) -> File:
    max_bytes = settings.max_upload_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise AppError(
            code=ErrorCode.BAD_REQUEST,
            message="File size exceeds the 5MB limit",
            status_code=400,
        )
    key = f"{uploader_id}/{uuid4()}-{file_name or 'upload.bin'}"
    stored = get_storage().put_bytes(key, content, content_type)
    file = File(
        uploader_id=uploader_id,
        file_name=file_name or stored.key,
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
