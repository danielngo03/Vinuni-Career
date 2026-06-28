from __future__ import annotations

from collections.abc import Iterable
from threading import Lock


class APIKeyPool:
    """In-process API key rotation with temporary exhaustion tracking."""

    def __init__(self, api_keys: Iterable[str | None]) -> None:
        seen: set[str] = set()
        self._keys = []
        for api_key in api_keys:
            normalized = (api_key or "").strip()
            if normalized and normalized not in seen:
                self._keys.append(normalized)
                seen.add(normalized)
        self._exhausted: set[str] = set()
        self._cursor = 0
        self._lock = Lock()

    def available_keys(self) -> list[str]:
        with self._lock:
            return self._available_keys_locked()

    def claim_keys_for_request(self) -> list[str]:
        """Return keys for one request and advance the cursor before network I/O."""
        with self._lock:
            keys = self._available_keys_locked()
            if keys:
                first_key_index = self._keys.index(keys[0])
                self._cursor = (first_key_index + 1) % len(self._keys)
            return keys

    def mark_exhausted(self, api_key: str) -> None:
        with self._lock:
            self._exhausted.add(api_key)

    def record_success(self, api_key: str) -> None:
        with self._lock:
            if api_key in self._keys:
                self._cursor = (self._keys.index(api_key) + 1) % len(self._keys)

    def has_available_key(self) -> bool:
        return bool(self.available_keys())

    def _available_keys_locked(self) -> list[str]:
        if not self._keys:
            return []
        ordered = self._keys[self._cursor :] + self._keys[: self._cursor]
        return [key for key in ordered if key not in self._exhausted]


def looks_like_key_exhaustion(status_code: int, detail: str) -> bool:
    normalized = detail.lower()
    if status_code in {401, 402, 403, 429}:
        return True
    if status_code != 400:
        return False
    markers = (
        "api key not valid",
        "api_key_invalid",
        "key invalid",
        "permission_denied",
        "project has been denied access",
        "quota",
        "rate limit",
        "ratelimit",
        "resource_exhausted",
        "resource exhausted",
        "userratelimitexceeded",
        "ratelimitexceeded",
        "quotaexceeded",
        "exceeded your current quota",
    )
    return any(marker in normalized for marker in markers)
