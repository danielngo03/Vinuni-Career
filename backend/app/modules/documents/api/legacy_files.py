from __future__ import annotations

from fastapi import APIRouter, Depends, Query, UploadFile
from fastapi import File as UploadParam
from sqlalchemy.orm import Session

from app.modules.access.api.auth import get_current_user
from app.modules.documents.application.legacy_file_service import signed_file_url, store_upload
from app.modules.documents.legacy_schemas import FileView, SignedUrlResponse
from app.platform.database.models import File, User
from app.platform.database.session import get_db
from app.shared.config import settings

router = APIRouter()


@router.post("/upload", response_model=FileView, status_code=201)
async def upload_file(
    upload: UploadFile = UploadParam(...),
    is_public: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> File:
    return store_upload(
        db,
        uploader_id=current_user.id,
        file_name=upload.filename or "upload.bin",
        content_type=upload.content_type or "application/octet-stream",
        content=await upload.read(),
        is_public=is_public,
    )


@router.get("/signed-url", response_model=SignedUrlResponse)
def get_signed_url(
    key: str = Query(...),
    _: User = Depends(get_current_user),
) -> SignedUrlResponse:
    return SignedUrlResponse(url=signed_file_url(key), ttl_seconds=settings.signed_url_ttl_seconds)
