from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.shared.enum import NotificationType


class NotificationCreate(BaseModel):
    user_id: str
    title: str = Field(max_length=255)
    content: str
    notification_type: NotificationType = NotificationType.SYSTEM
    action_link: str | None = None

class NotificationView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    title: str
    content: str
    notification_type: NotificationType
    is_read: bool
    action_link: str | None

class CompanyReviewCreate(BaseModel):
    org_id: str
    title: str = Field(min_length=3, max_length=255)
    overall_rating: int | None = Field(default=None, ge=1, le=5)
    culture_rating: int | None = Field(default=None, ge=1, le=5)
    interview_experience_rating: int | None = Field(default=None, ge=1, le=5)
    review_content: str | None = Field(default=None, min_length=10)
    rating: int | None = Field(default=None, ge=1, le=5)
    content: str | None = Field(default=None, min_length=10)
    is_anonymous: bool = False

    @model_validator(mode="after")
    def normalize_legacy_fields(self) -> CompanyReviewCreate:
        if self.overall_rating is None and self.rating is not None:
            self.overall_rating = self.rating
        if self.culture_rating is None:
            self.culture_rating = self.overall_rating
        if self.interview_experience_rating is None:
            self.interview_experience_rating = self.overall_rating
        if self.review_content is None and self.content is not None:
            self.review_content = self.content
        if self.overall_rating is None:
            raise ValueError("overall_rating is required")
        if self.review_content is None:
            raise ValueError("review_content is required")
        return self

class CompanyReviewView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    student_id: str
    org_id: str
    title: str
    overall_rating: int
    culture_rating: int
    interview_experience_rating: int
    review_content: str
    is_anonymous: bool
