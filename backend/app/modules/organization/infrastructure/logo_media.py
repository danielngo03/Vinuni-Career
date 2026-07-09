"""Organization logo media validation + storage-key helpers.

Org logos are **public** marketing assets (``docs/API_CONTRACTS.md`` "Organization
Media And Logo Delivery", ``docs/SECURITY_PRIVACY.md`` "Public Media And
Organization Assets"). Unlike CV files they are not behind a signed token, so the
validation here is the only gate before bytes become publicly servable.

Validation is intentionally magic-byte first: the declared ``Content-Type`` and
the filename extension are untrusted hints, so a ``.txt`` renamed to ``.png`` (or
a declared ``image/png`` carrying non-image bytes) is rejected. Only PNG / JPEG /
WebP are accepted. Storage keys are internal and never returned to clients.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from uuid import UUID

# Allowed declared content types (a secondary hint; magic bytes are authoritative).
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
class LogoMedia:
    """Resolved, validated image identity (derived from magic bytes)."""

    media_type: str
    extension: str


# reason code -> user-safe (vi, en). Reasons are stable; messages are friendly.
_REASONS: dict[str, tuple[str, str]] = {
    "empty_file": (
        "Tệp trống. Hãy chọn một tệp ảnh logo hợp lệ.",
        "The file is empty. Choose a valid logo image.",
    ),
    "file_too_large": (
        "Tệp quá lớn. Hãy chọn ảnh logo nhỏ hơn.",
        "The file is too large. Choose a smaller logo image.",
    ),
    "unsupported_image_type": (
        "Định dạng ảnh không hợp lệ. Hãy tải lên logo dạng PNG, JPEG hoặc WebP.",
        "Unsupported image format. Upload a PNG, JPEG, or WebP logo.",
    ),
}


class LogoValidationError(Exception):
    """A logo upload failed validation; carries a stable, user-safe reason."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        self.message_vi, self.message_en = _REASONS.get(reason, _REASONS["unsupported_image_type"])
        super().__init__(reason)


def sniff_image(data: bytes) -> LogoMedia | None:
    """Return the image identity from magic bytes, or ``None`` if not an image."""

    if data.startswith(_PNG_MAGIC):
        return LogoMedia("image/png", ".png")
    if data.startswith(_JPEG_MAGIC):
        return LogoMedia("image/jpeg", ".jpg")
    if len(data) >= 12 and data[0:4] == _RIFF_MAGIC and data[8:12] == _WEBP_MAGIC:
        return LogoMedia("image/webp", ".webp")
    return None


def validate_logo(data: bytes, content_type: str | None, *, max_bytes: int) -> LogoMedia:
    """Validate an uploaded logo and return its resolved media identity.

    Order: empty -> size -> declared content-type allowlist -> magic-byte sniff.
    Raises :class:`LogoValidationError` with a stable reason on any failure.
    """

    if not data:
        raise LogoValidationError("empty_file")
    if len(data) > max_bytes:
        raise LogoValidationError("file_too_large")
    # Declared type is a cheap pre-filter; magic bytes below are authoritative.
    if content_type and content_type.split(";")[0].strip().lower() not in ALLOWED_CONTENT_TYPES:
        raise LogoValidationError("unsupported_image_type")
    media = sniff_image(data)
    if media is None:
        raise LogoValidationError("unsupported_image_type")
    return media


def storage_key_for(org_id: UUID, asset_id: UUID, extension: str) -> str:
    """Internal storage key for an org logo (never exposed to clients)."""

    return f"org-logos/{org_id}/{asset_id}{extension}"


def media_type_for_key(storage_key: str) -> str:
    """Resolve the response ``Content-Type`` for a stored logo from its key."""

    suffix = PurePosixPath(storage_key).suffix.lower()
    return _EXT_TO_MEDIA_TYPE.get(suffix, "application/octet-stream")
