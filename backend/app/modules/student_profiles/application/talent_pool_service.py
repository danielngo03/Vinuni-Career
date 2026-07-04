"""Passive talent pool search for partners and university staff.

Privacy contracts (``docs/SECURITY_PRIVACY.md`` §8 / BUSINESS_LOGIC.md §talent-pool):

- Only students who have ``is_open_to_work = True`` AND ``profile_visibility``
  allows the caller appear in results. ``public`` profiles appear for any
  authenticated partner; ``vinuni_only`` appear only for VinUni personas.
  ``private`` profiles are never surfaced.
- Contact fields (email / phone) are NEVER exposed in the talent-pool list
  endpoint, regardless of the student's per-field gate — partners must use the
  recruitment reveal flow to access PII.
- Each result returns a ``profile_id`` (not ``user_id``) so recruiters can
  deep-link to the privacy-gated profile detail without leaking internal IDs.
- No raw avatar storage key is returned; only the safe ``avatar_url`` pointer.
- Result ordering: most recently updated ``open_to_work`` profile first (i.e.
  signal freshness).
- Quota (max page size: 20) to limit bulk enumeration risk.
"""

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings as _get_settings
from app.modules.student_profiles.application._shared import VINUNI_PERSONAS
from app.modules.student_profiles.domain import vocab
from app.modules.student_profiles.domain.models import StudentProfile
from app.modules.users.application import user_read_facade
from app.shared.exceptions import PermissionDeniedError
from app.shared.permissions import Principal

MAX_PAGE_SIZE = 20
_ALLOWED_OPEN_TO_WORK_TYPES = {"full_time", "internship", "part_time", "contract"}


def _require_partner_or_staff(principal: Principal) -> None:
    """Only active partners and university staff / superadmins may search."""
    if principal.is_superadmin or principal.persona == "university_staff":
        return
    if principal.persona == "partner" and principal.org_id is not None:
        return
    raise PermissionDeniedError()


def _visibility_filter(principal: Principal):
    """SQLAlchemy ``WHERE`` clause fragment for the caller's visibility context."""
    if principal.is_superadmin or principal.persona == "university_staff":
        # University staff see all non-private open-to-work profiles.
        return StudentProfile.profile_visibility.in_([
            vocab.VISIBILITY_PUBLIC,
            vocab.VISIBILITY_VINUNI_ONLY,
        ])
    if principal.persona in VINUNI_PERSONAS:
        return StudentProfile.profile_visibility.in_([
            vocab.VISIBILITY_PUBLIC,
            vocab.VISIBILITY_VINUNI_ONLY,
        ])
    # External partners: only ``public`` profiles.
    return StudentProfile.profile_visibility == vocab.VISIBILITY_PUBLIC


async def search_talent_pool(
    session: AsyncSession,
    *,
    principal: Principal,
    open_to_work_type: str | None = None,
    degree_level: str | None = None,
    keyword: str | None = None,
    cursor: str | None = None,
    limit: int = 20,
) -> dict:
    """Search students who are open to work, subject to visibility rules.

    Returns a paginated list of anonymised profile summaries. No PII is returned
    here — partners use the recruitment reveal flow to obtain contact details.
    """

    _require_partner_or_staff(principal)
    limit = min(limit, MAX_PAGE_SIZE)

    stmt = (
        select(StudentProfile)
        .where(
            StudentProfile.deleted_at.is_(None),
            StudentProfile.is_open_to_work.is_(True),
            _visibility_filter(principal),
        )
    )

    # open_to_work_type filtering is applied in Python after the query because
    # JSON array containment syntax differs between SQLite (test) and Postgres.
    _filter_work_type = (
        open_to_work_type if open_to_work_type in _ALLOWED_OPEN_TO_WORK_TYPES else None
    )

    if degree_level:
        stmt = stmt.where(StudentProfile.degree_level == degree_level)

    if keyword:
        safe_kw = keyword.strip()[:100]
        ilike = f"%{safe_kw}%"
        stmt = stmt.where(
            or_(
                StudentProfile.headline.ilike(ilike),
                StudentProfile.major.ilike(ilike),
                StudentProfile.summary.ilike(ilike),
            )
        )

    # Cursor: last seen updated_at ISO string.
    if cursor:
        try:
            from datetime import datetime
            cursor_dt = datetime.fromisoformat(cursor)
            stmt = stmt.where(StudentProfile.updated_at < cursor_dt)
        except ValueError:
            pass

    # Fetch more when we'll post-filter in Python; avoids under-returning a page.
    db_limit = (limit * 4 + 1) if _filter_work_type else (limit + 1)
    stmt = stmt.order_by(
        StudentProfile.updated_at.desc(), StudentProfile.id.desc()
    ).limit(db_limit)

    profiles = list((await session.execute(stmt)).scalars().all())

    # Python-side filter for work type (cross-database safe).
    if _filter_work_type:
        profiles = [
            p for p in profiles
            if _filter_work_type in (list(p.open_to_work_types or []))
        ]

    has_more = len(profiles) > limit
    profiles = profiles[:limit]

    names = await user_read_facade.get_full_names(
        session, (p.user_id for p in profiles)
    )
    items = [_talent_card(p, names.get(p.user_id)) for p in profiles]
    next_cursor = profiles[-1].updated_at.isoformat() if has_more and profiles else None

    return {
        "items": items,
        "page": {
            "total": None,
            "limit": limit,
            "next_cursor": next_cursor,
        },
    }


def _profile_avatar_url(profile: StudentProfile) -> str | None:
    if not getattr(profile, "avatar_path", None):
        return None
    base = _get_settings().app_url.rstrip("/")
    return f"{base}/api/v1/students/{profile.id}/avatar?v={profile.version}"


def _talent_card(profile: StudentProfile, full_name: str | None) -> dict:
    """Anonymous-safe summary card for a talent pool result."""
    return {
        "profile_id": str(profile.id),
        "display_name": full_name or "Student",
        "avatar_url": _profile_avatar_url(profile),
        "headline": profile.headline,
        "major": profile.major,
        "degree_level": profile.degree_level,
        "degree_level_label": vocab.degree_label(profile.degree_level),
        "graduation_year": profile.graduation_year,
        "location_city": profile.location_city,
        "location_country": profile.location_country,
        "open_to_work_types": list(profile.open_to_work_types or []),
        "open_to_work_type_labels": [
            lbl for t in (profile.open_to_work_types or [])
            if (lbl := vocab.open_to_work_label(t))
        ],
        "profile_completion": profile.profile_completion,
        "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
    }
