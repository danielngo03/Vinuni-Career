"""Student-specific AI tool handlers (applications, profile, interviews)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.permissions import Principal


async def get_my_applications(session: AsyncSession, principal: Principal) -> dict:
    from app.modules.recruitment.application import apply_service

    items, _next, _limit = await apply_service.list_my_applications(
        session, principal=principal, cursor=None, limit=5
    )
    return {
        "ok": True,
        "applications": [
            {
                "id": str(a.get("id", "")),
                "job_title": a.get("job_title") or "Unknown Job",
                "company_name": a.get("company_name") or "",
                "status": a.get("status", "submitted"),
                "applied_at": a.get("applied_at", ""),
                "url": f"/student/applications/{a.get('id', '')}",
            }
            for a in items[:5]
        ],
    }


async def get_profile_status(session: AsyncSession, principal: Principal) -> dict:
    from app.modules.student_profiles.application import profile_service

    profile = await profile_service.get_my_profile(session, principal=principal)
    pct = int(profile.get("profile_completion") or 0)
    missing = []
    if not profile.get("headline"):
        missing.append("headline")
    if not profile.get("summary"):
        missing.append("summary")
    if not profile.get("education"):
        missing.append("education")
    if not profile.get("experience"):
        missing.append("experience")
    if not profile.get("skills"):
        missing.append("skills")
    if not profile.get("major") or not profile.get("degree_level"):
        missing.append("academic details (major, degree)")
    if not profile.get("links"):
        missing.append("portfolio or social links")
    return {
        "ok": True,
        "completion_pct": pct,
        "is_open_to_work": profile.get("is_open_to_work", False),
        "open_to_work_types": profile.get("open_to_work_type_labels") or [],
        "missing_sections": missing,
        "profile_url": "/student/profile",
    }


async def get_upcoming_interviews(session: AsyncSession, principal: Principal) -> dict:
    from app.modules.recruitment.application import dashboard_read

    if not principal.is_authenticated:
        return {"ok": False, "error": "auth_required"}
    assert principal.user_id is not None

    try:
        interviews = await dashboard_read.list_upcoming_student_interviews(
            session, user_id=principal.user_id, limit=5
        )
    except Exception:
        return {"ok": False, "error": "tool_failed"}
    return {
        "ok": True,
        "interviews": [
            {
                "job_title": iv.get("job_title", ""),
                "company_name": iv.get("company_name", ""),
                "mode": iv.get("mode", ""),
                "scheduled_at": iv.get("scheduled_at", ""),
                "location": iv.get("location") or None,
                "application_url": f"/student/applications/{iv.get('application_id', '')}",
            }
            for iv in interviews
        ],
    }
