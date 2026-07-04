"""Billing notifications — outbox email + in-app feed (ADR-0010 §8).

Thin helpers that enqueue a deduped outbox row (no synchronous SMTP) and an in-app
feed row in the caller's transaction. Bodies carry only friendly, PII-safe copy:
**never** the frozen price, the revenue roll-up, or the bank-transfer
``payment_reference`` — those are admin-only spend oversight and are never
notified. The owner already owns its own subscription, so a generic "active /
expiring / expired / cancelled" copy is safe.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.billing.domain.models import Subscription
from app.modules.notifications.application import feed_service
from app.modules.notifications.application.dispatch_service import enqueue_notification
from app.modules.users.application import user_service

# template_key (email) == in-app notif_type (catalog). Both vi+en seeded.
_TEMPLATE_KEYS: frozenset[str] = frozenset(
    {
        "billing.payment_recorded",
        "billing.active",
        "billing.expiring",
        "billing.expired",
        "billing.cancelled",
    }
)


async def notify_owner(
    session: AsyncSession,
    *,
    subscription: Subscription,
    template_key: str,
    locale: str = "vi",
) -> None:
    """Enqueue the owner-facing email + in-app feed row for a subscription event.

    The recipient is the requester (the student, or the partner Admin who
    requested for the org). No spend/price/reference variables are ever passed.
    """

    recipient_id = subscription.requested_by
    owner = await user_service.get_by_id(session, recipient_id)
    variables: dict[str, object] = {
        "email": owner.email if owner else "",
        "name": owner.full_name if owner and owner.full_name else "",
    }
    await enqueue_notification(
        session,
        recipient_id=recipient_id,
        template_key=template_key,
        channel="email",
        locale=locale,
        variables=variables,
        dedupe_key=f"{template_key}:{subscription.id}:{subscription.version}",
    )
    if template_key in _TEMPLATE_KEYS:
        await feed_service.create_in_app(
            session,
            recipient_id=recipient_id,
            notif_type=template_key,
            action_url=f"/billing/subscription/{subscription.id}",
            variables={},
            locale=locale,
        )
