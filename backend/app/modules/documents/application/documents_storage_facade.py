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

from app.modules.documents.infrastructure import storage as _storage
from app.modules.documents.infrastructure.storage import StorageBackend

StorageError = _storage.StorageError


def get_storage() -> StorageBackend:
    """Return the process-wide storage backend (test seam included)."""

    return _storage.get_storage()


def save(key: str, data: bytes) -> None:
    _storage.get_storage().save(key, data)


def load(key: str) -> bytes:
    return _storage.get_storage().load(key)


def exists(key: str) -> bool:
    return _storage.get_storage().exists(key)


def delete(key: str) -> None:
    _storage.get_storage().delete(key)
