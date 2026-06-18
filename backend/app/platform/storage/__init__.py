"""app/platform/storage — Object storage (S3/local). Canonical location."""
from __future__ import annotations

from app.platform.storage.factory import get_storage

__all__ = ["get_storage"]
