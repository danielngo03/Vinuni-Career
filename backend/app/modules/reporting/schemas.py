from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MetricItem(BaseModel):
    label: str
    value: str
    delta: str
    icon: str = "activity"
    tone: str = "info"

class DashboardJob(BaseModel):
    id: str
    title: str
    company: str
    location: str | None = None
    salary_range: str | None = None
    status: str
    match_score: float | None = None
    tags: list[str] = Field(default_factory=list)
    reason: str | None = None

class DashboardApplication(BaseModel):
    id: str
    job_id: str
    job_title: str
    company: str
    status: str
    ai_match_score: float | None = None
    consent_to_unmask: bool

class DashboardCV(BaseModel):
    id: str
    is_primary: bool
    masked_preview: str
    skills: list[str] = Field(default_factory=list)

class DashboardIdentity(BaseModel):
    id: str
    org_id: str
    org_name: str
    org_type: str
    role_name: str
    portal: str

class DashboardTrendPoint(BaseModel):
    label: str
    value: float

class DashboardActivity(BaseModel):
    id: str
    title: str
    description: str
    occurred_at: str
    tone: str = "info"

class DashboardEvent(BaseModel):
    id: str
    title: str
    event_type: str
    start_time: str
    location: str | None = None

class StudentDashboard(BaseModel):
    identity: DashboardIdentity
    metrics: list[MetricItem]
    recommended_jobs: list[DashboardJob]
    applications: list[DashboardApplication]
    cvs: list[DashboardCV]
    privacy: dict[str, Any]
    saved_jobs: list[DashboardJob] = Field(default_factory=list)
    skill_gaps: list[str] = Field(default_factory=list)
    events: list[DashboardEvent] = Field(default_factory=list)
    recent_activity: list[DashboardActivity] = Field(default_factory=list)
    application_distribution: list[DashboardTrendPoint] = Field(default_factory=list)

class PartnerCandidate(BaseModel):
    application_id: str
    job_id: str
    job_title: str
    anonymous_label: str
    status: str
    ai_match_score: float | None = None
    masked_preview: str
    consent_to_unmask: bool

class PartnerDashboard(BaseModel):
    identity: DashboardIdentity
    metrics: list[MetricItem]
    jobs: list[DashboardJob]
    candidates: list[PartnerCandidate]
    ai_usage: dict[str, Any]
    application_distribution: list[DashboardTrendPoint] = Field(default_factory=list)
    usage_trend: list[DashboardTrendPoint] = Field(default_factory=list)
    recent_activity: list[DashboardActivity] = Field(default_factory=list)

class UniversityDashboard(BaseModel):
    identity: DashboardIdentity
    metrics: list[MetricItem]
    moderation_queue: list[DashboardJob]
    partners: list[dict[str, Any]]
    ai_usage: dict[str, Any]
    moderation_distribution: list[DashboardTrendPoint] = Field(default_factory=list)
    usage_trend: list[DashboardTrendPoint] = Field(default_factory=list)
    recent_activity: list[DashboardActivity] = Field(default_factory=list)
