"""Storage backend selection + GCS adapter unit tests.

The GCS client is faked (no network); these tests pin the factory contract so
`STORAGE_BACKEND=gcs` cannot silently fall back to local disk on Cloud Run.
"""

from __future__ import annotations

from unittest import mock

import pytest
from app.core.config import get_settings
from app.modules.documents.infrastructure import storage as storage_mod
from app.modules.documents.infrastructure.storage import (
    GcsStorageBackend,
    LocalStorageBackend,
    StorageError,
    set_storage,
)


@pytest.fixture(autouse=True)
def _reset_storage_singleton():
    set_storage(None)
    yield
    set_storage(None)


def _settings_override(**values):
    settings = get_settings().model_copy(update=values)
    return mock.patch.object(storage_mod, "get_settings", return_value=settings)


def test_factory_defaults_to_local(tmp_path) -> None:
    with _settings_override(storage_backend="local", local_storage_dir=str(tmp_path)):
        backend = storage_mod.get_storage()
    assert isinstance(backend, LocalStorageBackend)


def test_factory_rejects_unknown_backend() -> None:
    with _settings_override(storage_backend="s3"):
        with pytest.raises(StorageError, match="unsupported STORAGE_BACKEND"):
            storage_mod.get_storage()


def test_factory_gcs_requires_bucket() -> None:
    with _settings_override(storage_backend="gcs", gcs_bucket_name=""):
        with pytest.raises(StorageError, match="GCS_BUCKET_NAME"):
            storage_mod.get_storage()


def test_factory_builds_gcs_backend() -> None:
    with _settings_override(
        storage_backend="gcs", gcs_bucket_name="test-bucket", gcs_key_prefix="media"
    ):
        with mock.patch("google.cloud.storage.Client") as client_cls:
            backend = storage_mod.get_storage()
    assert isinstance(backend, GcsStorageBackend)
    client_cls.return_value.bucket.assert_called_once_with("test-bucket")


class _FakeBlob:
    def __init__(self, store: dict[str, bytes], name: str) -> None:
        self._store = store
        self.name = name

    def upload_from_string(self, data: bytes, content_type: str | None = None) -> None:
        self._store[self.name] = data

    def download_as_bytes(self) -> bytes:
        if self.name not in self._store:
            raise KeyError(self.name)
        return self._store[self.name]

    def exists(self) -> bool:
        return self.name in self._store

    def delete(self) -> None:
        if self.name not in self._store:
            raise KeyError(self.name)
        del self._store[self.name]


def _gcs_backend_with_fake_bucket(prefix: str = "") -> tuple[GcsStorageBackend, dict[str, bytes]]:
    store: dict[str, bytes] = {}
    with mock.patch("google.cloud.storage.Client") as client_cls:
        bucket = mock.Mock()
        bucket.blob.side_effect = lambda name: _FakeBlob(store, name)
        client_cls.return_value.bucket.return_value = bucket
        backend = GcsStorageBackend("test-bucket", prefix=prefix)
    return backend, store


def test_gcs_save_load_exists_delete_roundtrip() -> None:
    backend, store = _gcs_backend_with_fake_bucket()
    backend.save("cv-uploads/u1/doc.pdf", b"pdf-bytes")
    assert store == {"cv-uploads/u1/doc.pdf": b"pdf-bytes"}
    assert backend.exists("cv-uploads/u1/doc.pdf") is True
    assert backend.load("cv-uploads/u1/doc.pdf") == b"pdf-bytes"
    backend.delete("cv-uploads/u1/doc.pdf")
    assert backend.exists("cv-uploads/u1/doc.pdf") is False
    # Deleting a missing object is a no-op, mirroring LocalStorageBackend.
    backend.delete("cv-uploads/u1/doc.pdf")


def test_gcs_prefix_is_applied() -> None:
    backend, store = _gcs_backend_with_fake_bucket(prefix="media/")
    backend.save("org-logos/o1/logo.png", b"png")
    assert list(store) == ["media/org-logos/o1/logo.png"]
    assert backend.load("org-logos/o1/logo.png") == b"png"


def test_gcs_load_missing_raises_storage_error() -> None:
    backend, _ = _gcs_backend_with_fake_bucket()
    with pytest.raises(StorageError, match="object not found"):
        backend.load("nope/missing.pdf")


@pytest.mark.parametrize("bad_key", ["", "/", "../secrets", "a/../../b"])
def test_gcs_rejects_traversal_keys(bad_key: str) -> None:
    backend, _ = _gcs_backend_with_fake_bucket()
    with pytest.raises(StorageError, match="invalid storage key"):
        backend.save(bad_key, b"x")
