"""
Access module — application layer.

Commands and queries are pure dataclasses.
Use cases orchestrate repositories and emit domain events.
No FastAPI, no SQLAlchemy, no HTTP.
"""
from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LoginCommand:
    email: str
    password: str
    ip_address: str | None = None
    user_agent: str | None = None


@dataclass(frozen=True)
class RefreshTokenCommand:
    refresh_token: str
    ip_address: str | None = None


@dataclass(frozen=True)
class RevokeSessionCommand:
    session_id: str
    user_id: str


@dataclass(frozen=True)
class SelectIdentityCommand:
    """User selects which org/role they want active for the current session."""

    user_id: str
    identity_id: str  # UserOrgRole.id


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GetUserIdentitiesQuery:
    user_id: str


@dataclass(frozen=True)
class GetActiveIdentityQuery:
    user_id: str
    identity_id: str
