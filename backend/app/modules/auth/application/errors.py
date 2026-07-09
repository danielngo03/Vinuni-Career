"""Auth use-case errors mapped to the API error envelope.

All subclass :class:`AppError` so the global handler emits the standard envelope
with a friendly, user-safe message. Codes stay within the documented families
(``docs/API_CONTRACTS.md``); machine-readable hints go in ``details.reason`` for
the frontend without leaking enumeration signals.
"""

from __future__ import annotations

from app.shared.exceptions import AppError


class InvalidCredentialsError(AppError):
    code = "AUTH_REQUIRED"
    http_status = 401
    message = "Email hoặc mật khẩu không đúng."

    def __init__(self) -> None:
        super().__init__(details={"reason": "invalid_credentials"})


class EmailNotVerifiedError(AppError):
    code = "VALIDATION_FAILED"
    http_status = 403
    message = "Vui lòng xác minh email trước khi đăng nhập."

    def __init__(self) -> None:
        super().__init__(details={"reason": "email_not_verified"})


class EmailAlreadyRegisteredError(AppError):
    code = "CONFLICT"
    http_status = 409
    message = "Email này đã được đăng ký. Vui lòng đăng nhập hoặc dùng quên mật khẩu."

    def __init__(self) -> None:
        super().__init__(details={"reason": "email_already_registered"})


class AccountLockedError(AppError):
    code = "RATE_LIMITED"
    http_status = 429
    message = "Tài khoản tạm thời bị khóa do đăng nhập sai nhiều lần. Vui lòng thử lại sau ít phút."

    def __init__(self, *, retry_after_minutes: int) -> None:
        super().__init__(
            details={
                "reason": "account_locked",
                "retry_after_minutes": retry_after_minutes,
            }
        )


class InvalidTokenError(AppError):
    code = "VALIDATION_FAILED"
    http_status = 400
    message = "Liên kết không hợp lệ hoặc đã hết hạn. Vui lòng yêu cầu lại."

    def __init__(self, reason: str = "invalid_token") -> None:
        super().__init__(details={"reason": reason})


class SessionExpiredError(AppError):
    code = "AUTH_REQUIRED"
    http_status = 401
    message = "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại."

    def __init__(self, reason: str = "session_expired") -> None:
        super().__init__(details={"reason": reason})


class RateLimitedError(AppError):
    """Anti-enumeration-safe throttle error for resend-verification,
    forgot-password, and register-resume.

    Fires identically (same status/shape/timing profile) whether or not the
    presented email maps to a real account, since it is evaluated BEFORE any
    account lookup — a 429 here is not an enumeration leak.
    """

    code = "RATE_LIMITED"
    http_status = 429
    message = "Bạn thao tác quá nhanh. Vui lòng thử lại sau giây lát."

    def __init__(self, *, reason: str, retry_after_seconds: int) -> None:
        super().__init__(details={"reason": reason, "retry_after_seconds": retry_after_seconds})
