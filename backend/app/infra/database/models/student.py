from __future__ import annotations

from sqlalchemy import JSON, Boolean, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infra.database.models.base import SoftDeleteMixin, TimestampMixin, uuid_str
from app.infra.database.session import Base


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
    student_code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    gpa_overall: Mapped[float | None] = mapped_column(Numeric(4, 2), nullable=True)
    attendance_overall: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    privacy_settings: Mapped[dict] = mapped_column(JSON, default=dict)
    embedding: Mapped[list | None] = mapped_column(JSON, nullable=True)


class AcademicRecord(Base):
    __tablename__ = "academic_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    student_id: Mapped[str] = mapped_column(ForeignKey("student_profiles.id"), index=True)
    subject_name: Mapped[str] = mapped_column(String(255), nullable=False)
    grade: Mapped[float | None] = mapped_column(Numeric(4, 2), nullable=True)


class CV(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "cvs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    student_id: Mapped[str] = mapped_column(ForeignKey("student_profiles.id"), index=True)
    file_id: Mapped[str | None] = mapped_column(ForeignKey("files.id"), nullable=True)
    parsed_data: Mapped[dict] = mapped_column(JSON, default=dict)
    masked_data: Mapped[dict] = mapped_column(JSON, default=dict)
    embedding: Mapped[list | None] = mapped_column(JSON, nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
