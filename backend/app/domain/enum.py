from __future__ import annotations

from enum import StrEnum


class OrgType(StrEnum):
    UNIVERSITY = "UNIVERSITY"
    COMPANY = "COMPANY"


class JobStatus(StrEnum):
    DRAFT = "DRAFT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CLOSED = "CLOSED"


class ApprovalSource(StrEnum):
    MANUAL_HR = "MANUAL_HR"
    AI_AUTOMATION = "AI_AUTOMATION"


class ApplicationStatus(StrEnum):
    APPLIED = "APPLIED"
    SHORTLISTED = "SHORTLISTED"
    HR_INTERVIEW = "HR_INTERVIEW"
    OFFERED = "OFFERED"
    REJECTED = "REJECTED"
    HIRED = "HIRED"


class PlanInterval(StrEnum):
    MONTHLY = "MONTHLY"
    YEARLY = "YEARLY"
    LIFETIME = "LIFETIME"


class ReviewStatus(StrEnum):
    PENDING_MODERATION = "PENDING_MODERATION"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
