"""Events-module application errors (ADR-0008).

All map to the shared API error envelope. ``details.reason`` carries a stable,
user-safe machine token (never a raw DB/enum code) for clients that branch on it.
"""

from __future__ import annotations

from app.shared.exceptions import ConflictError, ValidationFailedError


class IllegalEventTransitionError(ConflictError):
    """Requested lifecycle transition is not legal from the current status."""

    message = "Không thể thực hiện thao tác này ở trạng thái hiện tại của sự kiện."

    def __init__(self, *, event: str) -> None:
        super().__init__(
            self.message,
            details={"reason": "illegal_transition", "event": event},
        )


class EventNotEditableError(ConflictError):
    """The event is in a state that cannot be edited (e.g. published)."""

    message = "Sự kiện này không thể chỉnh sửa ở trạng thái hiện tại."

    def __init__(self) -> None:
        super().__init__(self.message, details={"reason": "not_editable"})


class EventVersionConflictError(ConflictError):
    """Stale optimistic-locking version on a concurrent edit."""

    message = "Nội dung đã được cập nhật ở nơi khác. Vui lòng tải lại trước khi lưu."

    def __init__(self) -> None:
        super().__init__(self.message, details={"reason": "version_conflict"})


class InvalidEventFieldError(ValidationFailedError):
    """An event field value is outside the allowed vocabulary or invalid."""

    message = "Dữ liệu sự kiện không hợp lệ. Vui lòng kiểm tra lại."

    def __init__(self, *, field: str) -> None:
        super().__init__(
            self.message, details={"reason": "invalid_field", "field": field}
        )


class RegistrationClosedError(ConflictError):
    """Registration is past its deadline (``registration_closes_at``/``starts_at``)."""

    message = "Đã hết hạn đăng ký cho sự kiện này."

    def __init__(self) -> None:
        super().__init__(self.message, details={"reason": "registration_closed"})


class RegistrationNotOpenError(ConflictError):
    """Registration has not opened yet (``registration_opens_at`` in the future)."""

    message = "Chưa đến thời gian mở đăng ký cho sự kiện này."

    def __init__(self) -> None:
        super().__init__(self.message, details={"reason": "registration_not_open"})


class EventNotOpenError(ConflictError):
    """The event is cancelled/completed and no longer accepts registrations."""

    message = "Sự kiện này hiện không nhận đăng ký."

    def __init__(self) -> None:
        super().__init__(self.message, details={"reason": "event_not_open"})


class NotRegisteredError(ConflictError):
    """The caller has no active registration to cancel."""

    message = "Bạn chưa đăng ký sự kiện này."

    def __init__(self) -> None:
        super().__init__(self.message, details={"reason": "not_registered"})


class EventAlreadyClaimedError(ConflictError):
    """Another moderator already claimed this event for review."""

    message = "Sự kiện này đang được người kiểm duyệt khác xử lý."

    def __init__(self) -> None:
        super().__init__(self.message, details={"reason": "already_claimed"})


class InvalidModerationReasonError(ValidationFailedError):
    """An unrecognized structured reason code, or ``other`` without a note."""

    message = "Vui lòng chọn lý do hợp lệ (hoặc nhập lý do cụ thể cho 'Lý do khác')."

    def __init__(self) -> None:
        super().__init__(self.message, details={"reason": "invalid_reason_code"})
