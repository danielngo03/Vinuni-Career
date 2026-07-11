"""Campaign-creative media validation, storage keys, and the public-URL chokepoint.

Campaign creatives are PUBLIC marketing assets (``docs/PRODUCT_INTERACTION_VISUAL_
REALISM_SPEC.md`` §5). Unlike CV files they are not behind a signed token, so the
magic-byte allowlist + size cap here are the only gate before bytes become
publicly servable. Validation is magic-byte first: the declared ``Content-Type``
and the filename are untrusted hints, so a renamed ``.txt`` (or an ``image/png``
declaration carrying non-image bytes) is rejected. Only PNG / JPEG / WebP pass.

The internal ``image_path`` storage key is never returned to a client.
:func:`public_creative_url` is the single place creative exposure is decided, so a
raw storage path / object key can never leak into a public response (it mirrors
``organization.api.public_presenters.public_logo_url``).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from uuid import UUID

from app.core.config import get_settings

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
class CreativeMedia:
    """Resolved, validated image identity (derived from magic bytes)."""

    media_type: str
    extension: str


# reason code -> user-safe (vi, en). Reasons are stable; messages are friendly.
_REASONS: dict[str, tuple[str, str]] = {
    "empty_file": (
        "Tệp trống. Hãy chọn một tệp ảnh banner hợp lệ.",
        "The file is empty. Choose a valid banner image.",
    ),
    "file_too_large": (
        "Tệp quá lớn. Hãy chọn ảnh banner nhỏ hơn.",
        "The file is too large. Choose a smaller banner image.",
    ),
    "unsupported_image_type": (
        "Định dạng ảnh không hợp lệ. Hãy tải lên banner dạng PNG, JPEG hoặc WebP.",
        "Unsupported image format. Upload a PNG, JPEG, or WebP banner.",
    ),
}


class CreativeValidationError(Exception):
    """A creative upload failed validation; carries a stable, user-safe reason."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        self.message_vi, self.message_en = _REASONS.get(reason, _REASONS["unsupported_image_type"])
        super().__init__(reason)


def sniff_image(data: bytes) -> CreativeMedia | None:
    """Return the image identity from magic bytes, or ``None`` if not an image."""

    if data.startswith(_PNG_MAGIC):
        return CreativeMedia("image/png", ".png")
    if data.startswith(_JPEG_MAGIC):
        return CreativeMedia("image/jpeg", ".jpg")
    if len(data) >= 12 and data[0:4] == _RIFF_MAGIC and data[8:12] == _WEBP_MAGIC:
        return CreativeMedia("image/webp", ".webp")
    return None


def validate_creative(data: bytes, content_type: str | None, *, max_bytes: int) -> CreativeMedia:
    """Validate uploaded creative bytes and return the resolved media identity.

    Order: empty -> size -> declared content-type allowlist -> magic-byte sniff.
    Raises :class:`CreativeValidationError` with a stable reason on any failure.
    """

    if not data:
        raise CreativeValidationError("empty_file")
    if len(data) > max_bytes:
        raise CreativeValidationError("file_too_large")
    if content_type and content_type.split(";")[0].strip().lower() not in ALLOWED_CONTENT_TYPES:
        raise CreativeValidationError("unsupported_image_type")
    media = sniff_image(data)
    if media is None:
        raise CreativeValidationError("unsupported_image_type")
    return media


def storage_key_for(placement_id: UUID, asset_id: UUID, extension: str) -> str:
    """Internal storage key for a creative (never exposed to clients)."""

    return f"campaign-creatives/{placement_id}/{asset_id}{extension}"


def media_type_for_key(storage_key: str) -> str:
    """Resolve the response ``Content-Type`` for a stored creative from its key."""

    suffix = PurePosixPath(storage_key).suffix.lower()
    return _EXT_TO_MEDIA_TYPE.get(suffix, "application/octet-stream")


def public_creative_url(creative_id: UUID, *, version: int) -> str:
    """Stable public serve URL for a creative — never a raw storage key.

    Returns ``GET /api/v1/advertising/creatives/{id}/image`` with a ``?v=``
    cache-busting key. The serve endpoint independently re-checks that the
    creative is approved and its placement is active, so a stale URL for a now
    paused/expired placement resolves to ``404`` instead of leaking bytes.
    """

    base = get_settings().app_url.rstrip("/")
    return f"{base}/api/v1/advertising/creatives/{creative_id}/image?v={version}"
