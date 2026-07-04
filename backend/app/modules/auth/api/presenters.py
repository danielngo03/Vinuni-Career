"""Response presenters for auth — safe, client-facing shapes only."""

from __future__ import annotations

from app.modules.auth.application.auth_service import AuthTokens
from app.modules.users.application.user_write_facade import Identity, User


def user_summary(user: User, identity: Identity) -> dict:
    return {
        "id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "preferred_language": user.preferred_language,
        "timezone": user.timezone,
        "email_verified": user.is_email_verified,
        "is_superadmin": user.is_superadmin,
        "active_identity": identity_summary(identity),
    }


def identity_summary(identity: Identity, *, is_active: bool = True) -> dict:
    return {
        "id": str(identity.id),
        "persona": identity.persona,
        "org_id": str(identity.org_id) if identity.org_id else None,
        "is_primary": identity.is_primary,
        "is_active": is_active,
    }


def tokens_payload(tokens: AuthTokens) -> dict:
    """Client-facing token envelope.

    The refresh token is NEVER emitted in the JSON body — it is delivered only as
    an httpOnly cookie by the router (``docs/SECURITY_PRIVACY.md`` §8).
    """

    return {
        "access_token": tokens.access_token,
        "token_type": tokens.token_type,
        "expires_in": tokens.expires_in,
    }
