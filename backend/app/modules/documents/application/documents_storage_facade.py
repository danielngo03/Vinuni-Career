"""Internal blob-storage facade for cross-module media surfaces.

``documents.infrastructure.storage`` is the platform's one raw byte-storage
seam (local filesystem today, S3/MinIO later). Other modules that store their
own images (organization logos, student avatars, advertising creatives) go
through this thin facade instead of importing ``documents.infrastructure``
directly, so the module boundary holds (`docs/ARCHITECTURE.md`: communicate
through interfaces/read models). This is intentionally NOT document/CV-domain
logic — it only forwards to the shared byte-storage backend.
"""

from __future__ import annotations

from typing import Any

from app.modules.documents.infrastructure import storage as _storage
from app.modules.documents.infrastructure.storage import StorageBackend

StorageError = _storage.StorageError
SignedTokenError = _storage.SignedTokenError


def get_storage() -> StorageBackend:
    """Return the process-wide storage backend (test seam included)."""

    return _storage.get_storage()


def make_signed_token(payload: dict[str, Any], *, ttl_seconds: int | None = None) -> str:
    """Mint an opaque, expiring signed-access token for a resource reference.

    The payload must reference a resource (``kind`` + ids), never a storage key —
    the resolver looks the key up server-side. Lets other modules (e.g.
    organization company documents) hand out safe delivery URLs without importing
    ``documents.infrastructure`` directly.
    """

    return _storage.make_signed_token(payload, ttl_seconds=ttl_seconds)


def verify_signed_token(token: str) -> dict[str, Any]:
    """Validate signature + expiry; return the payload or raise ``SignedTokenError``."""

    return _storage.verify_signed_token(token)


def save(key: str, data: bytes) -> None:
    _storage.get_storage().save(key, data)


def load(key: str) -> bytes:
    return _storage.get_storage().load(key)


def exists(key: str) -> bool:
    return _storage.get_storage().exists(key)


def delete(key: str) -> None:
    _storage.get_storage().delete(key)
