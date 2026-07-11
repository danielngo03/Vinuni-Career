"""Single source of truth for the *public event visibility* SQL predicate (ADR-0008).

The marketplace overview and the events public-read facade must use the **exact**
same definition of "an event a guest may discover" as
:func:`event_service.list_public_events`, otherwise the public surfaces drift out
of sync. The predicate is factored here so there is only one place to change it.

An event is publicly visible to a principal of ``levels`` when it is:

- not soft-deleted;
- ``published`` status + ``approved`` moderation;
- published (``published_at`` set);
- within an allowed visibility tier for the principal;
- upcoming or in-progress (``ends_at > now`` — past events drop out of discovery).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Select

from app.modules.opportunities.domain import event_lifecycle
from app.modules.opportunities.domain.event_models import Event


def guest_levels() -> frozenset[str]:
    """Visibility tiers an unauthenticated guest may discover (public-tier only)."""

    # Reuses the shared jobs persona->visibility matrix.
    from app.modules.opportunities.domain import lifecycle

    return lifecycle.visible_levels_for("guest", is_authenticated=False)


def apply_visible_filter(stmt: Select, *, levels: frozenset[str], now: datetime) -> Select:
    """Constrain ``stmt`` (selecting from :class:`Event`) to publicly visible rows."""

    return stmt.where(
        Event.deleted_at.is_(None),
        Event.status == event_lifecycle.PUBLISHED,
        Event.moderation_status == event_lifecycle.MOD_APPROVED,
        Event.published_at.isnot(None),
        Event.visibility.in_(levels),
        Event.ends_at > now,
    )
