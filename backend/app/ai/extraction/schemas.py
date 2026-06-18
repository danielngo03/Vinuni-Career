from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SkillEvidence(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    evidence: str = Field(default="", max_length=500)
    proficiency: Literal["beginner", "intermediate", "advanced", "expert", "unknown"] = "unknown"


class EducationItem(BaseModel):
    institution: str = Field(default="", max_length=200)
    degree: str = Field(default="", max_length=200)
    major: str = Field(default="", max_length=200)
    start_year: int | None = Field(default=None, ge=1900, le=2100)
    end_year: int | None = Field(default=None, ge=1900, le=2100)


class ExperienceItem(BaseModel):
    company: str = Field(default="", max_length=200)
    title: str = Field(default="", max_length=200)
    summary: str = Field(default="", max_length=1500)
    start_date: str | None = Field(default=None, max_length=32)
    end_date: str | None = Field(default=None, max_length=32)


class ProjectItem(BaseModel):
    name: str = Field(default="", max_length=200)
    description: str = Field(default="", max_length=1500)
    technologies: list[str] = Field(default_factory=list, max_length=30)


class CVExtraction(BaseModel):
    document_type: Literal["cv"] = "cv"
    summary: str = Field(default="", max_length=1500)
    skills: list[SkillEvidence] = Field(default_factory=list, max_length=80)
    education: list[EducationItem] = Field(default_factory=list, max_length=20)
    experiences: list[ExperienceItem] = Field(default_factory=list, max_length=30)
    projects: list[ProjectItem] = Field(default_factory=list, max_length=40)
    languages: list[str] = Field(default_factory=list, max_length=20)
    certifications: list[str] = Field(default_factory=list, max_length=30)
    raw_text_quality: Literal[
        "native_text",
        "ocr_needed",
        "vision_extracted",
        "unknown",
    ] = "unknown"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class JDExtraction(BaseModel):
    document_type: Literal["job_description"] = "job_description"
    title: str = Field(default="", max_length=200)
    required_skills: list[SkillEvidence] = Field(default_factory=list, max_length=80)
    nice_to_have_skills: list[SkillEvidence] = Field(default_factory=list, max_length=80)
    responsibilities: list[str] = Field(default_factory=list, max_length=60)
    seniority: Literal["intern", "junior", "mid", "senior", "lead", "unknown"] = "unknown"
    employment_type: str = Field(default="", max_length=80)
    compliance_flags: list[str] = Field(default_factory=list, max_length=40)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
