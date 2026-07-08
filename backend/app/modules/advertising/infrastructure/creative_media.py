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
        self.message_vi, self.message_en = _REASONS.get(
            reason, _REASONS["unsupported_image_type"]
        )
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


def _png_dimensions(data: bytes) -> tuple[int, int] | None:
    # 8-byte signature + IHDR: length(4)+type(4) then width(4)+height(4) @ offset 16.
    if len(data) < 24:
        return None
    width = int.from_bytes(data[16:20], "big")
    height = int.from_bytes(data[20:24], "big")
    return (width, height) if width and height else None


def _jpeg_dimensions(data: bytes) -> tuple[int, int] | None:
    # Walk the JPEG marker segments to the first Start-Of-Frame (SOFn) marker.
    i = 2
    n = len(data)
    while i + 9 < n:
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        # SOF0..SOF15 carry the frame dimensions, except DHT/JPG/DAC (C4/C8/CC).
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            height = int.from_bytes(data[i + 5 : i + 7], "big")
            width = int.from_bytes(data[i + 7 : i + 9], "big")
            return (width, height) if width and height else None
        if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
            i += 2  # standalone markers carry no length
            continue
        seg_len = int.from_bytes(data[i + 2 : i + 4], "big")
        if seg_len < 2:
            return None
        i += 2 + seg_len
    return None


def _webp_dimensions(data: bytes) -> tuple[int, int] | None:
    if len(data) < 30:
        return None
    fourcc = data[12:16]
    if fourcc == b"VP8X":
        width = 1 + int.from_bytes(data[24:27], "little")
        height = 1 + int.from_bytes(data[27:30], "little")
        return (width, height)
    if fourcc == b"VP8 ":
        # Lossy: 3-byte frame tag, 3-byte start code, then 14-bit w/h at offset 26.
        if data[23:26] != b"\x9d\x01\x2a":
            return None
        width = int.from_bytes(data[26:28], "little") & 0x3FFF
        height = int.from_bytes(data[28:30], "little") & 0x3FFF
        return (width, height) if width and height else None
    if fourcc == b"VP8L" and data[20] == 0x2F:
        bits = int.from_bytes(data[21:25], "little")
        width = (bits & 0x3FFF) + 1
        height = ((bits >> 14) & 0x3FFF) + 1
        return (width, height)
    return None


def sniff_dimensions(data: bytes) -> tuple[int, int] | None:
    """Best-effort (width, height) from image bytes; ``None`` if not parseable.

    Pure header parsing (no image library) for the creative-policy dimension
    pre-check. A parse failure returns ``None`` so the dimension check is simply
    skipped — it never blocks an upload.
    """

    try:
        if data.startswith(_PNG_MAGIC):
            return _png_dimensions(data)
        if data.startswith(_JPEG_MAGIC):
            return _jpeg_dimensions(data)
        if len(data) >= 12 and data[0:4] == _RIFF_MAGIC and data[8:12] == _WEBP_MAGIC:
            return _webp_dimensions(data)
    except (IndexError, ValueError):
        return None
    return None


def validate_creative(
    data: bytes, content_type: str | None, *, max_bytes: int
) -> CreativeMedia:
    """Validate uploaded creative bytes and return the resolved media identity.

    Order: empty -> size -> declared content-type allowlist -> magic-byte sniff.
    Raises :class:`CreativeValidationError` with a stable reason on any failure.
    """

    if not data:
        raise CreativeValidationError("empty_file")
    if len(data) > max_bytes:
        raise CreativeValidationError("file_too_large")
    if (
        content_type
        and content_type.split(";")[0].strip().lower() not in ALLOWED_CONTENT_TYPES
    ):
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
