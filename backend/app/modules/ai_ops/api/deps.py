"""Auth dependencies for the AI ops admin surface.

``require_superadmin`` raises ``PermissionDeniedError`` (403) for any caller
that is not a platform superadmin.  Authorization is decided in the service /
deps layer — not the router — per ``docs/SECURITY_PRIVACY.md``.
"""

from __future__ import annotations

from fastapi import Depends

from app.modules.auth.api.deps import CurrentAuth, get_current_auth
from app.shared.exceptions import PermissionDeniedError
from app.shared.permissions import Principal


async def require_superadmin(
    auth: CurrentAuth = Depends(get_current_auth),
) -> Principal:
    """Return the principal only if the caller is a platform superadmin.

    Raises:
        AuthRequiredError: propagated from ``get_current_auth`` when token is absent/invalid (401).
        PermissionDeniedError: when the caller is authenticated but not a superadmin (403).
    """

    if not auth.principal.is_superadmin:
        raise PermissionDeniedError()
    return auth.principal
