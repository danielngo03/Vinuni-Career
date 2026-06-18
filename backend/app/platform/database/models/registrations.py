from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.platform.database.models.base import TimestampMixin, now_utc, uuid_str
from app.platform.database.session import Base
from app.shared.enum import RegistrationStatus, RegistrationType, VerificationPolicyMode


class Industry(Base, TimestampMixin):
    __tablename__ = "industries"
    __table_args__ = (
        UniqueConstraint("university_org_id", "code", name="uq_industries_university_code"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    university_org_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id"),
        index=True,
    )
    parent_id: Mapped[str | None] = mapped_column(
        ForeignKey("industries.id"),
        nullable=True,
    )
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    name_vi: Mapped[str] = mapped_column(String(255), nullable=False)
    name_en: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class RegistrationApplication(Base, TimestampMixin):
    __tablename__ = "registration_applications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    university_org_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id"),
        index=True,
    )
    registration_type: Mapped[RegistrationType] = mapped_column(
        Enum(RegistrationType),
        index=True,
    )
    status: Mapped[RegistrationStatus] = mapped_column(
        Enum(RegistrationStatus),
        default=RegistrationStatus.PENDING,
        index=True,
    )
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    reviewed_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    checklist: Mapped[list] = mapped_column(JSON, default=list)
    assessment: Mapped[dict] = mapped_column(JSON, default=dict)
    policy_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)

    student_detail: Mapped[StudentRegistration | None] = relationship(
        back_populates="application",
        uselist=False,
        cascade="all, delete-orphan",
    )
    partner_detail: Mapped[PartnerRegistration | None] = relationship(
        back_populates="application",
        uselist=False,
        cascade="all, delete-orphan",
    )
    industries: Mapped[list[RegistrationIndustry]] = relationship(
        back_populates="application",
        cascade="all, delete-orphan",
    )
    evidence: Mapped[list[RegistrationEvidence]] = relationship(
        back_populates="application",
        cascade="all, delete-orphan",
    )
    history: Mapped[list[RegistrationHistory]] = relationship(
        back_populates="application",
        cascade="all, delete-orphan",
    )


class VerificationPolicy(Base, TimestampMixin):
    __tablename__ = "verification_policies"
    __table_args__ = (
        UniqueConstraint(
            "university_org_id",
            "registration_type",
            name="uq_verification_policy_university_type",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    university_org_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id"),
        index=True,
    )
    registration_type: Mapped[RegistrationType] = mapped_column(
        Enum(RegistrationType),
        index=True,
    )
    mode: Mapped[VerificationPolicyMode] = mapped_column(
        Enum(VerificationPolicyMode),
        default=VerificationPolicyMode.SHADOW,
    )
    global_kill_switch: Mapped[bool] = mapped_column(Boolean, default=False)
    confidence_threshold: Mapped[int] = mapped_column(Integer, default=90)
    required_providers: Mapped[list] = mapped_column(JSON, default=list)
    required_documents: Mapped[list] = mapped_column(JSON, default=list)
    sample_rate: Mapped[int] = mapped_column(Integer, default=100)
    model_version: Mapped[str] = mapped_column(String(120), default="deterministic-v1")


class RegistrationEvidence(Base, TimestampMixin):
    __tablename__ = "registration_evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    application_id: Mapped[str] = mapped_column(
        ForeignKey("registration_applications.id"),
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    provider: Mapped[str] = mapped_column(String(120), index=True)
    field_name: Mapped[str] = mapped_column(String(120), index=True)
    authority: Mapped[str] = mapped_column(String(80), default="self_reported")
    trust_weight: Mapped[int] = mapped_column(Integer, default=50)
    confidence: Mapped[int] = mapped_column(Integer, default=0)
    extracted_value: Mapped[dict] = mapped_column(JSON, default=dict)
    provenance: Mapped[dict] = mapped_column(JSON, default=dict)
    mismatch: Mapped[bool] = mapped_column(Boolean, default=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    application: Mapped[RegistrationApplication] = relationship(back_populates="evidence")


class RegistrationHistory(Base):
    __tablename__ = "registration_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    application_id: Mapped[str] = mapped_column(
        ForeignKey("registration_applications.id"),
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer)
    from_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    to_status: Mapped[str] = mapped_column(String(40), index=True)
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    application: Mapped[RegistrationApplication] = relationship(back_populates="history")


class StudentRegistration(Base):
    __tablename__ = "student_registrations"

    application_id: Mapped[str] = mapped_column(
        ForeignKey("registration_applications.id"),
        primary_key=True,
    )
    student_code: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    major_id: Mapped[str] = mapped_column(ForeignKey("university_majors.id"), index=True)
    degree_level: Mapped[str] = mapped_column(String(40))
    enrollment_year: Mapped[int] = mapped_column(Integer)
    expected_graduation_year: Mapped[int] = mapped_column(Integer)
    phone_number: Mapped[str] = mapped_column(String(30))

    application: Mapped[RegistrationApplication] = relationship(
        back_populates="student_detail",
    )


class PartnerRegistration(Base):
    __tablename__ = "partner_registrations"

    application_id: Mapped[str] = mapped_column(
        ForeignKey("registration_applications.id"),
        primary_key=True,
    )
    company_name: Mapped[str] = mapped_column(String(255), index=True)
    tax_code: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    company_size: Mapped[str] = mapped_column(String(80))
    founded_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    headquarters_address: Mapped[str] = mapped_column(String(500))
    company_description: Mapped[str] = mapped_column(Text)
    representative_name: Mapped[str] = mapped_column(String(255))
    representative_title: Mapped[str] = mapped_column(String(160))
    representative_phone: Mapped[str] = mapped_column(String(30))
    representative_email: Mapped[str] = mapped_column(String(320))
    logo_file_id: Mapped[str] = mapped_column(ForeignKey("files.id"))
    business_license_file_id: Mapped[str] = mapped_column(ForeignKey("files.id"))

    application: Mapped[RegistrationApplication] = relationship(
        back_populates="partner_detail",
    )


class RegistrationIndustry(Base):
    __tablename__ = "registration_industries"

    application_id: Mapped[str] = mapped_column(
        ForeignKey("registration_applications.id"),
        primary_key=True,
    )
    industry_id: Mapped[str] = mapped_column(ForeignKey("industries.id"), primary_key=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)

    application: Mapped[RegistrationApplication] = relationship(
        back_populates="industries",
    )
    industry: Mapped[Industry] = relationship()


class OrganizationIndustry(Base):
    __tablename__ = "organization_industries"

    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), primary_key=True)
    industry_id: Mapped[str] = mapped_column(ForeignKey("industries.id"), primary_key=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
