"""Message attachments — upload / bind / list / gated download (Messaging V2).

Images and common document types can be attached to a message. Upload validates the
caller may SEND in the thread + a MIME allowlist + a size cap, stores the bytes through
the shared storage seam (never the raw key/path in any response), and returns a pending
attachment. ``send_message`` binds pending attachments to the created message. Download
re-checks thread READ access every time and streams the bytes through a gated endpoint
(`.claude/rules/backend.md`: signed/gated file access, never a storage path).
"""

from __future__ import annotations

import re
import uuid
from urllib.parse import quote

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.auth.application.context import RequestContext
from app.modules.messaging.application import _shared, capability, party_service
from app.modules.messaging.domain import rules
from app.modules.messaging.domain.models import (
    Message,
    MessageAttachment,
    MessageThread,
    MessageThreadParty,
)
from app.shared import storage
from app.shared.audit import write_audit
from app.shared.exceptions import ResourceNotFoundError, ValidationFailedError
from app.shared.permissions import Principal

_IMAGE_MIMES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
_FILE_MIMES = {
    "application/pdf",
    "text/plain",
    "text/csv",
    "application/zip",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}
_ALLOWED = _IMAGE_MIMES | _FILE_MIMES


def _attachment_view(a: MessageAttachment) -> dict:
    return {
        "id": str(a.id),
        "kind": a.kind,
        "file_name": a.file_name,
        "content_type": a.content_type,
        "size_bytes": a.size_bytes,
        "width": a.width,
        "height": a.height,
        # A gated endpoint — NEVER the storage key/path.
        "url": f"/api/v1/messaging/attachments/{a.id}",
    }


async def _send_party(
    session: AsyncSession, *, principal: Principal, thread: MessageThread
) -> MessageThreadParty | None:
    """The party the caller may SEND within, or ``None`` if they cannot."""

    participant = await _shared.get_participant(
        session, thread_id=thread.id, user_id=principal.user_id  # type: ignore[arg-type]
    )
    if participant is not None:
        if participant.party_id is not None:
            party = await party_service.get_party(
                session, party_id=participant.party_id
            )
            if party is not None:
                return party
        user_org_ids = {principal.org_id} if principal.org_id else set()
        return await party_service.party_for_user(
            session, thread_id=thread.id, user_id=principal.user_id, user_org_ids=user_org_ids  # type: ignore[arg-type]
        )
    if principal.org_id is not None:
        user_org_ids = {principal.org_id}
        party = await party_service.party_for_user(
            session, thread_id=thread.id, user_id=principal.user_id, user_org_ids=user_org_ids  # type: ignore[arg-type]
        )
        if (
            party is not None
            and party.party_kind == rules.PARTY_ORG
            and party.org_id is not None
            and capability.can_send_as_org(principal, party.org_id)
            and await capability.member_can_access_org_party(
                session, principal=principal, party=party
            )
        ):
            return party
    return None


async def _can_read_thread(
    session: AsyncSession, *, principal: Principal, thread: MessageThread
) -> bool:
    if await _shared.is_university_moderator(session, principal):
        return True
    participant = await _shared.get_participant(
        session, thread_id=thread.id, user_id=principal.user_id  # type: ignore[arg-type]
    )
    if participant is not None:
        return True
    if principal.org_id is None:
        return False
    org_party = (
        await session.execute(
            select(MessageThreadParty).where(
                MessageThreadParty.thread_id == thread.id,
                MessageThreadParty.party_kind == rules.PARTY_ORG,
                MessageThreadParty.org_id == principal.org_id,
            )
        )
    ).scalar_one_or_none()
    if org_party is None or not capability.can_read_org_inbox(
        principal, principal.org_id
    ):
        return False
    # Department scope is access control here too — a download deep link must not
    # cross a department boundary.
    return await capability.member_can_access_org_party(
        session, principal=principal, party=org_party
    )


async def upload(
    session: AsyncSession,
    *,
    principal: Principal,
    thread_id: uuid.UUID,
    file: UploadFile,
    ctx: RequestContext,
) -> dict:
    if not principal.is_authenticated or principal.user_id is None:
        raise ResourceNotFoundError()
    thread = await _shared.load_thread(session, thread_id=thread_id)
    if await _send_party(session, principal=principal, thread=thread) is None:
        raise ResourceNotFoundError()

    max_bytes = get_settings().messaging_attachment_max_mb * 1024 * 1024
    key, size_bytes, content_type = await storage.save_upload_meta(
        file=file,
        folder="messaging",
        allowed_mime=_ALLOWED,
        max_bytes=max_bytes,
    )
    kind = "image" if content_type in _IMAGE_MIMES else "file"
    attachment = MessageAttachment(
        message_id=None,
        thread_id=thread.id,
        uploader_id=principal.user_id,
        kind=kind,
        file_name=(file.filename or "attachment")[:300],
        content_type=content_type,
        size_bytes=size_bytes,
        storage_key=key,
    )
    session.add(attachment)
    await session.flush()
    await write_audit(
        session,
        action="messaging.attachment.upload",
        resource_type="message_attachment",
        resource_id=attachment.id,
        context=_shared.audit_ctx(principal, ctx),
        after={
            "attachment_id": str(attachment.id),
            "thread_id": str(thread.id),
            "kind": kind,
            "size_bytes": size_bytes,
            "content_type": content_type,
        },
    )
    await session.commit()
    return _attachment_view(attachment)


