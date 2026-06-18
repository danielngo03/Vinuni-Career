from __future__ import annotations

from functools import lru_cache

from app.platform.storage.local import LocalStorage
from app.platform.storage.protocols import StorageClient
from app.platform.storage.s3 import S3Storage
from app.shared.config import settings


@lru_cache
def get_storage() -> StorageClient:
    if settings.storage_backend == "s3":
        return S3Storage(
            bucket=settings.s3_bucket,
            endpoint_url=settings.s3_endpoint_url,
            access_key_id=settings.s3_access_key_id,
            secret_access_key=settings.s3_secret_access_key,
        )
    return LocalStorage(settings.storage_local_root, settings.storage_public_base_url)
