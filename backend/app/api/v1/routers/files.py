from __future__ import annotations

from fastapi import APIRouter, Depends, Query, UploadFile
from fastapi import File as UploadParam
from sqlalchemy.orm import Session

from app.api.dependencies.auth import get_current_user
from app.core.config import settings
from app.infra.database.models import File, User
from app.infra.database.session import get_db
from app.schemas.files import FileView, SignedUrlResponse
from app.services.file_service import signed_file_url, store_upload

router = APIRouter()


@router.post("/upload", response_model=FileView, status_code=201)
async def upload_file(
    upload: UploadFile = UploadParam(...),
    is_public: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> File:
    return await store_upload(db, uploader_id=current_user.id, upload=upload, is_public=is_public)


@router.get("/signed-url", response_model=SignedUrlResponse)
def get_signed_url(
    key: str = Query(...),
    _: User = Depends(get_current_user),
) -> SignedUrlResponse:
    return SignedUrlResponse(url=signed_file_url(key), ttl_seconds=settings.signed_url_ttl_seconds)
