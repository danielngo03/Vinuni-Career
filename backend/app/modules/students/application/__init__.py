"""Students — application layer (commands + queries)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UpdatePrivacySettingsCommand:
    student_id: str
    blind_hiring: bool
    pii_unmask_requires_consent: bool
    share_gpa: bool
    share_contact: bool


@dataclass(frozen=True)
class GetStudentProfileQuery:
    student_id: str
    viewer_id: str | None = None    # None = self-view (full access)
    consent_granted: bool = False
