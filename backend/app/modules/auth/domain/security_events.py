"""Security-event types and friendly bilingual labels.

End users never see raw enum codes (``docs/API_CONTRACTS.md``); the account
security screen renders ``label_vi`` / ``label_en`` resolved here.
"""

from __future__ import annotations

LOGIN_SUCCESS = "login_success"
LOGIN_FAILED = "login_failed"
LOGOUT = "logout"
PASSWORD_CHANGED = "password_changed"
PASSWORD_RESET = "password_reset"
SESSION_REVOKED = "session_revoked"
TOTP_ENABLED = "totp_enabled"
TOTP_DISABLED = "totp_disabled"
TOTP_CHALLENGE = "totp_challenge"
EMAIL_VERIFIED = "email_verified"
TOKEN_REUSE_DETECTED = "token_reuse_detected"

_LABELS: dict[str, tuple[str, str]] = {
    LOGIN_SUCCESS: ("Đăng nhập thành công", "Signed in"),
    LOGIN_FAILED: ("Đăng nhập thất bại", "Failed sign-in attempt"),
    LOGOUT: ("Đăng xuất", "Signed out"),
    PASSWORD_CHANGED: ("Đổi mật khẩu", "Password changed"),
    PASSWORD_RESET: ("Đặt lại mật khẩu", "Password reset"),
    SESSION_REVOKED: ("Đăng xuất thiết bị từ xa", "Device signed out remotely"),
    TOTP_ENABLED: ("Bật xác thực hai lớp", "Two-factor authentication enabled"),
    TOTP_DISABLED: ("Tắt xác thực hai lớp", "Two-factor authentication disabled"),
    TOTP_CHALLENGE: (
        "Yêu cầu xác thực hai lớp",
        "Two-factor verification requested",
    ),
    EMAIL_VERIFIED: ("Xác minh email", "Email verified"),
    TOKEN_REUSE_DETECTED: (
        "Phát hiện phiên đăng nhập bất thường",
        "Suspicious session activity detected",
    ),
}


def label_for(event_type: str, *, locale: str = "vi") -> str:
    vi, en = _LABELS.get(event_type, (event_type, event_type))
    return vi if locale == "vi" else en
