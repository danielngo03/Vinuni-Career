"""ORM -> friendly response shapes for events (ADR-0008).

Two detail views exist:

- :func:`public_event_detail` / :func:`public_event_summary` — what guests and
  non-owners receive. **Never** include moderation notes/status, the creator id,
  or other internal fields.
- :func:`owner_event_detail` / :func:`owner_event_summary` — what the owning org
  (and university moderators) receive: the full record including lifecycle /
  moderation metadata.

Media rule (backend non-negotiable): the API exposes ``cover_image_url`` only,
never the raw ``cover_image_path``. Attendee rows follow the §3 PII rule — email
is included **only** for the organizer projection and never elsewhere.

Every enum column is paired with a localized label via ``domain.event_lifecycle``.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.modules.opportunities.domain import event_lifecycle
from app.modules.opportunities.domain.event_models import Event, EventRegistration
from app.modules.organization.application.org_reporting_facade import (
    OrgSummary,
    company_block,
)
from app.shared.moderation import queue_age_fields, reason_code_label


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def cover_image_url(event: Event) -> str | None:
    """Return a safe cover URL, never a raw storage path.

    V1 has no signed event-media endpoint, so an externally-hosted absolute URL is
    surfaced as-is while any internal storage key resolves to ``None`` (the UI
    falls back to a placeholder). This keeps local paths/object keys from leaking.
    """

    path = event.cover_image_path
    if path and (path.startswith("http://") or path.startswith("https://")):
        return path
    return None


def _venue(event: Event) -> dict | None:
    if event.format == "online":
        return None
    if not event.venue_name and not event.venue_address:
        return None
    return {"name": event.venue_name, "address": event.venue_address}


def _common(event: Event, *, locale: str) -> dict:
    return {
        "id": str(event.id),
        "org_id": str(event.org_id),
        "title": event.title,
        "slug": event.slug,
        "event_type": event.event_type,
        "event_type_label": event_lifecycle.event_type_label(event.event_type, locale=locale),
        "format": event.format,
        "format_label": event_lifecycle.format_label(event.format, locale=locale),
        "cover_image_url": cover_image_url(event),
        "venue": _venue(event),
        "starts_at": _iso(event.starts_at),
        "ends_at": _iso(event.ends_at),
        "timezone": event.timezone,
        "registration_opens_at": _iso(event.registration_opens_at),
        "registration_closes_at": _iso(event.registration_closes_at),
        "capacity": event.capacity,
        "registration_count": event.registration_count,
        "seats_remaining": (
            None if event.capacity is None else max(event.capacity - event.registration_count, 0)
        ),
        "is_featured": event.is_featured,
        "is_sponsored": event.is_sponsored,
        "tags": list(event.tags or []),
        "published_at": _iso(event.published_at),
    }


def _detail_body(event: Event, *, locale: str) -> dict:
    data = _common(event, locale=locale)
    data["description"] = event.description
    return data


def public_event_summary(
    event: Event, *, company: OrgSummary | None = None, locale: str = "vi"
) -> dict:
    data = _common(event, locale=locale)
    data["company"] = company_block(company)
    return data


def public_event_detail(
    event: Event, *, company: OrgSummary | None = None, locale: str = "vi"
) -> dict:
    data = _detail_body(event, locale=locale)
    data["company"] = company_block(company)
    return data


def _owner_fields(event: Event, *, locale: str) -> dict:
    return {
        "created_by": str(event.created_by),
        "visibility": event.visibility,
        "status": event.status,
        "status_label": event_lifecycle.status_label(event.status, locale=locale),
        "moderation_status": event.moderation_status,
        "moderation_status_label": event_lifecycle.moderation_label(
            event.moderation_status, locale=locale
        ),
        "moderation_note": event.moderation_note,
        "moderation_reason_code": event.moderation_reason_code,
        "moderation_reason_label": reason_code_label(event.moderation_reason_code, locale=locale),
        "submitted_at": _iso(event.submitted_at),
        "approved_at": _iso(event.approved_at),
        "cancelled_at": _iso(event.cancelled_at),
        "settings": dict(event.settings or {}),
        "version": event.version,
        "created_at": _iso(event.created_at),
        "updated_at": _iso(event.updated_at),
        "claimed_by": str(event.claimed_by) if event.claimed_by else None,
        "claimed_at": _iso(event.claimed_at),
        **queue_age_fields(
            submitted_at=event.submitted_at,
            due_by=event.due_by,
            now=datetime.now(tz=UTC),
        ),
    }


def owner_event_summary(event: Event, *, locale: str = "vi") -> dict:
    data = _common(event, locale=locale)
    data.update(
        {
            "status": event.status,
            "status_label": event_lifecycle.status_label(event.status, locale=locale),
            "moderation_status": event.moderation_status,
            "moderation_status_label": event_lifecycle.moderation_label(
                event.moderation_status, locale=locale
            ),
            "moderation_reason_code": event.moderation_reason_code,
            "moderation_reason_label": reason_code_label(
                event.moderation_reason_code, locale=locale
            ),
            "visibility": event.visibility,
            "version": event.version,
            "created_at": _iso(event.created_at),
            "claimed_by": str(event.claimed_by) if event.claimed_by else None,
            "claimed_at": _iso(event.claimed_at),
            **queue_age_fields(
                submitted_at=event.submitted_at,
                due_by=event.due_by,
                now=datetime.now(tz=UTC),
            ),
        }
    )
    return data


def owner_event_detail(event: Event, *, locale: str = "vi") -> dict:
    data = _detail_body(event, locale=locale)
    data.update(_owner_fields(event, locale=locale))
    return data


# --------------------------------------------------------------------------- #
# Registration projections                                                    #
# --------------------------------------------------------------------------- #


def my_registration(
    reg: EventRegistration,
    *,
    event: Event,
    waitlist_position: int | None = None,
    locale: str = "vi",
) -> dict:
    """A student's own registration row ("My Events"). No other attendee's PII."""

    return {
        "registration_id": str(reg.id),
        "status": reg.status,
        "status_label": event_lifecycle.registration_state_label(reg.status, locale=locale),
        "waitlist_position": waitlist_position,
        "registered_at": _iso(reg.created_at),
        "checked_in_at": _iso(reg.check_in_at),
        "event": public_event_summary(event, locale=locale),
    }


def attendee_row(
    reg: EventRegistration,
    *,
    display_name: str | None,
    email: str | None,
    include_email: bool,
    locale: str = "vi",
) -> dict:
    """One attendee-list row (organizer/university only).

    Per ADR-0008 §3 the email is included **only** for the owning org's organizer
    projection (``include_email=True``); it is never present otherwise. The raw
    ``user_id`` is intentionally not surfaced.
    """

    row = {
        "registration_id": str(reg.id),
        "display_name": display_name or "—",
        "status": reg.status,
        "status_label": event_lifecycle.registration_state_label(reg.status, locale=locale),
        "registered_at": _iso(reg.created_at),
        "checked_in_at": _iso(reg.check_in_at),
    }
    if include_email:
        row["email"] = email
    return row
