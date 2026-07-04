"""Application exception hierarchy mapped to the API error envelope.

Every raised :class:`AppError` carries a stable ``code`` from the
``docs/API_CONTRACTS.md`` error-code families and a friendly, user-safe
``message`` (Vietnamese primary). Internal details, stack traces, provider
names, and raw enum codes are never placed in ``message`` or ``details``.
"""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    """Base class for all expected, user-safe application errors."""

    code: str = "INTERNAL_ERROR"
    http_status: int = 500
    message: str = "Đã có lỗi xảy ra. Vui lòng thử lại sau."

    def __init__(
        self,
        message: str | None = None,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message or self.message
        self.details = details or {}
        super().__init__(self.message)


class AuthRequiredError(AppError):
    code = "AUTH_REQUIRED"
    http_status = 401
    message = "Bạn cần đăng nhập để tiếp tục."


class PermissionDeniedError(AppError):
    code = "PERMISSION_DENIED"
    http_status = 403
    message = "Bạn không có quyền thực hiện thao tác này."


class ResourceNotFoundError(AppError):
    code = "RESOURCE_NOT_FOUND"
    http_status = 404
    message = "Không tìm thấy nội dung bạn yêu cầu."


class ValidationFailedError(AppError):
    code = "VALIDATION_FAILED"
    http_status = 422
    message = "Dữ liệu không hợp lệ. Vui lòng kiểm tra lại."


class ConflictError(AppError):
    code = "CONFLICT"
    http_status = 409
    message = "Nội dung đã được cập nhật ở nơi khác. Vui lòng tải lại trước khi lưu."


class RateLimitedError(AppError):
    code = "RATE_LIMITED"
    http_status = 429
    message = "Bạn thao tác quá nhanh. Vui lòng thử lại sau giây lát."


class QuotaExceededError(AppError):
    # 409: an allocation/usage limit is reached (distinct from RATE_LIMITED 429,
    # which is a transient throttle). Matches docs/API_CONTRACTS.md "CV Library And
    # Quota" — over-limit creation returns ``409 QUOTA_EXCEEDED``.
    code = "QUOTA_EXCEEDED"
    http_status = 409
    message = "Bạn đã dùng hết hạn mức cho thao tác này."


class PaymentRequiredError(AppError):
    code = "PAYMENT_REQUIRED"
    http_status = 402
    message = "Thao tác này yêu cầu thanh toán hoặc gói dịch vụ phù hợp."


class AIUnavailableError(AppError):
    code = "AI_UNAVAILABLE"
    http_status = 503
    message = "Tính năng AI tạm thời không khả dụng. Vui lòng thử lại sau."


class InternalError(AppError):
    code = "INTERNAL_ERROR"
    http_status = 500
    message = "Đã có lỗi xảy ra. Vui lòng thử lại sau."
