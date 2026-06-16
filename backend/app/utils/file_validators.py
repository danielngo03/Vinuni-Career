from __future__ import annotations

from fastapi import HTTPException, UploadFile, status

ALLOWED_CV_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
}


def validate_cv_upload(upload: UploadFile) -> None:
    if upload.content_type not in ALLOWED_CV_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported CV content type: {upload.content_type}",
        )
