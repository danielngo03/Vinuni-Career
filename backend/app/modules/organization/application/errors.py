"""Organization-module application errors.

All map to the shared API error envelope. ``details.reason`` carries a stable,
user-safe machine token (never a raw DB/enum code) for clients that branch on it
(ADR-0002 §7).
"""

from __future__ import annotations

from app.shared.exceptions import (
    ConflictError,
    PermissionDeniedError,
    ValidationFailedError,
)


class PermissionEscalationError(PermissionDeniedError):
    """Actor tried to grant/assign a permission beyond its own ceiling."""

    message = "Bạn không thể cấp quyền vượt quá quyền hạn của chính mình."

    def __init__(self) -> None:
        super().__init__(self.message, details={"reason": "permission_escalation"})


class LastAdminError(ConflictError):
    """Would leave the organization with no active admin."""

    message = "Tổ chức phải luôn còn ít nhất một quản trị viên."

    def __init__(self) -> None:
        super().__init__(self.message, details={"reason": "last_admin"})


class SystemRoleImmutableError(ConflictError):
    """System roles cannot be renamed/deleted or have their ``*:*`` removed."""

    message = "Không thể chỉnh sửa hoặc xoá vai trò hệ thống."

    def __init__(self) -> None:
        super().__init__(self.message, details={"reason": "system_role_immutable"})


class VersionConflictError(ConflictError):
    """Stale optimistic-locking version on a concurrent edit."""

    message = "Nội dung đã được cập nhật ở nơi khác. Vui lòng tải lại trước khi lưu."

    def __init__(self) -> None:
        super().__init__(self.message, details={"reason": "version_conflict"})


class DuplicateRegistrationError(ConflictError):
    """A pending registration / active org already exists for this contact."""

    message = "Đã tồn tại một hồ sơ đăng ký đối tác đang chờ duyệt cho thông tin này."

    def __init__(self) -> None:
        super().__init__(self.message, details={"reason": "duplicate_registration"})


class AlreadyRejectedError(ConflictError):
    """Cannot approve a registration that was already rejected (or vice versa)."""

    message = "Hồ sơ đăng ký này đã được xử lý trước đó."

    def __init__(self, reason: str) -> None:
        super().__init__(self.message, details={"reason": reason})


class DuplicateNameError(ConflictError):
    """A role/department with this name already exists in the org."""

    message = "Tên này đã tồn tại trong tổ chức."

    def __init__(self) -> None:
        super().__init__(self.message, details={"reason": "duplicate_name"})


class InvalidPermissionError(ValidationFailedError):
    """A requested permission tuple is not in the legal catalog vocabulary."""

    message = "Quyền yêu cầu không hợp lệ."

    def __init__(self) -> None:
        super().__init__(self.message, details={"reason": "invalid_permission"})


class InvitationError(ValidationFailedError):
    """Invitation token invalid / expired / already used."""

    def __init__(self, reason: str) -> None:
        super().__init__("Lời mời không hợp lệ hoặc đã hết hạn.", details={"reason": reason})


class NotOwnerError(PermissionDeniedError):
    """Only the org's current designated owner may perform this action."""

    message = "Chỉ chủ sở hữu hiện tại của tổ chức mới có thể thực hiện thao tác này."

    def __init__(self) -> None:
        super().__init__(self.message, details={"reason": "not_owner"})


class ConfirmationRequiredError(ValidationFailedError):
    """A consequential action was requested without explicit confirmation."""

    message = "Thao tác này cần được xác nhận rõ ràng trước khi thực hiện."

    def __init__(self) -> None:
        super().__init__(self.message, details={"reason": "confirmation_required"})


class InvalidMembershipStateError(ConflictError):
    """The membership is not in a state that allows this transition."""

    message = "Trạng thái thành viên hiện tại không cho phép thao tác này."

    def __init__(self, reason: str) -> None:
        super().__init__(self.message, details={"reason": reason})


class NotUniversityActorError(PermissionDeniedError):
    """Only university-role actors may perform this CRM action."""

    message = "Chỉ cán bộ trường đại học mới có thể thực hiện thao tác này."

    def __init__(self) -> None:
        super().__init__(self.message, details={"reason": "not_university_actor"})


class NoProfileChangesError(ValidationFailedError):
    """A profile update carried no recognizable fields or file attachments."""

    message = "Không có thay đổi nào để lưu."

    def __init__(self) -> None:
        super().__init__(self.message, details={"reason": "no_changes"})


class InvalidCompanyDocumentError(ValidationFailedError):
    """An attached company file failed type/size/kind validation."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            "Tệp tài liệu doanh nghiệp không hợp lệ.", details={"reason": reason}
        )


class ChangeRequestNotPendingError(ConflictError):
    """A decision/withdraw was attempted on an already-decided change request."""

    message = "Yêu cầu thay đổi này đã được xử lý trước đó."

    def __init__(self, reason: str = "change_request_not_pending") -> None:
        super().__init__(self.message, details={"reason": reason})


class SeatLimitReachedError(ConflictError):
    """Partner org has reached its seat cap for the current subscription tier."""

    message = (
        "Tổ chức đã đạt giới hạn số lượng thành viên cho gói hiện tại. "
        "Vui lòng nâng cấp gói để thêm thành viên."
    )

    def __init__(self, current: int, limit: int) -> None:
        super().__init__(
            self.message,
            details={"reason": "seat_limit_reached", "current": current, "limit": limit},
        )
