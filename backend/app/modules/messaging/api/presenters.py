"""ORM -> friendly response shapes for messaging.

Presenters carry vi+en labels and the MASKED-or-real identity decided by
``thread_view`` (never raw codes, raw paths, or another user's PII). A soft-deleted
message renders the neutral placeholder; a system message renders a system label,
never a user identity.
"""

from __future__ import annotations

from app.core.config import get_settings
from app.modules.messaging.domain import labels
from app.modules.messaging.domain.models import (
    Message,
    MessageThread,
    MessageThreadParty,
)

_SYSTEM_LABEL = {"vi": "Hệ thống", "en": "System"}

_REQUEST_LABELS = {
    "vi": {
        "accepted": "Đang trò chuyện",
        "pending": "Chờ chấp nhận",
        "declined": "Đã từ chối",
        "blocked": "Đã chặn",
    },
    "en": {
        "accepted": "Open",
        "pending": "Pending request",
        "declined": "Declined",
        "blocked": "Blocked",
    },
}


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def thread_summary(
    thread: MessageThread,
    *,
    counterpart: str,
    unread: int,
    can_reply: bool,
    muted: bool,
    locale: str = "vi",
) -> dict:
    return {
        "id": str(thread.id),
        "kind": thread.kind,
        "kind_label": labels.kind_label(thread.kind, locale=locale),
        "context_type": thread.context_type,
        "context_label": labels.context_label(thread.context_type, locale=locale),
        "subject": thread.subject,
        "counterpart_label": counterpart,
        "status": thread.status,
        "status_label": labels.status_label(thread.status, locale=locale),
        "is_anonymous": thread.is_anonymous,
        "thread_kind": thread.thread_kind or thread.kind,
        "request_state": thread.request_state,
        "request_label": _REQUEST_LABELS.get(
            labels.normalize_locale(locale), _REQUEST_LABELS["vi"]
        ).get(thread.request_state, thread.request_state),
        "request_message_count": thread.request_message_count,
        "request_message_limit": get_settings().messaging_request_message_limit,
        "unread": unread,
        "can_reply": can_reply,
        "muted": muted,
        "last_message_at": _iso(thread.last_message_at),
    }


def assignment_block(party: MessageThreadParty) -> dict:
    """Org-inbox routing fields for a shared-inbox thread row (never raw PII)."""

    return {
        "assignment_state": party.assignment_state,
        "assigned_department_id": (
            str(party.assigned_department_id)
            if party.assigned_department_id
            else None
        ),
        "assigned_user_id": (
            str(party.assigned_user_id) if party.assigned_user_id else None
        ),
    }


def thread_detail(
    thread: MessageThread,
    *,
    counterpart: str,
    participants: list[dict],
    unread: int,
    can_reply: bool,
    muted: bool,
    locale: str = "vi",
) -> dict:
    base = thread_summary(
        thread,
        counterpart=counterpart,
        unread=unread,
        can_reply=can_reply,
        muted=muted,
        locale=locale,
    )
    base["participants"] = participants
    return base


def participant_item(*, label: str, can_reply: bool, role_in_thread: str) -> dict:
    # Identity is the MASKED-or-real label only — never a raw user id / email.
    return {
        "label": label,
        "can_reply": can_reply,
        "role_in_thread": role_in_thread,
    }


def message_item(
    message: Message,
    *,
    sender_label: str,
    is_mine: bool,
    locale: str = "vi",
    attachments: list[dict] | None = None,
) -> dict:
    is_deleted = message.deleted_at is not None
    if is_deleted:
        body = labels.deleted_body(locale=locale)
    else:
        body = message.body
    label = (
        _SYSTEM_LABEL.get(labels.normalize_locale(locale), _SYSTEM_LABEL["vi"])
        if message.is_system
        else sender_label
    )
    return {
        "id": str(message.id),
        "body": body,
        "is_system": message.is_system,
        "is_mine": is_mine,
        "is_deleted": is_deleted,
        "sender_label": label,
        "reply_to_id": str(message.reply_to_id) if message.reply_to_id else None,
        # Attachments are hidden on a soft-deleted message.
        "attachments": [] if is_deleted else (attachments or []),
        "created_at": _iso(message.created_at),
    }
