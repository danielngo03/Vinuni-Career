"""Messaging-specific coded errors (ADR-0012 §7).

All extend the shared :class:`AppError` family so they map to the canonical error
envelope. Messages are friendly + bilingual-safe; internal reason tokens travel in
``details`` (never raw stack/limit internals to the user).
"""

from __future__ import annotations

from app.shared.exceptions import AppError, RateLimitedError, ValidationFailedError


class StudentToStudentBlockedError(AppError):
    # 400 per ADR-0012 §7 — a structurally impossible action, not a missing resource.
    code = "STUDENT_TO_STUDENT_BLOCKED"
    http_status = 400
    message = "Không thể nhắn tin trực tiếp giữa sinh viên."


class MessagingNotAllowedError(AppError):
    code = "PERMISSION_DENIED"
    http_status = 403
    message = "Bạn không thể bắt đầu cuộc trò chuyện này."


class ThreadClosedError(AppError):
    code = "THREAD_CLOSED"
    http_status = 409
    message = "Cuộc trò chuyện này đã đóng. Bạn không thể gửi thêm tin nhắn."


class MessageRateLimitedError(RateLimitedError):
    code = "RATE_LIMITED"
    message = "Bạn đã gửi quá nhiều tin nhắn hôm nay. Vui lòng thử lại sau."

    def __init__(self, *, reset_at: str, scope: str) -> None:
        super().__init__(
            self.message,
            details={"reason": "message_rate_limited", "reset_at": reset_at, "scope": scope},
        )


class BlankMessageError(ValidationFailedError):
    message = "Nội dung tin nhắn không được để trống."

    def __init__(self) -> None:
        super().__init__(self.message, details={"field": "body"})


class ContextRequiredError(ValidationFailedError):
    message = "Cần có hồ sơ ứng tuyển để nhắn tin với ứng viên."

    def __init__(self) -> None:
        super().__init__(self.message, details={"field": "context_id"})


class MessageDeleteNotAllowedError(AppError):
    code = "PERMISSION_DENIED"
    http_status = 403
    message = "Bạn không thể xóa tin nhắn này."


class RequestPendingError(AppError):
    # 409 — the message request has hit its intro-message cap and is waiting for the
    # recipient to accept (Messaging V2 gate). Friendly, non-enumerating.
    code = "REQUEST_LIMIT_REACHED"
    http_status = 409
    message = (
        "Bạn đã gửi hết số tin nhắn giới thiệu. Vui lòng chờ bên kia chấp nhận "
        "để tiếp tục trò chuyện."
    )

    def __init__(self, *, reason: str = "request_pending_limit") -> None:
        super().__init__(self.message, details={"reason": reason})


class RequestNotActionableError(AppError):
    # 409 — accept/decline/block on a thread that is not a pending request.
    code = "REQUEST_NOT_PENDING"
    http_status = 409
    message = "Yêu cầu nhắn tin này không còn ở trạng thái chờ duyệt."
