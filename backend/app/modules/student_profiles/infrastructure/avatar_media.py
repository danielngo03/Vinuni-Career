"""Student avatar media validation + storage-key helpers.

Avatar images are private by default — access is via signed URLs, not raw paths.
Only PNG / JPEG / WebP are accepted; magic-byte validation is authoritative.
The internal ``avatar_path`` storage key is never returned to any client.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from uuid import UUID

ALLOWED_CONTENT_TYPES = frozenset({"image/png", "image/jpeg", "image/webp"})

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_JPEG_MAGIC = b"\xff\xd8\xff"
_RIFF_MAGIC = b"RIFF"
_WEBP_MAGIC = b"WEBP"

_EXT_TO_MEDIA_TYPE = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


@dataclass(slots=True)
class AvatarMedia:
    media_type: str
    extension: str


_REASONS: dict[str, tuple[str, str]] = {
    "empty_file": (
        "Tệp trống. Hãy chọn một tệp ảnh hợp lệ.",
        "The file is empty. Choose a valid image.",
    ),
    "file_too_large": (
        "Tệp quá lớn. Hãy chọn ảnh nhỏ hơn 3 MB.",
        "The file is too large. Choose an image under 3 MB.",
    ),
    "unsupported_image_type": (
        "Định dạng ảnh không hợp lệ. Hãy tải lên ảnh PNG, JPEG hoặc WebP.",
        "Unsupported image format. Upload a PNG, JPEG, or WebP image.",
    ),
}


class AvatarValidationError(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        self.message_vi, self.message_en = _REASONS.get(
            reason, _REASONS["unsupported_image_type"]
        )
        super().__init__(reason)


def sniff_image(data: bytes) -> AvatarMedia | None:
    if data.startswith(_PNG_MAGIC):
        return AvatarMedia("image/png", ".png")
    if data.startswith(_JPEG_MAGIC):
        return AvatarMedia("image/jpeg", ".jpg")
    if len(data) >= 12 and data[0:4] == _RIFF_MAGIC and data[8:12] == _WEBP_MAGIC:
        return AvatarMedia("image/webp", ".webp")
    return None


def validate_avatar(data: bytes, content_type: str | None, *, max_bytes: int) -> AvatarMedia:
    if not data:
        raise AvatarValidationError("empty_file")
    if len(data) > max_bytes:
        raise AvatarValidationError("file_too_large")
    if content_type and content_type.split(";")[0].strip().lower() not in ALLOWED_CONTENT_TYPES:
        raise AvatarValidationError("unsupported_image_type")
    media = sniff_image(data)
    if media is None:
        raise AvatarValidationError("unsupported_image_type")
    return media


def storage_key_for(user_id: UUID, asset_id: UUID, extension: str) -> str:
    return f"student-avatars/{user_id}/{asset_id}{extension}"


def media_type_for_key(storage_key: str) -> str:
    suffix = PurePosixPath(storage_key).suffix.lower()
    return _EXT_TO_MEDIA_TYPE.get(suffix, "application/octet-stream")
