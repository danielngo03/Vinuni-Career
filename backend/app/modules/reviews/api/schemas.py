"""Request schemas for the reviews API (Pydantic v2)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ReviewRatingsIn(BaseModel):
    overall: int = Field(ge=1, le=5)
    work_life_balance: int = Field(ge=1, le=5)
    culture_values: int = Field(ge=1, le=5)
    compensation: int = Field(ge=1, le=5)
    career_growth: int = Field(ge=1, le=5)
    interview_experience: int | None = Field(default=None, ge=1, le=5)


class ReviewWriteRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=5000)
    pros: str | None = Field(default=None, max_length=5000)
    cons: str | None = Field(default=None, max_length=5000)
    is_anonymous: bool = False
    ratings: ReviewRatingsIn
    version: int | None = None  # optimistic lock (edit only)

    def to_payload(self) -> dict:
        return {
            "title": self.title,
            "body": self.body,
            "pros": self.pros,
            "cons": self.cons,
            "is_anonymous": self.is_anonymous,
            **self.ratings.model_dump(),
        }


class ReviewReportRequest(BaseModel):
    reason_code: str = Field(max_length=30)
    note: str | None = Field(default=None, max_length=2000)


class ReviewRemoveRequest(BaseModel):
    reason: str = Field(max_length=30)
    note: str | None = Field(default=None, max_length=2000)


class PartnerResponseRequest(BaseModel):
    response: str = Field(min_length=10, max_length=2000)
