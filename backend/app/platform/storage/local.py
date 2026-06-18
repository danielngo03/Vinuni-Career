from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from app.platform.storage.protocols import StoredObject


class LocalStorage:
    def __init__(self, root: str, public_base_url: str) -> None:
        self.root = Path(root)
        self.public_base_url = public_base_url.rstrip("/")
        self.root.mkdir(parents=True, exist_ok=True)

    def put_bytes(self, key: str, content: bytes, content_type: str) -> StoredObject:
        clean_key = key.lstrip("/").replace("..", "_")
        destination = self.root / clean_key
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        return StoredObject(
            key=clean_key,
            url=self.signed_url(clean_key, ttl_seconds=0),
            content_type=content_type,
            size_bytes=len(content),
        )

    def signed_url(self, key: str, ttl_seconds: int) -> str:
        suffix = f"?ttl={ttl_seconds}" if ttl_seconds else ""
        return f"{self.public_base_url}/{quote(key)}{suffix}"

    def presigned_upload(
        self,
        key: str,
        content_type: str,
        ttl_seconds: int,
    ) -> dict[str, object]:
        return {
            "url": self.signed_url(key, ttl_seconds),
            "method": "PUT",
            "fields": {"content_type": content_type},
        }
