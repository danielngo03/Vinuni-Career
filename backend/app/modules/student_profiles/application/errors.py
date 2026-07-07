"""Student-profile application errors mapped to the shared API error envelope.

``details.reason`` carries a stable, user-safe machine token (never a raw DB/enum
code) for clients that branch on it.
"""

from __future__ import annotations

from app.shared.exceptions import ConflictError, ValidationFailedError


class ProfileVersionConflictError(ConflictError):
    """Stale optimistic-locking version on a concurrent profile/section edit."""

    message = "Hồ sơ đã được cập nhật ở nơi khác. Vui lòng tải lại trước khi lưu."

    def __init__(self, *, current_version: int) -> None:
        super().__init__(
            self.message,
            details={"reason": "version_conflict", "current_version": current_version},
        )


class InvalidProfileFieldError(ValidationFailedError):
    """A profile field value is outside the allowed vocabulary."""

    message = "Dữ liệu hồ sơ không hợp lệ. Vui lòng kiểm tra lại."

    def __init__(self, *, field: str) -> None:
        super().__init__(self.message, details={"reason": "invalid_field", "field": field})
