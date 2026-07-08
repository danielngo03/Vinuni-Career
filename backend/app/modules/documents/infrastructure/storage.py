"""File storage abstraction + HMAC signed access tokens.

Design (``docs/SECURITY_PRIVACY.md``, ``.claude/rules/backend.md``):

- Domain code stores/loads bytes by an internal ``storage_key`` only. The key is
  never returned in any API response or written to logs.
- Downloads are authorized by an opaque HMAC-signed token with a short TTL. The
  token references a *resource* (``kind`` + ``id``), **not** a raw storage path:
  the download endpoint resolves the storage key server-side from the DB. So even
  a decoded token never reveals a storage path.
- Tokens are tamper-evident (HMAC-SHA256 over the canonical payload) and expire.

The default backend is a local filesystem under ``LOCAL_STORAGE_DIR``. The same
``StorageBackend`` interface is later backed by S3/MinIO without changing callers.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from pathlib import Path
from typing import Any, Protocol

from app.core.config import get_settings


class StorageError(Exception):
    """Raised when a stored object cannot be read/written."""


class StorageBackend(Protocol):
    """Abstract byte storage addressed by an internal key."""

    def save(self, key: str, data: bytes) -> None: ...

    def load(self, key: str) -> bytes: ...

    def exists(self, key: str) -> bool: ...

    def delete(self, key: str) -> None: ...


class LocalStorageBackend:
    """Filesystem-backed storage rooted at ``LOCAL_STORAGE_DIR``.

    Keys are normalized and confined to the storage root (path-traversal safe).
    """

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        # Reject absolute keys / traversal; keys are server-generated but defend anyway.
        norm = Path(key.lstrip("/"))
        target = (self._root / norm).resolve()
        if self._root != target and self._root not in target.parents:
            raise StorageError("invalid storage key")
        return target

    def save(self, key: str, data: bytes) -> None:
        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def load(self, key: str) -> bytes:
        path = self._resolve(key)
        try:
            return path.read_bytes()
        except OSError as exc:
            raise StorageError("object not found") from exc

    def exists(self, key: str) -> bool:
        try:
            return self._resolve(key).is_file()
        except StorageError:
            return False

    def delete(self, key: str) -> None:
        try:
            self._resolve(key).unlink(missing_ok=True)
        except StorageError:
            return


_backend: StorageBackend | None = None


def get_storage() -> StorageBackend:
    """Return the process-wide storage backend chosen by ``STORAGE_BACKEND``."""

    global _backend
    if _backend is None:
        settings = get_settings()
        # Only the local backend is wired for now; cloud backends slot in here.
        _backend = LocalStorageBackend(settings.local_storage_dir)
    return _backend


def set_storage(backend: StorageBackend | None) -> None:
    """Override the storage backend (test seam)."""

    global _backend
    _backend = backend


# --------------------------------------------------------------------------- #
# Signed access tokens                                                         #
# --------------------------------------------------------------------------- #


class SignedTokenError(Exception):
    """Raised when a signed token is malformed, tampered, or expired."""


def _secret() -> bytes:
    return get_settings().jwt_secret_key.encode("utf-8")


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64d(token: str) -> bytes:
    pad = "=" * (-len(token) % 4)
    return base64.urlsafe_b64decode(token + pad)


def make_signed_token(payload: dict[str, Any], *, ttl_seconds: int | None = None) -> str:
    """Build an opaque, tamper-evident, expiring token for a resource.

    ``payload`` must NOT contain a storage path — only a resource reference
    (``kind`` + ``id``) plus access metadata (purpose, watermark, accessor).
    """

    ttl = ttl_seconds if ttl_seconds is not None else get_settings().signed_url_ttl_seconds
    body = dict(payload)
    body["exp"] = int(time.time()) + ttl
    raw = json.dumps(body, separators=(",", ":"), sort_keys=True, default=str).encode("utf-8")
    encoded = _b64e(raw)
    sig = hmac.new(_secret(), encoded.encode("ascii"), hashlib.sha256).digest()
    return f"{encoded}.{_b64e(sig)}"


def verify_signed_token(token: str) -> dict[str, Any]:
    """Validate signature + expiry; return the payload or raise ``SignedTokenError``."""

    try:
        encoded, _, sig_part = token.partition(".")
        if not encoded or not sig_part:
            raise SignedTokenError("malformed token")
        expected = hmac.new(_secret(), encoded.encode("ascii"), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _b64d(sig_part)):
            raise SignedTokenError("bad signature")
        payload = json.loads(_b64d(encoded).decode("utf-8"))
    except SignedTokenError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise SignedTokenError("malformed token") from exc

    if not isinstance(payload, dict):
        raise SignedTokenError("malformed token")
    exp = payload.get("exp")
    if not isinstance(exp, int) or exp < int(time.time()):
        raise SignedTokenError("expired token")
    return payload


def token_hash(token: str) -> str:
    """Stable hash of a signed token for audit (never store the token itself)."""

    return hashlib.sha256(token.encode("utf-8")).hexdigest()
