"""Partners — domain layer: Company entity and verification state."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class CompanyVerificationStatus(StrEnum):
    UNVERIFIED = "unverified"
    PENDING = "pending"
    VERIFIED = "verified"
    SUSPENDED = "suspended"


@dataclass
class Company:
    """Domain entity for a verified partner company."""

    org_id: str
    name: str
    tax_code: str
    verification_status: CompanyVerificationStatus
    is_active: bool = True

    def can_post_jobs(self) -> bool:
        return (
            self.verification_status == CompanyVerificationStatus.VERIFIED
            and self.is_active
        )
