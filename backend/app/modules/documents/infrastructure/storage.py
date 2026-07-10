"""File storage abstraction + HMAC signed access tokens.

Design (``docs/SECURITY_PRIVACY.md``, ``.claude/rules/backend.md``):

- Domain code stores/loads bytes by an internal ``storage_key`` only. The key is
  never returned in any API response or written to logs.
- Downloads are authorized by an opaque HMAC-signed token with a short TTL. The
  token references a *resource* (``kind`` + ``id``), **not** a raw storage path:
  the download endpoint resolves the storage key server-side from the DB. So even
  a decoded token never reveals a storage path.
- Tokens are tamper-evident (HMAC-SHA256 over the canonical payload) and expire.

The default backend is a local filesystem under ``LOCAL_STORAGE_DIR``. Setting
``STORAGE_BACKEND=gcs`` + ``GCS_BUCKET_NAME`` switches every caller to Google
Cloud Storage without any schema change (keys are opaque strings either way).
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


class GcsStorageBackend:
    """Google Cloud Storage-backed storage for Cloud Run / production.

    Credentials come from Application Default Credentials (the Cloud Run
    service account in production, ``gcloud auth application-default login``
    locally). Bucket must stay private; all reads flow through the app's
    RBAC/signed-token download endpoints, never public object URLs.
    """

    def __init__(self, bucket_name: str, *, prefix: str = "") -> None:
        try:
            from google.cloud import storage as gcs
        except ImportError as exc:  # pragma: no cover - dependency is in pyproject
            raise StorageError("google-cloud-storage is not installed") from exc
        if not bucket_name:
            raise StorageError("GCS_BUCKET_NAME is not configured")
        self._client = gcs.Client()
        self._bucket = self._client.bucket(bucket_name)
        self._prefix = prefix.strip("/")

    def _blob(self, key: str):  # noqa: ANN202 - google types are untyped here
        norm = key.lstrip("/")
        if not norm or ".." in norm.split("/"):
            raise StorageError("invalid storage key")
        name = f"{self._prefix}/{norm}" if self._prefix else norm
        return self._bucket.blob(name)

    def save(self, key: str, data: bytes) -> None:
        blob = self._blob(key)
        try:
            blob.upload_from_string(data, content_type="application/octet-stream")
        except Exception as exc:  # noqa: BLE001 - normalize provider errors
            raise StorageError("object write failed") from exc

    def load(self, key: str) -> bytes:
        blob = self._blob(key)
        try:
            return blob.download_as_bytes()
        except Exception as exc:  # noqa: BLE001 - includes NotFound
            raise StorageError("object not found") from exc

    def exists(self, key: str) -> bool:
        try:
            return bool(self._blob(key).exists())
        except StorageError:
            return False
        except Exception:  # noqa: BLE001
            return False

    def delete(self, key: str) -> None:
        try:
            self._blob(key).delete()
        except StorageError:
            return
        except Exception:  # noqa: BLE001 - missing objects are fine on delete
            return


_backend: StorageBackend | None = None


def _build_backend() -> StorageBackend:
    settings = get_settings()
    kind = (settings.storage_backend or "local").strip().lower()
    if kind == "local":
        return LocalStorageBackend(settings.local_storage_dir)
    if kind == "gcs":
        return GcsStorageBackend(settings.gcs_bucket_name, prefix=settings.gcs_key_prefix)
    raise StorageError(f"unsupported STORAGE_BACKEND: {kind}")


def get_storage() -> StorageBackend:
    """Return the process-wide storage backend chosen by ``STORAGE_BACKEND``."""

    global _backend
    if _backend is None:
        _backend = _build_backend()
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
