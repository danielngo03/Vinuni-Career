"""Use-cases for platform appearance settings."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.platform_settings.infrastructure.repository import get_or_create_platform
from app.shared.exceptions import PermissionDeniedError, ValidationFailedError
from app.shared.permissions import Principal

# Self-hosted font catalogue — keys match frontend globals.css @font-face declarations.
# All fonts support Vietnamese, Latin, and Latin-Extended subsets.
FONT_CATALOGUE: dict[str, str] = {
    "plus_jakarta_sans": "Plus Jakarta Sans",
    "inter": "Inter",
    "be_vietnam_pro": "Be Vietnam Pro",
    "manrope": "Manrope",
    "nunito": "Nunito",
    "lexend": "Lexend",
}

DEFAULT_FONT_KEY = "plus_jakarta_sans"


def _check_admin(principal: Principal) -> None:
    """Gate platform appearance-settings writes.

    V1 scope: superadmin-only. The previous check compared
    ``principal.persona`` against the string ``"university_admin"``, which is
    never actually assigned anywhere in the system — the real bootstrap
    persona for university staff is ``UNIVERSITY_STAFF = "university_staff"``
    (see ``app.modules.auth.domain.personas``). That means the check has
    always silently rejected every real university-staff principal and only
    ever passed for ``is_superadmin=True``.

    Whether university-staff org-admins (not just platform superadmin) SHOULD
    be allowed to manage platform-wide appearance settings is not addressed
    by docs/SECURITY_PRIVACY.md or docs/BUSINESS_LOGIC.md — both are silent on
    this capability. Pending an explicit product/architecture decision, this
    stays superadmin-only rather than widening the permission boundary as a
    side effect of a bug fix.
    """
    if not principal.is_authenticated:
        raise PermissionDeniedError("Authentication required.")
    if not principal.is_superadmin:
        raise PermissionDeniedError("Superadmin required.")


def _to_response(row) -> dict:
    # PlatformSettings (domain/models.py) has no ``font_key`` column — only
    # ``google_font_url`` / ``google_font_family``. The self-hosted font
    # catalogue is keyed by ``font_key`` (see FONT_CATALOGUE above), so the
    # active key is derived by reverse-looking-up the stored family name
    # against the catalogue rather than reading a nonexistent attribute.
    active_key = DEFAULT_FONT_KEY
    if row.google_font_family:
        for key, family in FONT_CATALOGUE.items():
            if family == row.google_font_family:
                active_key = key
                break
    return {
        "font_key": active_key,
        "font_family": FONT_CATALOGUE[active_key],
        "catalogue": [{"key": k, "family": v} for k, v in FONT_CATALOGUE.items()],
    }


async def get_settings(session: AsyncSession) -> dict:
    row = await get_or_create_platform(session)
    return _to_response(row)


async def update_settings(
    session: AsyncSession,
    *,
    principal: Principal,
    font_key: str | None,
    actor_id: uuid.UUID | None = None,
) -> dict:
    _check_admin(principal)

    if font_key is not None and font_key not in FONT_CATALOGUE:
        raise ValidationFailedError(f"font_key must be one of: {', '.join(FONT_CATALOGUE)}")

    row = await get_or_create_platform(session)
    # None = reset to default.
    row.google_font_family = FONT_CATALOGUE[font_key] if font_key else None
    if actor_id is not None:
        row.updated_by = actor_id

    await session.flush()
    return _to_response(row)
