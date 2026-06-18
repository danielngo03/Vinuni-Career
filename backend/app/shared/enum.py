from __future__ import annotations

from enum import Enum, StrEnum


class JobType(StrEnum):
    FULL_TIME = "FULL_TIME"
    PART_TIME = "PART_TIME"
    INTERNSHIP = "INTERNSHIP"
    FREELANCE = "FREELANCE"


class ExperienceLevel(StrEnum):
    INTERN = "INTERN"
    FRESHER = "FRESHER"
    JUNIOR = "JUNIOR"
    MID = "MID"
    SENIOR = "SENIOR"
    LEAD = "LEAD"
    MANAGER = "MANAGER"


class LocationType(StrEnum):
    ONSITE = "ONSITE"
    REMOTE = "REMOTE"
    HYBRID = "HYBRID"


class DegreeLevel(StrEnum):
    BACHELOR = "BACHELOR"
    MASTER = "MASTER"
    PHD = "PHD"
    MD = "MD"
    ASSOCIATE = "ASSOCIATE"
    DIPLOMA = "DIPLOMA"


class EventType(StrEnum):
    CAREER_FAIR = "CAREER_FAIR"
    WORKSHOP = "WORKSHOP"
    SEMINAR = "SEMINAR"
    COMPANY_TOUR = "COMPANY_TOUR"


class EventStatus(StrEnum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    CANCELLED = "CANCELLED"


class EventRegistrationStatus(StrEnum):
    REGISTERED = "REGISTERED"
    ATTENDED = "ATTENDED"
    CANCELLED = "CANCELLED"
    WAITLISTED = "WAITLISTED"


class OrgType(StrEnum):
    UNIVERSITY = "UNIVERSITY"
    PARTNER = "PARTNER"


class StudentStatus(str, Enum):
    STUDYING = "STUDYING"
    GRADUATED = "GRADUATED"
    DROPPED_OUT = "DROPPED_OUT"
    ALUMNI = "ALUMNI"


class NotificationType(str, Enum):
    SYSTEM = "SYSTEM"
    APPLICATION = "APPLICATION"
    EVENT = "EVENT"
    INTERVIEW = "INTERVIEW"


class InterviewType(str, Enum):
    HR_ROUND = "HR_ROUND"
    TECHNICAL_ROUND = "TECHNICAL_ROUND"
    FINAL_ROUND = "FINAL_ROUND"
    OTHER = "OTHER"


class InterviewStatus(str, Enum):
    SCHEDULED = "SCHEDULED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


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
    TECH_INTERVIEW = "TECH_INTERVIEW"
    FINAL_INTERVIEW = "FINAL_INTERVIEW"
    OFFERED = "OFFERED"
    REJECTED = "REJECTED"
    HIRED = "HIRED"
    DECLINED = "DECLINED"


class PlanInterval(StrEnum):
    MONTHLY = "MONTHLY"
    YEARLY = "YEARLY"
    LIFETIME = "LIFETIME"


class ReviewStatus(StrEnum):
    PENDING_MODERATION = "PENDING_MODERATION"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class RegistrationType(StrEnum):
    STUDENT = "STUDENT"
    PARTNER = "PARTNER"


class RegistrationStatus(StrEnum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    VERIFYING = "VERIFYING"
    PENDING = "PENDING"
    UNDER_REVIEW = "UNDER_REVIEW"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"
    NEEDS_CHANGES = "NEEDS_CHANGES"
    RESUBMITTED = "RESUBMITTED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    WITHDRAWN = "WITHDRAWN"


class RegistrationDecision(StrEnum):
    START_REVIEW = "START_REVIEW"
    REQUEST_CHANGES = "REQUEST_CHANGES"
    APPROVE = "APPROVE"
    REJECT = "REJECT"


class VerificationPolicyMode(StrEnum):
    DISABLED = "DISABLED"
    SHADOW = "SHADOW"
    AUTO_LOW_RISK = "AUTO_LOW_RISK"


class VerificationOutcome(StrEnum):
    APPROVE = "APPROVE"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    REQUEST_CHANGES = "REQUEST_CHANGES"
