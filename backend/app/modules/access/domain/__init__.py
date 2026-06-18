"""
Access module — domain layer.

Entities and value objects for identity, session, and RBAC.
No ORM, no FastAPI imports.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class PortalType(StrEnum):
    STUDENT = "student"
    PARTNER = "partner"
    UNIVERSITY = "university"
    PENDING = "pending"


@dataclass(frozen=True)
class ActiveIdentity:
    """Value object representing a resolved user + org + role context."""

    identity_id: str          # UserOrgRole.id
    user_id: str
    org_id: str
    org_type: str             # OrgType value
    role_name: str
    portal: PortalType
    permissions: frozenset[str]  # "resource:action"


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str
    access_token_expires_at: datetime
    refresh_token_expires_at: datetime
    token_type: str = "bearer"
