"""
Students — domain layer.

Entities, value objects and privacy policies.
No ORM, no HTTP.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class PrivacyLevel(StrEnum):
    PUBLIC = "public"
    BLIND = "blind"          # PII hidden from partners by default
    EXPLICIT_CONSENT = "explicit_consent"  # Partner must request and student approves


@dataclass
class PrivacySettings:
    blind_hiring: bool = True
    pii_unmask_requires_consent: bool = True
    share_gpa: bool = False
    share_contact: bool = False

    def can_partner_view_pii(self, consent_granted: bool = False) -> bool:
        if not self.pii_unmask_requires_consent:
            return True
        return consent_granted

    def effective_level(self) -> PrivacyLevel:
        if self.pii_unmask_requires_consent:
            return PrivacyLevel.EXPLICIT_CONSENT
        if self.blind_hiring:
            return PrivacyLevel.BLIND
        return PrivacyLevel.PUBLIC


@dataclass
class AcademicProfile:
    """Read-only domain view of a student's academic record."""

    student_id: str
    student_code: str
    major_id: str | None
    degree_level: str | None
    enrollment_year: int | None
    graduation_year: int | None
    gpa: float | None
    privacy: PrivacySettings = field(default_factory=PrivacySettings)
