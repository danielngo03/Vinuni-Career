"""Advertising notifications — outbox email + in-app feed (ADR-0009 §9.7).

Thin helpers that enqueue a deduped outbox row (no synchronous SMTP) and an in-app
feed row in the caller's transaction. Bodies carry only friendly, PII-safe copy:
never a provider/model/token internal, never the spend amount or payment reference
to non-admin recipients (the partner already owns its own placement, so the frozen
price + target title are safe; the bank-transfer reference is admin-only and never
notified).
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.advertising.domain.models import SponsoredPlacement
from app.modules.notifications.application import feed_service
from app.modules.notifications.application.dispatch_service import enqueue_notification
from app.modules.users.application import user_service

# template_key (email) -> in-app notif_type (catalog). Both vi+en seeded.
_FEED_TYPE: dict[str, str] = {
    "advertising.approved": "advertising.approved",
    "advertising.rejected": "advertising.rejected",
    "advertising.payment_recorded": "advertising.payment_recorded",
    "advertising.live": "advertising.live",
    "advertising.ending": "advertising.ending",
}


async def notify_partner(
    session: AsyncSession,
    *,
    placement: SponsoredPlacement,
    template_key: str,
    locale: str = "vi",
    extra: dict | None = None,
) -> None:
    """Enqueue the partner-facing email + in-app feed row for a placement event."""

    recipient_id = placement.created_by
    poster = await user_service.get_by_id(session, recipient_id)
    variables: dict[str, object] = {
        "email": poster.email if poster else "",
        "name": poster.full_name if poster and poster.full_name else "",
    }
    if extra:
        variables.update(extra)
    await enqueue_notification(
        session,
        recipient_id=recipient_id,
        template_key=template_key,
        channel="email",
        locale=locale,
        variables=variables,
        dedupe_key=f"{template_key}:{placement.id}:{placement.version}",
    )
    notif_type = _FEED_TYPE.get(template_key)
    if notif_type is not None:
        await feed_service.create_in_app(
            session,
            recipient_id=recipient_id,
            notif_type=notif_type,
            action_url=f"/partner/advertising/{placement.id}",
            variables={
                "reason": (extra or {}).get("reason", ""),
            },
            locale=locale,
        )


async def notify_partner_by_id(
    session: AsyncSession,
    *,
    placement_id: uuid.UUID,
    placement: SponsoredPlacement,
    template_key: str,
    locale: str = "vi",
    extra: dict | None = None,
) -> None:
    await notify_partner(
        session,
        placement=placement,
        template_key=template_key,
        locale=locale,
        extra=extra,
    )
