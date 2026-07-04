"""Discovery application errors mapped to the API error envelope.

User-safe codes/messages only — no internal vocabulary leaks into ``message``.
"""

from __future__ import annotations

from app.shared.exceptions import ValidationFailedError


class InvalidDiscoveryEventError(ValidationFailedError):
    """An event field failed vocabulary validation (type/surface/target)."""

    message = "Dữ liệu sự kiện không hợp lệ."

    def __init__(self, *, field: str) -> None:
        super().__init__(details={"field": field})