async def bind_to_message(
    session: AsyncSession,
    *,
    message: Message,
    thread_id: uuid.UUID,
    uploader_id: uuid.UUID,
    attachment_ids: list[uuid.UUID],
) -> bool:
    """Bind pending uploads to ``message`` (same thread + uploader, not already bound).

    Returns True if any attachment was bound. No commit (caller owns the tx).
    """

    if not attachment_ids:
        return False
    rows = list(
        (
            await session.execute(
                select(MessageAttachment).where(
                    MessageAttachment.id.in_(attachment_ids),
                    MessageAttachment.thread_id == thread_id,
                    MessageAttachment.uploader_id == uploader_id,
                    MessageAttachment.message_id.is_(None),
                    MessageAttachment.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return False
    for a in rows:
        a.message_id = message.id
    message.has_attachments = True
    await session.flush()
    return True


async def list_for_messages(
    session: AsyncSession, *, message_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[dict]]:
    if not message_ids:
        return {}
    rows = list(
        (
            await session.execute(
                select(MessageAttachment).where(
                    MessageAttachment.message_id.in_(message_ids),
                    MessageAttachment.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    out: dict[uuid.UUID, list[dict]] = {}
    for a in rows:
        if a.message_id is not None:
            out.setdefault(a.message_id, []).append(_attachment_view(a))
    return out


async def download(
    session: AsyncSession,
    *,
    principal: Principal,
    attachment_id: uuid.UUID,
) -> tuple[bytes, str, str]:
    """Return ``(bytes, content_type, filename)`` if the caller may read the thread."""

    if not principal.is_authenticated or principal.user_id is None:
        raise ResourceNotFoundError()
    attachment = (
        await session.execute(
            select(MessageAttachment).where(
                MessageAttachment.id == attachment_id,
                MessageAttachment.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if attachment is None:
        raise ResourceNotFoundError()
    thread = await _shared.load_thread(session, thread_id=attachment.thread_id)
    if not await _can_read_thread(session, principal=principal, thread=thread):
        raise ResourceNotFoundError()
    if attachment.message_id is None:
        # UNBOUND draft (uploaded, not yet sent) → visible only to its uploader; a
        # teammate must not fetch another member's not-yet-sent attachment by id.
        if attachment.uploader_id != principal.user_id:
            raise ResourceNotFoundError()
    else:
        # A soft-deleted message's attachments are no longer downloadable (the UI
        # hides them; the raw endpoint must not keep streaming the bytes).
        parent = await session.get(Message, attachment.message_id)
        if parent is None or parent.deleted_at is not None:
            raise ResourceNotFoundError()
    try:
        data = storage.load_file(attachment.storage_key)
    except Exception as exc:  # noqa: BLE001
        raise ResourceNotFoundError() from exc
    return data, attachment.content_type, attachment.file_name


def validate_attachment_ids(raw: list) -> list[uuid.UUID]:
    if len(raw) > 10:
        raise ValidationFailedError(details={"field": "attachment_ids"})
    return list(raw)


# Only these render inline (as <img>); everything else is forced to download so a
# mislabeled/crafted file can never execute in the app's origin (XSS defense).
_INLINE_SAFE = {"image/png", "image/jpeg", "image/webp", "image/gif"}


def response_meta(*, content_type: str, filename: str) -> tuple[str, dict[str, str]]:
    """Return ``(safe_media_type, headers)`` for a gated attachment download.

    Neutralizes content-sniffing XSS: ``nosniff`` + a strict CSP sandbox, inline only
    for a safelist of image types (attachment otherwise), and an RFC 6266 filename
    (percent-encoded ``filename*`` + a stripped ASCII fallback — no quote/CR/LF).
    """

    inline = content_type in _INLINE_SAFE
    # Serve non-inline content as an opaque octet-stream so the browser cannot be
    # coerced into interpreting it in-origin even if the declared type were wrong.
    media_type = content_type if inline else "application/octet-stream"
    ascii_name = re.sub(r'[":\\\r\n]', "_", filename)
    ascii_name = ascii_name.encode("ascii", "ignore").decode("ascii") or "attachment"
    star = quote(filename, safe="")
    disposition = "inline" if inline else "attachment"
    headers = {
        "Content-Disposition": (
            f"{disposition}; filename=\"{ascii_name}\"; filename*=UTF-8''{star}"
        ),
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'; sandbox; frame-ancestors 'none'",
        "Cache-Control": "private, no-store",
    }
    return media_type, headers
