"""Affiliation facade — the authoritative read/write seam for a student's
institutional affiliation and the verified-student badge.

Owner decision (2026-07-09): the three student personas — VinUni student, alumni,
external student — used to collapse to a single ``identity.persona = 'student'``.
The VinUni-vs-external distinction lived only ephemerally inside billing. This
facade makes affiliation a persisted, surfaced fact on the student profile.

It is the ONLY cross-module entry point: other modules (onboarding verification,
auth ``/me``) call these functions instead of importing the ``student_profiles``
ORM. It owns the ``student_profiles.affiliation`` +
``student_profiles.student_verified_at`` columns and the *provisional* label
derived before a student verifies.

- :func:`set_affiliation` — upsert affiliation (+ optional verified timestamp),
  lazily materializing the profile row exactly like ``profile_service`` does.
- :func:`get_affiliation` — the stored fact + whether the student is verified.
- :func:`resolve_display` — the value to badge in session/profile UI: the stored
  verified affiliation when present, else a provisional (``verified=False``)
  label derived from the login-email institution domain + onboarding seeker type.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import is_institution_email
from app.modules.student_profiles.application import _shared
from app.modules.student_profiles.domain.models import StudentProfile

# Affiliation vocabulary (kept here — this facade owns the column).
AFFILIATION_VINUNI_STUDENT = "vinuni_student"
AFFILIATION_ALUMNI = "alumni"
AFFILIATION_EXTERNAL = "external"
AFFILIATION_GENERAL = "general"

AFFILIATION_VALUES = frozenset(
    {
        AFFILIATION_VINUNI_STUDENT,
        AFFILIATION_ALUMNI,
        AFFILIATION_EXTERNAL,
        AFFILIATION_GENERAL,
    }
)

# Onboarding seeker sub-types used for provisional derivation (kept as literals so
# this facade does not import the onboarding module).
_SEEKER_PROFESSIONAL = "professional"
_SEEKER_EXTERNAL = frozenset({"student", "fresh_graduate"})


async def _load_or_create(
    session: AsyncSession, *, user_id: uuid.UUID
) -> StudentProfile:
    """Load the student's profile, lazily materializing an empty shell if absent.

    Mirrors ``_shared.load_owned_profile`` / ``profile_service`` so a first
    affiliation write persists the profile row without a prior GET.
    """

    profile = await _shared.load_profile_by_user(session, user_id=user_id)
    if profile is None:
        profile = StudentProfile(user_id=user_id)
        session.add(profile)
        await session.flush()
    return profile


async def set_affiliation(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    affiliation: str,
    verified_at: datetime | None = None,
) -> None:
    """Upsert ``affiliation`` (and optionally the verified timestamp) onto the
    student's profile row, creating the row lazily if absent.

    The caller owns the audit record for the surrounding use case; this seam only
    mutates the affiliation columns and flushes. ``verified_at`` is set only when
    provided (a re-derivation must not clear an existing badge).
    """

    if affiliation not in AFFILIATION_VALUES:
        # Internal invariant guard — callers pass a known constant.
        raise ValueError(f"unknown affiliation: {affiliation!r}")

    profile = await _load_or_create(session, user_id=user_id)
    profile.affiliation = affiliation
    if verified_at is not None:
        profile.student_verified_at = verified_at
    await session.flush()


async def get_affiliation(session: AsyncSession, *, user_id: uuid.UUID) -> dict:
    """Return the stored affiliation fact for ``user_id``.

    ``{"affiliation": str, "verified": bool, "verified_at": datetime | None}``.
    Absent profile → the safe ``general`` / unverified default.
    """

    profile = await _shared.load_profile_by_user(session, user_id=user_id)
    if profile is None:
        return {
            "affiliation": AFFILIATION_GENERAL,
            "verified": False,
            "verified_at": None,
        }
    return {
        "affiliation": profile.affiliation or AFFILIATION_GENERAL,
        "verified": profile.student_verified_at is not None,
        "verified_at": profile.student_verified_at,
    }


def _provisional_affiliation(login_email: str | None, seeker_type: str | None) -> str:
    """Derive an unverified provisional label (no persistence)."""

    if is_institution_email(login_email):
        return AFFILIATION_VINUNI_STUDENT
    if seeker_type == _SEEKER_PROFESSIONAL:
        return AFFILIATION_GENERAL
    if seeker_type in _SEEKER_EXTERNAL:
        return AFFILIATION_EXTERNAL
    return AFFILIATION_GENERAL


async def resolve_display(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    login_email: str | None,
    seeker_type: str | None,
) -> dict:
    """Resolve the affiliation to badge in the session / profile UI.

    ``{"affiliation": str, "verified": bool}``. If a stored affiliation exists AND
    the student is verified, it is returned as ``verified=True``. Otherwise a
    provisional label is derived (``verified=False``) from the institution
    login-email domain and onboarding seeker type — giving the otherwise-inert
    ``seeker_type`` a real purpose without over-persisting.
    """

    profile = await _shared.load_profile_by_user(session, user_id=user_id)
    if profile is not None and profile.student_verified_at is not None:
        return {
            "affiliation": profile.affiliation or AFFILIATION_GENERAL,
            "verified": True,
        }
    return {
        "affiliation": _provisional_affiliation(login_email, seeker_type),
        "verified": False,
    }


__all__ = [
    "AFFILIATION_ALUMNI",
    "AFFILIATION_EXTERNAL",
    "AFFILIATION_GENERAL",
    "AFFILIATION_VALUES",
    "AFFILIATION_VINUNI_STUDENT",
    "get_affiliation",
    "resolve_display",
    "set_affiliation",
]
