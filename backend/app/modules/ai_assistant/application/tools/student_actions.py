"""Student confirmation-gated WRITE tool handlers (job alert, event register).

These are the two "safe write" student actions the design spec keeps in the chat
alongside ``save_job`` and ``start_interview_sim`` (frozen contract §9). Each is a
thin wrapper over an existing service that already enforces RBAC and writes its
own audit trail — the tool adds a confirmation card (declared in ``specs.py``) so
the student explicitly confirms before the row is written. The handler runs only
AFTER that confirmation (``native_loop`` gates the confirmation_required class),
so executing the write here is correct. Handlers never raise — always
``{"ok": bool, ...}`` — and never surface a raw error/enum to the end user.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.permissions import Principal

from .student_match import _uuid_or_none


async def set_job_alert(session: AsyncSession, principal: Principal, args: dict) -> dict:
    """Create a saved job-alert subscription for the student (idempotent-safe)."""
    if not principal.is_authenticated:
        return {"ok": False, "error": "auth_required"}
    name = (args.get("name") or "").strip()
    if not name:
        return {"ok": False, "error": "name_required"}

    from app.modules.auth.application.context import RequestContext
    from app.modules.opportunities.application import job_alert_service

    try:
        alert = await job_alert_service.create_alert(
            session,
            principal=principal,
            name=name[:120],
            keywords=(args.get("keywords") or "").strip() or None,
            employment_type=(args.get("employment_type") or "").strip() or None,
            location_type=(args.get("location_type") or "").strip() or None,
            province_code=(args.get("province_code") or "").strip() or None,
            ctx=RequestContext(),
        )
    except Exception as exc:  # noqa: BLE001 - map service errors to user-safe codes
        kind = type(exc).__name__.lower()
        if "quota" in kind or "limit" in kind:
            return {"ok": False, "error": "alert_limit_reached"}
        if "conflict" in kind or "duplicate" in kind:
            return {"ok": False, "error": "alert_exists"}
        if "forbidden" in kind:
            return {"ok": False, "error": "student_only"}
        return {"ok": False, "error": "alert_failed"}

    return {
        "ok": True,
        "created": True,
        "alert_name": alert.get("name") if isinstance(alert, dict) else name,
        "manage_url": "/student/alerts",
    }


async def register_for_event(session: AsyncSession, principal: Principal, args: dict) -> dict:
    """Register the student for an event (confirmed or FIFO-waitlisted)."""
    if not principal.is_authenticated:
        return {"ok": False, "error": "auth_required"}
    event_id = _uuid_or_none(args.get("event_id"))
    if event_id is None:
        return {"ok": False, "error": "invalid_event_id"}

    from app.modules.auth.application.context import RequestContext
    from app.modules.opportunities.application import registration_service

    try:
        reg = await registration_service.register(
            session, principal=principal, event_id=event_id, ctx=RequestContext()
        )
    except Exception as exc:  # noqa: BLE001 - map service errors to user-safe codes
        kind = type(exc).__name__.lower()
        if "notfound" in kind:
            return {"ok": False, "error": "event_not_found"}
        if "forbidden" in kind or "authrequired" in kind:
            return {"ok": False, "error": "not_allowed"}
        if "closed" in kind or "conflict" in kind or "invalid" in kind:
            return {"ok": False, "error": "registration_unavailable"}
        return {"ok": False, "error": "registration_failed"}

    return {
        "ok": True,
        "registered": True,
        # Friendly label (never the raw enum code) when the presenter provides one.
        "status": (
            reg.get("status_label") or reg.get("status") if isinstance(reg, dict) else None
        ),
        "manage_url": "/events",
    }
