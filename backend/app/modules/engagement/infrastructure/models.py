from __future__ import annotations

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.platform.database.models.base import TimestampMixin, uuid_str
from app.platform.database.models.identity import User
from app.platform.database.session import Base
from app.shared.enum import NotificationType, ReviewStatus


class Notification(Base, TimestampMixin):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    notification_type: Mapped[NotificationType] = mapped_column(Enum(NotificationType), default=NotificationType.SYSTEM)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    action_link: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped[User] = relationship()

class CompanyReview(Base, TimestampMixin):
    __tablename__ = "company_reviews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    student_id: Mapped[str] = mapped_column(ForeignKey("student_profiles.id"), index=True)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    title: Mapped[str] = mapped_column(String(255), default="Company review")
    overall_rating: Mapped[int] = mapped_column(Integer)
    culture_rating: Mapped[int] = mapped_column(Integer, default=0)
    interview_experience_rating: Mapped[int] = mapped_column(Integer, default=0)
    review_content: Mapped[str] = mapped_column(Text)
    is_anonymous: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[ReviewStatus] = mapped_column(
        Enum(ReviewStatus), default=ReviewStatus.PENDING_MODERATION
    )
