"""Partners — application layer (commands + queries)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GetCompanyProfileQuery:
    org_id: str


@dataclass(frozen=True)
class UpdateCompanyProfileCommand:
    org_id: str
    actor_id: str
    company_description: str | None = None
    website: str | None = None
    headquarters_address: str | None = None
