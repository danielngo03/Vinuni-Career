"""Pydantic request schemas for the career-services counselor workspace API.

HTTP validation only; enum-value/business-rule validation happens in the
application services (so the same friendly error surfaces whether the request
comes through HTTP or an internal caller).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class CohortCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    # Optional owning department (P2/WS2.1). When set, cohort writes are gated by
    # a department-scoped ``career_services_cohorts`` grant for this department.
    department_id: uuid.UUID | None = None


class CohortUpdateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    description: str | None = None
    status: str | None = None


class CohortMemberRequest(BaseModel):
    student_id: uuid.UUID


class AtRiskFlagCreateRequest(BaseModel):
    student_id: uuid.UUID
    reason: str
    severity: str = "medium"
    notes: str | None = None
    cohort_id: uuid.UUID | None = None


class AtRiskFlagStatusRequest(BaseModel):
    status: str
    resolution_notes: str | None = None


class CvReviewCreateRequest(BaseModel):
    student_id: uuid.UUID
    cv_id: uuid.UUID | None = None
    priority: str = "normal"


class CvReviewAssignRequest(BaseModel):
    counselor_id: uuid.UUID


class CvReviewStatusRequest(BaseModel):
    status: str
    feedback: str | None = None


class AppointmentCreateRequest(BaseModel):
    student_id: uuid.UUID
    counselor_id: uuid.UUID
    scheduled_at: datetime
    duration_minutes: int = 30
    mode: str = "in_person"
    location: str | None = None
    notes: str | None = None


class AppointmentStatusRequest(BaseModel):
    status: str
    cancel_reason: str | None = None


class EmployerNoteCreateRequest(BaseModel):
    employer_org_id: uuid.UUID
    category: str = "general"
    visibility: str = "all_staff"
    note_text: str = Field(min_length=1)


class EmployerNoteUpdateRequest(BaseModel):
    note_text: str | None = None
    category: str | None = None
    visibility: str | None = None


class InterventionCreateRequest(BaseModel):
    student_id: uuid.UUID
    intervention_type: str
    description: str = Field(min_length=1)
    linked_appointment_id: uuid.UUID | None = None
    linked_at_risk_flag_id: uuid.UUID | None = None


class InterventionOutcomeRequest(BaseModel):
    outcome: str
