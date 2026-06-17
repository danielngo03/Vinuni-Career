from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


MatchingMode = Literal["strict", "balanced", "intern_friendly"]
MissingRequiredPolicy = Literal["reject", "penalize"]
MatchAudience = Literal["student", "company", "matrix"]
MatchDecision = Literal["shortlist", "review", "low_match", "rejected"]


class MatchingSkillRequirement(BaseModel):
    required_level: float = Field(default=5.0, ge=0, le=10)
    importance: float = Field(default=1.0, ge=0, le=1)
    required: bool = True


class MatchingStudentSkill(BaseModel):
    score: float = Field(default=0.0, ge=0, le=10)
    confidence: float = Field(default=1.0, ge=0, le=1)
    evidence: list[str] = Field(default_factory=list)


class MatchingExperienceRequirement(BaseModel):
    required: bool = False
    min_months: int = Field(default=0, ge=0)
    preferred_titles: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    importance: float = Field(default=0.0, ge=0, le=1)


class MatchingEducationRequirement(BaseModel):
    required: bool = False
    degrees: list[str] = Field(default_factory=list)
    fields_of_study: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    importance: float = Field(default=0.0, ge=0, le=1)


class MatchingWorkExperience(BaseModel):
    title: str = Field(default="", max_length=160)
    company: str = Field(default="", max_length=160)
    duration: str = Field(default="", max_length=120)
    summary: str = Field(default="", max_length=500)
    score: float = Field(default=0.0, ge=0, le=10)
    score_reason: str = Field(default="", max_length=300)


class MatchingEducation(BaseModel):
    degree: str = Field(default="", max_length=180)
    institution: str = Field(default="", max_length=180)
    year: str = Field(default="", max_length=120)
    summary: str = Field(default="", max_length=500)
    score: float = Field(default=0.0, ge=0, le=10)
    score_reason: str = Field(default="", max_length=300)


class MatchingConfig(BaseModel):
    mode: MatchingMode = "balanced"
    skill_weight: float = Field(default=0.65, ge=0, le=1)
    experience_weight: float = Field(default=0.20, ge=0, le=1)
    education_weight: float = Field(default=0.15, ge=0, le=1)
    required_skill_weight: float = Field(default=0.85, ge=0, le=1)
    optional_skill_weight: float = Field(default=0.15, ge=0, le=1)
    missing_required_policy: MissingRequiredPolicy = "penalize"
    missing_required_penalty: float = Field(default=25.0, ge=0, le=100)
    under_level_penalty: float = Field(default=10.0, ge=0, le=100)
    minimum_confidence: float = Field(default=0.65, ge=0, le=1)
    low_confidence_penalty: float = Field(default=6.0, ge=0, le=100)
    evidence_bonus: float = Field(default=3.0, ge=0, le=20)
    cap_skill_ratio: float = Field(default=1.2, ge=1, le=2)
    shortlist_threshold: float = Field(default=85.0, ge=0, le=100)
    review_threshold: float = Field(default=70.0, ge=0, le=100)
    low_match_threshold: float = Field(default=55.0, ge=0, le=100)

    @model_validator(mode="after")
    def normalize_mode_defaults(self) -> MatchingConfig:
        if self.mode == "strict":
            if "skill_weight" not in self.model_fields_set:
                self.skill_weight = 0.80
            if "experience_weight" not in self.model_fields_set:
                self.experience_weight = 0.15
            if "education_weight" not in self.model_fields_set:
                self.education_weight = 0.05
            if "required_skill_weight" not in self.model_fields_set:
                self.required_skill_weight = 0.9
            if "optional_skill_weight" not in self.model_fields_set:
                self.optional_skill_weight = 0.1
            if "missing_required_policy" not in self.model_fields_set:
                self.missing_required_policy = "reject"
            if "minimum_confidence" not in self.model_fields_set:
                self.minimum_confidence = 0.7
        elif self.mode == "intern_friendly":
            if "skill_weight" not in self.model_fields_set:
                self.skill_weight = 0.60
            if "experience_weight" not in self.model_fields_set:
                self.experience_weight = 0.15
            if "education_weight" not in self.model_fields_set:
                self.education_weight = 0.25
            if "required_skill_weight" not in self.model_fields_set:
                self.required_skill_weight = 0.75
            if "optional_skill_weight" not in self.model_fields_set:
                self.optional_skill_weight = 0.25
            if "missing_required_policy" not in self.model_fields_set:
                self.missing_required_policy = "penalize"
            if "missing_required_penalty" not in self.model_fields_set:
                self.missing_required_penalty = 18.0
            if "under_level_penalty" not in self.model_fields_set:
                self.under_level_penalty = 6.0
        return self


class MatchingJobInput(BaseModel):
    job_id: str
    company_id: str | None = None
    title: str
    status: str | None = None
    location: str | None = None
    skills: dict[str, MatchingSkillRequirement]
    experience_requirements: MatchingExperienceRequirement = Field(
        default_factory=MatchingExperienceRequirement
    )
    education_requirements: MatchingEducationRequirement = Field(
        default_factory=MatchingEducationRequirement
    )
    raw_text: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MatchingStudentInput(BaseModel):
    student_id: str
    name: str | None = None
    target_position: str | None = None
    skills: dict[str, MatchingStudentSkill]
    work_experience: list[MatchingWorkExperience] = Field(default_factory=list)
    education: list[MatchingEducation] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SkillMatchBreakdown(BaseModel):
    skill: str
    required: bool
    required_level: float
    student_score: float | None = None
    confidence: float | None = None
    importance: float
    score: float
    status: Literal["matched", "weak", "missing"]
    evidence: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


class MatchBreakdown(BaseModel):
    required_skills: float
    optional_skills: float
    skill_score: float = 0.0
    experience_score: float = 0.0
    education_score: float = 0.0
    component_weights: dict[str, float] = Field(default_factory=dict)
    evidence_bonus: float
    penalties: float
    raw_score: float


class MatchResult(BaseModel):
    student_id: str
    student_name: str | None = None
    job_id: str
    job_title: str
    company_id: str | None = None
    job_status: str | None = None
    job_location: str | None = None
    match_score: float
    label: Literal["Strong match", "Good match", "Partial match", "Weak match", "Rejected"]
    decision: MatchDecision
    breakdown: MatchBreakdown
    required_skills: dict[str, list[str]]
    optional_skills: dict[str, list[str]]
    skill_breakdown: list[SkillMatchBreakdown]
    strengths: list[str]
    gaps: list[str]
    risks: list[str]
    recommendations: list[str]
    explanations: list[str]


class StudentJobMatchRequest(BaseModel):
    student: MatchingStudentInput
    jobs: list[MatchingJobInput] = Field(min_length=1)
    config: MatchingConfig = Field(default_factory=MatchingConfig)


class CompanyCandidateMatchRequest(BaseModel):
    job: MatchingJobInput
    students: list[MatchingStudentInput] = Field(min_length=1)
    config: MatchingConfig = Field(default_factory=MatchingConfig)


class MatchingMatrixRequest(BaseModel):
    jobs: list[MatchingJobInput] = Field(min_length=1)
    students: list[MatchingStudentInput] = Field(min_length=1)
    config: MatchingConfig = Field(default_factory=MatchingConfig)


class MatchListResponse(BaseModel):
    audience: MatchAudience
    config: MatchingConfig
    results: list[MatchResult]
