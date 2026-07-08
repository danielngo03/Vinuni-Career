"""Shared helpers for events (ADR-0008) service-level tests."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.modules.opportunities.application import event_moderation_service, event_service
from sqlalchemy.ext.asyncio import AsyncSession

from tests.auth_utils import CTX


def _now() -> datetime:
    return datetime.now(tz=UTC)


def event_payload(title: str = "Career Day 2026", **over) -> dict:
    starts = over.pop("starts_at", _now() + timedelta(days=7))
    ends = over.pop("ends_at", starts + timedelta(hours=3))
    base = {
        "title": title,
        "description": "Join us for a day of networking and workshops.",
        "event_type": "career_fair",
        "format": "onsite",
        "cover_image_path": None,
        "venue_name": "VinUni Campus",
        "venue_address": "Gia Lam, Hanoi",
        "starts_at": starts,
        "ends_at": ends,
        "timezone": "Asia/Ho_Chi_Minh",
        "registration_opens_at": None,
        "registration_closes_at": None,
        "capacity": None,
        "visibility": "public",
        "tags": [],
    }
    base.update(over)
    return base


async def publish_event(
    db: AsyncSession, organizer, uni, *, title: str = "Live Event", **over
) -> uuid.UUID:
    """Create -> submit (partner) -> university approve -> published."""

    created = await event_service.create_event(
        db, principal=organizer, payload=event_payload(title, **over), ctx=CTX
    )
    await event_service.submit_event(
        db, principal=organizer, event_id=uuid.UUID(created["id"]), ctx=CTX
    )
    await event_moderation_service.approve_event(
        db, principal=uni, event_id=uuid.UUID(created["id"]), ctx=CTX
    )
    return uuid.UUID(created["id"])
