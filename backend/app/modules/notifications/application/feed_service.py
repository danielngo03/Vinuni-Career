"""In-app Notification Center: creation facade + recipient-scoped read API.

Two responsibilities, one cohesive module:

1. :func:`create_in_app` — the creation facade product events call (in the
   caller's transaction, alongside the existing email/push outbox enqueue). It
   resolves the recipient's locale, renders friendly bilingual title/body from the
   server-side message catalog, honors the recipient's in-app preference, and
   inserts a recipient-scoped feed row.

2. The read API (:func:`list_feed`, :func:`unread_count`, :func:`mark_read`,
   :func:`mark_all_read`) — strictly recipient-scoped. A user only ever sees/acts
   on its own ``recipient_id`` rows; acting on someone else's row is
   indistinguishable from a missing row (``404``, never ``403``), so notifications
   are not enumerable.

RBAC is enforced here (not in the router). Read-state toggles are low-value and
intentionally NOT audited (mirroring that no other read-state write in the
codebase writes an audit row); every product-event creation is already audited at
its origin service.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notifications.application import message_catalog
from app.modules.notifications.domain.models import Notification
from app.modules.users.application import user_read_facade
from app.shared.exceptions import AuthRequiredError, ResourceNotFoundError
from app.shared.pagination import build_cursor_page, clamp_limit, decode_cursor
from app.shared.permissions import Principal


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _as_aware(dt: datetime) -> datetime:
    """Coerce a possibly-naive timestamp (SQLite reads back naive) to UTC-aware."""

    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


# --------------------------------------------------------------------------- #
# Creation facade                                                             #
# --------------------------------------------------------------------------- #


async def _resolve_locale(
    session: AsyncSession, *, recipient_id: uuid.UUID, locale: str | None
) -> str:
    if locale:
        return message_catalog.normalize_locale(locale)
    pref_lang = await user_read_facade.get_preferred_language(session, recipient_id)
    return message_catalog.normalize_locale(pref_lang)


async def _in_app_allowed(
    session: AsyncSession, *, recipient_id: uuid.UUID, notif_type: str
) -> bool:
    """Honor the recipient's in-app preference for this notif_type's category.

    - Mandatory categories (security/lifecycle/...) can never be muted.
    - A stored preference row with ``in_app_enabled = False`` mutes the category.
    - No stored row => in-app is on by default (spec §5).
    """

    if message_catalog.is_mandatory_type(notif_type):
        return True
    category = message_catalog.category_for(notif_type)
    if category is None:
        return True
    pref = await user_read_facade.get_notification_in_app_preference(
        session, user_id=recipient_id, category=category
    )
    if pref is None:
        return True
    return pref


async def _existing_dedupe(
    session: AsyncSession,
    *,
    recipient_id: uuid.UUID,
    notif_type: str,
    action_url: str | None,
) -> Notification | None:
    """Defensive dedupe on the natural key ``(recipient, type, action_url)``.

    Action URLs for wired events uniquely identify their subject (e.g. a specific
    application or job), so a retried product write does not create a duplicate
    feed row. When ``action_url`` is ``None`` we never dedupe.
    """

    if action_url is None:
        return None
    return (
        await session.execute(
            select(Notification).where(
                Notification.recipient_id == recipient_id,
                Notification.notif_type == notif_type,
                Notification.action_url == action_url,
            )
        )
    ).scalars().first()


async def create_in_app(
    session: AsyncSession,
    *,
    recipient_id: uuid.UUID,
    notif_type: str,
    action_url: str | None = None,
    sender_id: uuid.UUID | None = None,
    variables: dict[str, object] | None = None,
    locale: str | None = None,
) -> Notification | None:
    """Insert one in-app feed row in the caller's transaction (no commit).

    Returns the inserted row, the pre-existing row on dedupe, or ``None`` when the
    recipient has muted the category. Never raises on a muted/duplicate path — it
    is a fire-and-forget side effect of the product write.
    """

    if not await _in_app_allowed(
        session, recipient_id=recipient_id, notif_type=notif_type
    ):
        return None

    existing = await _existing_dedupe(
        session,
        recipient_id=recipient_id,
        notif_type=notif_type,
        action_url=action_url,
    )
    if existing is not None:
        return existing

    resolved_locale = await _resolve_locale(
        session, recipient_id=recipient_id, locale=locale
    )
    title, body = message_catalog.render(
        notif_type, locale=resolved_locale, variables=variables
    )
    row = Notification(
        recipient_id=recipient_id,
        sender_id=sender_id,
        notif_type=notif_type,
        title=title,
        body=body,
        action_url=action_url,
        is_read=False,
        channels=["in_app"],
        delivered_at={"in_app": _now().isoformat()},
    )
    session.add(row)
    await session.flush()
    return row


# --------------------------------------------------------------------------- #
# Read API (recipient-scoped)                                                  #
# --------------------------------------------------------------------------- #


def _require_recipient(principal: Principal) -> uuid.UUID:
    if not principal.is_authenticated or principal.user_id is None:
        raise AuthRequiredError()
    return principal.user_id


def _to_feed_item(row: Notification) -> dict:
    return {
        "id": str(row.id),
        "notif_type": row.notif_type,
        "title": row.title,
        "body": row.body,
        "action_url": row.action_url,
        "is_read": row.is_read,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


async def unread_count(session: AsyncSession, *, principal: Principal) -> int:
    recipient_id = _require_recipient(principal)
    return (
        await session.execute(
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.recipient_id == recipient_id,
                Notification.is_read.is_(False),
            )
        )
    ).scalar_one()


async def list_feed(
    session: AsyncSession,
    *,
    principal: Principal,
    cursor: str | None = None,
    limit: int | None = None,
    unread_only: bool = False,
) -> tuple[list[dict], str | None, int, int]:
    """Return ``(items, next_cursor, limit, unread_count)`` newest-first.

    Strictly scoped to the caller's own rows. ``meta.unread_count`` is the
    caller's TOTAL unread (independent of ``unread_only`` / the current page).
    """

    recipient_id = _require_recipient(principal)
    page_limit = clamp_limit(limit)

    stmt = select(Notification).where(Notification.recipient_id == recipient_id)
    if unread_only:
        stmt = stmt.where(Notification.is_read.is_(False))

    decoded = decode_cursor(cursor)
    if decoded is not None:
        anchor_created = datetime.fromisoformat(decoded["created_at"])
        anchor_id = uuid.UUID(decoded["id"])
        stmt = stmt.where(
            or_(
                Notification.created_at < anchor_created,
                (Notification.created_at == anchor_created)
                & (Notification.id < anchor_id),
            )
        )
    stmt = stmt.order_by(
        Notification.created_at.desc(), Notification.id.desc()
    ).limit(page_limit + 1)

    rows = list((await session.execute(stmt)).scalars().all())
    page = build_cursor_page(
        rows,
        limit=page_limit,
        cursor_builder=lambda n: {
            "created_at": _as_aware(n.created_at).isoformat(),
            "id": str(n.id),
        },
    )
    total_unread = await unread_count(session, principal=principal)
    items = [_to_feed_item(n) for n in page.items]
    return items, page.next_cursor, page.limit, total_unread


async def _load_own(
    session: AsyncSession, *, recipient_id: uuid.UUID, notification_id: uuid.UUID
) -> Notification:
    """Load a row only if it belongs to ``recipient_id`` (else ``404``).

    Recipient scoping is the RBAC boundary: another user's (or a non-existent)
    notification is indistinguishable from missing — never a ``403``.
    """

    row = (
        await session.execute(
            select(Notification).where(
                Notification.id == notification_id,
                Notification.recipient_id == recipient_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise ResourceNotFoundError()
    return row


async def mark_read(
    session: AsyncSession,
    *,
    principal: Principal,
    notification_id: uuid.UUID,
) -> dict:
    """Idempotently mark one of the caller's notifications read."""

    recipient_id = _require_recipient(principal)
    row = await _load_own(
        session, recipient_id=recipient_id, notification_id=notification_id
    )
    if not row.is_read:
        row.is_read = True
        row.read_at = _now()
        await session.flush()
    await session.commit()
    remaining = await unread_count(session, principal=principal)
    return {
        "status": "ok",
        "id": str(row.id),
        "is_read": True,
        "unread_count": remaining,
    }


async def mark_all_read(
    session: AsyncSession, *, principal: Principal
) -> dict:
    """Mark every unread notification of the caller as read; return the count."""

    recipient_id = _require_recipient(principal)
    now = _now()
    result = await session.execute(
        update(Notification)
        .where(
            Notification.recipient_id == recipient_id,
            Notification.is_read.is_(False),
        )
        .values(is_read=True, read_at=now)
    )
    await session.commit()
    updated = int(getattr(result, "rowcount", 0) or 0)
    return {"updated": updated, "unread_count": 0}
