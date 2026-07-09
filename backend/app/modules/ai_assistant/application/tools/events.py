"""Event-related AI tool handlers."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.permissions import Principal


async def get_upcoming_events(session: AsyncSession, principal: Principal, args: dict) -> dict:
    from app.modules.opportunities.application import event_service

    event_type = args.get("event_type") or None
    items, _next, _limit, _total = await event_service.list_public_events(
        session, principal=principal, cursor=None, limit=4, event_type=event_type
    )
    return {
        "ok": True,
        "events": [
            {
                "id": str(e.get("id", "")),
                "title": e.get("title", ""),
                "event_type": e.get("event_type_label") or e.get("event_type", ""),
                "format": e.get("format_label") or e.get("format", ""),
                "starts_at": e.get("starts_at", ""),
                "url": f"/events/{e.get('id', '')}",
            }
            for e in items[:4]
        ],
    }


async def get_my_registered_events(session: AsyncSession, principal: Principal) -> dict:
    from app.modules.opportunities.application import registration_service

    rows = await registration_service.my_registrations(session, principal=principal)
    return {
        "ok": True,
        "registered_events": [
            {
                "title": (r.get("event") or {}).get("title", ""),
                "event_type": (r.get("event") or {}).get("event_type_label", ""),
                "format": (r.get("event") or {}).get("format_label", ""),
                "starts_at": (r.get("event") or {}).get("starts_at", ""),
                "venue_name": (r.get("event") or {}).get("venue_name", ""),
                "status": r.get("status_label") or r.get("status", ""),
                "waitlist_position": r.get("waitlist_position"),
                "url": f"/events/{(r.get('event') or {}).get('id', '')}",
            }
            for r in rows[:5]
        ],
    }


async def search_events(session: AsyncSession, principal: Principal, args: dict) -> dict:
    from app.modules.opportunities.application import event_service

    q = args.get("q") or None
    event_type = args.get("event_type") or None
    items, _next, _limit, _total = await event_service.list_public_events(
        session, principal=principal, cursor=None, limit=5, q=q, event_type=event_type
    )
    return {
        "ok": True,
        "events": [
            {
                "id": str(e.get("id", "")),
                "title": e.get("title", ""),
                "event_type": e.get("event_type_label") or e.get("event_type", ""),
                "format": e.get("format_label") or e.get("format", ""),
                "starts_at": e.get("starts_at", ""),
                "venue_name": e.get("venue_name", ""),
                "capacity": e.get("capacity"),
                "spots_left": (
                    (e.get("capacity") or 0) - (e.get("registration_count") or 0)
                    if e.get("capacity")
                    else None
                ),
                "url": f"/events/{e.get('id', '')}",
            }
            for e in items[:5]
        ],
        "total": _total,
    }
