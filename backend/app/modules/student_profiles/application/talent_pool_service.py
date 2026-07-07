"""Passive talent pool search for partners and university staff (identity-only).

Owner decision (2026-07-06): the profile is identity-only, so passive talent
search now filters by ``is_open_to_work`` + visibility only. Career filters
(degree/major/headline/summary) are gone — a recruiter who wants career detail
opens the student's CV(s) via the recruitment reveal flow.

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


def _require_partner_or_staff(principal: Principal) -> None:
    """Only active partners and university staff / superadmins may search.

    The canonical partner persona is ``partner_member`` (``auth.domain.personas``);
    a prior version checked for ``"partner"`` which never matched a real partner
    principal, so only staff/superadmin could search. Fixed here to accept
    ``partner_member`` with an org context.
    """
    if principal.is_superadmin or principal.persona == "university_staff":
        return
    if principal.persona == "partner_member" and principal.org_id is not None:
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
    keyword: str | None = None,
    cursor: str | None = None,
    limit: int = 20,
) -> dict:
    """Search students who are open to work, subject to visibility rules.

    Returns a paginated list of anonymised identity summaries. No PII is returned
    here — partners use the recruitment reveal flow to obtain contact details and
    to view the student's CV(s).
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

    # Keyword now matches identity fields only (city/country); career text is gone.
    if keyword:
        safe_kw = keyword.strip()[:100]
        ilike = f"%{safe_kw}%"
        stmt = stmt.where(
            or_(
                StudentProfile.location_city.ilike(ilike),
                StudentProfile.location_country.ilike(ilike),
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

    stmt = stmt.order_by(
        StudentProfile.updated_at.desc(), StudentProfile.id.desc()
    ).limit(limit + 1)

    profiles = list((await session.execute(stmt)).scalars().all())

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
    """Anonymous-safe identity summary card for a talent pool result."""
    return {
        "profile_id": str(profile.id),
        "display_name": full_name or "Student",
        "avatar_url": _profile_avatar_url(profile),
        "location_city": profile.location_city,
        "location_country": profile.location_country,
        "is_open_to_work": profile.is_open_to_work,
        "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
    }
