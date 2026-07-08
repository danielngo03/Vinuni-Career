"""ORM -> friendly, leak-safe response shapes for the identity-only student profile.

Owner decision (2026-07-06): the profile is identity-only. It carries name/email
(from the user account), phone/location, privacy gates, an avatar, and the single
``is_open_to_work`` career signal — nothing else. All career content lives in CVs.

Two audiences:

- :func:`owner_profile` — what the owning student sees (raw contact fields).
- :func:`public_profile` — the privacy-gated projection a partner / VinUni viewer
  sees. Contact fields appear ONLY when the relevant per-field gate allows it for
  the caller's context.

Every raw enum code is paired with a localized label (``.claude/rules/backend.md``).
"""

from __future__ import annotations

from app.core.config import get_settings
from app.modules.student_profiles.domain import vocab
from app.modules.student_profiles.domain.models import StudentProfile


def _iso(value) -> str | None:
    return value.isoformat() if value else None


# --------------------------------------------------------------------------- #
# Avatar                                                                       #
# --------------------------------------------------------------------------- #


def _avatar_url(p: StudentProfile) -> str | None:
    if not getattr(p, "avatar_path", None):
        return None
    base = get_settings().app_url.rstrip("/")
    return f"{base}/api/v1/students/{p.id}/avatar?v={p.version}"


# Exported alias for use by other modules (talent pool service etc.)
avatar_url_for = _avatar_url


# --------------------------------------------------------------------------- #
# Profile (owner / public)                                                     #
# --------------------------------------------------------------------------- #


def owner_profile(p: StudentProfile, *, user, locale: str = "vi") -> dict:
    return {
        "id": str(p.id),
        "user_id": str(p.user_id),
        "display_name": (getattr(user, "full_name", None) or "") if user else "",
        "email": (getattr(user, "email", None) or "") if user else "",
        "avatar_url": _avatar_url(p),
        "phone": p.phone,
        "location_city": p.location_city,
        "location_country": p.location_country,
        "profile_visibility": p.profile_visibility,
        "profile_visibility_label": vocab.visibility_label(
            p.profile_visibility, locale=locale
        ),
        "show_email": p.show_email,
        "show_email_label": vocab.contact_label(p.show_email, locale=locale),
        "show_phone": p.show_phone,
        "show_phone_label": vocab.contact_label(p.show_phone, locale=locale),
        "is_open_to_work": p.is_open_to_work,
        "created_at": _iso(p.created_at),
        "updated_at": _iso(p.updated_at),
        "version": p.version,
    }


def public_profile(
    p: StudentProfile,
    *,
    user,
    expose_email: bool,
    expose_phone: bool,
    locale: str = "vi",
) -> dict:
    """Privacy-gated identity projection.

    ``expose_email`` / ``expose_phone`` are decided by the visibility service from
    the per-field gate + caller context; this presenter only renders what it is
    told it may render and never leaks raw contact otherwise.
    """

    body: dict = {
        "id": str(p.id),
        "user_id": str(p.user_id),
        "display_name": (getattr(user, "full_name", None) or "") if user else "",
        "avatar_url": _avatar_url(p),
        "location_city": p.location_city,
        "location_country": p.location_country,
        "is_open_to_work": p.is_open_to_work,
        "profile_visibility": p.profile_visibility,
    }
    if expose_email and user is not None:
        body["email"] = getattr(user, "email", None) or ""
    if expose_phone:
        body["phone"] = p.phone
    return body
