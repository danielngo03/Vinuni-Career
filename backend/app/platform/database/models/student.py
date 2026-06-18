from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.platform.database.models.base import SoftDeleteMixin, TimestampMixin, uuid_str
from app.platform.database.session import Base
from app.shared.enum import DegreeLevel, StudentStatus


class UniversityMajor(Base):
    __tablename__ = "university_majors"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    major_code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    major_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class SkillDictionary(Base):
    __tablename__ = "sys_skills_dictionary"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    synonyms: Mapped[list] = mapped_column(JSON, default=list)


class File(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    uploader_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_url: Mapped[str] = mapped_column(Text, nullable=False)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)
    file_type: Mapped[str] = mapped_column(String(80), nullable=False)


class StudentProfile(Base):
    __tablename__ = "student_profiles"

    id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    major_id: Mapped[str | None] = mapped_column(ForeignKey("university_majors.id"), nullable=True)
    student_code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    enrollment_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    graduation_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    date_of_birth: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    phone_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_status: Mapped[StudentStatus | None] = mapped_column(Enum(StudentStatus), nullable=True)
    degree_level: Mapped[DegreeLevel | None] = mapped_column(Enum(DegreeLevel), nullable=True)
    gpa_overall: Mapped[float | None] = mapped_column(Numeric(4, 2), nullable=True)
    attendance_overall: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    social_links: Mapped[dict] = mapped_column(JSON, default=dict)
    skills: Mapped[list | None] = mapped_column(JSON, nullable=True)
    privacy_settings: Mapped[dict] = mapped_column(JSON, default=dict)
    embedding: Mapped[list | None] = mapped_column(JSON, nullable=True)
    profile_completeness: Mapped[int] = mapped_column(Integer, default=0)

    major: Mapped[UniversityMajor | None] = relationship()


class AcademicRecord(Base):
    __tablename__ = "academic_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    student_id: Mapped[str] = mapped_column(ForeignKey("student_profiles.id"), index=True)
    subject_name: Mapped[str] = mapped_column(String(255), nullable=False)
    grade: Mapped[float | None] = mapped_column(Numeric(4, 2), nullable=True)
