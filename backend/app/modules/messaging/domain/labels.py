"""Localized (vi + en) labels for messaging vocabularies + masked-identity copy.

Raw enum codes never reach end users (CLAUDE.md / SECURITY_PRIVACY): every
``kind``/``context_type``/``status`` is paired with a friendly bilingual label, the
soft-deleted body renders a neutral placeholder, and the anonymous applicant handle
is a stable, PII-free token.
"""

from __future__ import annotations

from app.modules.messaging.domain import rules

DEFAULT_LOCALE = "vi"
_SUPPORTED = frozenset({"vi", "en"})

_KIND_LABELS: dict[str, dict[str, str]] = {
    "vi": {rules.KIND_DIRECT: "Trực tiếp", rules.KIND_ANNOUNCEMENT: "Thông báo"},
    "en": {rules.KIND_DIRECT: "Direct", rules.KIND_ANNOUNCEMENT: "Announcement"},
}

_CONTEXT_LABELS: dict[str, dict[str, str]] = {
    "vi": {
        rules.CONTEXT_APPLICATION: "Hồ sơ ứng tuyển",
        rules.CONTEXT_SUPPORT: "Hỗ trợ",
        rules.CONTEXT_TEAM: "Nội bộ",
    },
    "en": {
        rules.CONTEXT_APPLICATION: "Application",
        rules.CONTEXT_SUPPORT: "Support",
        rules.CONTEXT_TEAM: "Team",
    },
}

_STATUS_LABELS: dict[str, dict[str, str]] = {
    "vi": {
        rules.STATUS_ACTIVE: "Đang hoạt động",
        rules.STATUS_ARCHIVED: "Đã lưu trữ",
        rules.STATUS_CLOSED: "Đã đóng",
    },
    "en": {
        rules.STATUS_ACTIVE: "Active",
        rules.STATUS_ARCHIVED: "Archived",
        rules.STATUS_CLOSED: "Closed",
    },
}

_DELETED_BODY: dict[str, str] = {
    "vi": "Tin nhắn đã bị xóa",
    "en": "This message was deleted",
}

_ANON_PREFIX: dict[str, str] = {
    "vi": "Ứng viên ẩn danh",
    "en": "Anonymous candidate",
}


def normalize_locale(locale: str | None) -> str:
    return locale if locale in _SUPPORTED else DEFAULT_LOCALE


def _label(table: dict[str, dict[str, str]], code: str, locale: str) -> str:
    loc = normalize_locale(locale)
    return table.get(loc, table[DEFAULT_LOCALE]).get(code, code)


def kind_label(code: str, *, locale: str = "vi") -> str:
    return _label(_KIND_LABELS, code, locale)


def context_label(code: str | None, *, locale: str = "vi") -> str | None:
    if code is None:
        return None
    return _label(_CONTEXT_LABELS, code, locale)


def status_label(code: str, *, locale: str = "vi") -> str:
    return _label(_STATUS_LABELS, code, locale)


def deleted_body(*, locale: str = "vi") -> str:
    return _DELETED_BODY.get(normalize_locale(locale), _DELETED_BODY[DEFAULT_LOCALE])


def anonymous_handle(*, short_code: str, locale: str = "vi") -> str:
    """A stable PII-free handle for a masked applicant, e.g. ``Ứng viên ẩn danh #1A2B3C``."""

    prefix = _ANON_PREFIX.get(normalize_locale(locale), _ANON_PREFIX[DEFAULT_LOCALE])
    return f"{prefix} #{short_code}"
