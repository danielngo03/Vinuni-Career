from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class StoredObject:
    key: str
    url: str
    content_type: str
    size_bytes: int


class StorageClient(Protocol):
    def put_bytes(self, key: str, content: bytes, content_type: str) -> StoredObject: ...

    def signed_url(self, key: str, ttl_seconds: int) -> str: ...
