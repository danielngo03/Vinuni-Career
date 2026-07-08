"""Cursor and offset pagination helpers.

Cursor pagination is the default for mutable lists; offset pagination is only for
small admin/static lookup lists (``docs/API_CONTRACTS.md``). Cursors are opaque,
URL-safe base64 tokens — clients must not parse them.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any

from app.shared.exceptions import ValidationFailedError

DEFAULT_LIMIT = 20
MAX_LIMIT = 100


def encode_cursor(payload: dict[str, Any]) -> str:
    """Encode a cursor payload into an opaque URL-safe token."""

    raw = json.dumps(payload, separators=(",", ":"), default=str).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def decode_cursor(token: str | None) -> dict[str, Any] | None:
    """Decode an opaque cursor token, raising a user-safe error if malformed."""

    if not token:
        return None
    try:
        raw = base64.urlsafe_b64decode(token.encode("ascii"))
        decoded = json.loads(raw.decode("utf-8"))
    except (ValueError, json.JSONDecodeError) as exc:
        raise ValidationFailedError("Con trỏ phân trang không hợp lệ.") from exc
    if not isinstance(decoded, dict):
        raise ValidationFailedError("Con trỏ phân trang không hợp lệ.")
    return decoded


def clamp_limit(limit: int | None, *, default: int = DEFAULT_LIMIT) -> int:
    """Clamp a requested page size into the allowed range."""

    if limit is None:
        return default
    if limit < 1:
        return 1
    return min(limit, MAX_LIMIT)


@dataclass(slots=True)
class CursorPage:
    """A single page of cursor-paginated results."""

    items: list[Any]
    next_cursor: str | None
    limit: int


@dataclass(slots=True)
class OffsetParams:
    """Offset pagination parameters for small admin/static lists."""

    page: int = 1
    page_size: int = DEFAULT_LIMIT

    @property
    def offset(self) -> int:
        return (max(self.page, 1) - 1) * self.limit

    @property
    def limit(self) -> int:
        return clamp_limit(self.page_size)


def build_cursor_page(
    rows: list[Any],
    *,
    limit: int,
    cursor_builder: Any,
) -> CursorPage:
    """Build a :class:`CursorPage` from one extra-fetched row of lookahead.

    Pass ``limit + 1`` rows: if the extra row exists there is a next page, and
    ``cursor_builder(last_returned_row)`` produces its opaque cursor.
    """

    has_more = len(rows) > limit
    items = rows[:limit]
    next_cursor = encode_cursor(cursor_builder(items[-1])) if has_more and items else None
    return CursorPage(items=items, next_cursor=next_cursor, limit=limit)
