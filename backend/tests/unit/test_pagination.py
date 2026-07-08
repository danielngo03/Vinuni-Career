"""Cursor + offset pagination helpers."""

from __future__ import annotations

import pytest
from app.shared.exceptions import ValidationFailedError
from app.shared.pagination import (
    MAX_LIMIT,
    OffsetParams,
    build_cursor_page,
    clamp_limit,
    decode_cursor,
    encode_cursor,
)


def test_cursor_round_trip() -> None:
    payload = {"created_at": "2026-06-27T00:00:00", "id": "abc"}
    token = encode_cursor(payload)
    assert decode_cursor(token) == payload


def test_decode_none_returns_none() -> None:
    assert decode_cursor(None) is None


def test_decode_invalid_cursor_raises() -> None:
    with pytest.raises(ValidationFailedError):
        decode_cursor("!!!not-base64!!!")


def test_clamp_limit_bounds() -> None:
    assert clamp_limit(None) == 20
    assert clamp_limit(0) == 1
    assert clamp_limit(9999) == MAX_LIMIT


def test_offset_params() -> None:
    params = OffsetParams(page=3, page_size=10)
    assert params.limit == 10
    assert params.offset == 20


def test_build_cursor_page_has_next() -> None:
    rows = [{"id": i} for i in range(21)]  # limit 20 + 1 lookahead
    page = build_cursor_page(rows, limit=20, cursor_builder=lambda r: {"id": r["id"]})
    assert len(page.items) == 20
    assert page.next_cursor is not None
    assert decode_cursor(page.next_cursor) == {"id": 19}


def test_build_cursor_page_no_next() -> None:
    rows = [{"id": i} for i in range(5)]
    page = build_cursor_page(rows, limit=20, cursor_builder=lambda r: {"id": r["id"]})
    assert len(page.items) == 5
    assert page.next_cursor is None
