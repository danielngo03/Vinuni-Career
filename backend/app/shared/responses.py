"""Helpers that build the canonical API response envelopes.

Shapes follow ``docs/API_CONTRACTS.md``:

- object:  ``{"data": {...}, "meta": {...}}``
- list:    ``{"data": [...], "page": {"next_cursor": ..., "limit": ...}}``
- error:   ``{"error": {"code", "message", "details", "request_id"}}``
"""

from __future__ import annotations

from typing import Any


def success(data: Any, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"data": data}
    if meta is not None:
        body["meta"] = meta
    return body


def paginated(
    data: list[Any],
    *,
    next_cursor: str | None = None,
    limit: int,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "data": data,
        "page": {"next_cursor": next_cursor, "limit": limit},
    }
    if meta is not None:
        body["meta"] = meta
    return body


def error_envelope(
    *,
    code: str,
    message: str,
    request_id: str | None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
            "request_id": request_id,
        }
    }
