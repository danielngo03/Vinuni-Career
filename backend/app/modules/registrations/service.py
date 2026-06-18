from __future__ import annotations

import re
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.registrations.schemas import (
    PendingRegistrationView,
    RegistrationChecklistItem,
    RegistrationEvidenceView,
    RegistrationQueueItem,
    RegistrationResubmitRequest,
    RegistrationReviewRequest,
    StudentRegistrationCreate,
    VerificationAssessment,
    VerificationPolicyUpdate,
)
from app.platform.database.models import (
    File,
    Industry,
    Organization,
    OrganizationIndustry,
    PartnerRegistration,
    Permission,
    RegistrationApplication,
    RegistrationEvidence,
    RegistrationHistory,
    RegistrationIndustry,
    Role,
    RolePermission,
    StudentProfile,
    StudentRegistration,
    UniversityMajor,
    User,
    UserOrgRole,
    VerificationPolicy,
)
from app.platform.storage import get_storage
from app.shared.config import settings
from app.shared.enum import (
    OrgType,
    RegistrationDecision,
    RegistrationStatus,
    RegistrationType,
    VerificationOutcome,
    VerificationPolicyMode,
)
from app.shared.errors import AppError, ErrorCode
from app.shared.security import hash_password

LOGO_TYPES = {"image/png", "image/jpeg", "image/webp"}
LEGAL_DOCUMENT_TYPES = {"application/pdf", "image/png", "image/jpeg"}


def submit_student_registration(
    db: Session,
    payload: StudentRegistrationCreate,
) -> RegistrationApplication:
    _ensure_email_available(db, payload.email)
    university = _get_university(db, payload.university_org_id)
    major = db.get(UniversityMajor, payload.major_id)
    if not major or major.org_id != university.id or not major.is_active:
        raise AppError(
            code=ErrorCode.BAD_REQUEST,
            message="The selected major is not available for this university",
            status_code=400,
        )
    if db.scalar(
        select(StudentRegistration).where(
            StudentRegistration.student_code == payload.student_code.strip()
        )
    ):
        raise AppError(
            code=ErrorCode.CONFLICT,
            message="Student code already has a registration",
            status_code=409,
        )
    user = User(
        email=payload.email,
        full_name=payload.full_name.strip(),
        password_hash=hash_password(payload.password),
        is_active=False,
    )
    db.add(user)
    db.flush()
    application = RegistrationApplication(
        user_id=user.id,
        university_org_id=university.id,
        registration_type=RegistrationType.STUDENT,
        status=RegistrationStatus.SUBMITTED,
        submitted_at=datetime.now(UTC),
    )
    db.add(application)
    db.flush()
    detail = StudentRegistration(
            application_id=application.id,
            student_code=payload.student_code.strip().upper(),
            major_id=major.id,
            degree_level=payload.degree_level.value,
            enrollment_year=payload.enrollment_year,
            expected_graduation_year=payload.expected_graduation_year,
            phone_number=payload.phone_number.strip(),
        )
    db.add(detail)
    db.flush()
    _record_initial_verification(db, application, user)
    db.commit()
    db.refresh(application)
    return application


def submit_partner_registration(
    db: Session,
    *,
    university_org_id: str,
    full_name: str,
    email: str,
    password: str,
    company_name: str,
    tax_code: str,
    website: str | None,
    company_size: str,
    founded_year: int | None,
    headquarters_address: str,
    company_description: str,
    representative_name: str,
    representative_title: str,
    representative_phone: str,
    representative_email: str,
    industry_ids: list[str],
    primary_industry_id: str,
    logo_name: str,
    logo_type: str,
    logo_content: bytes,
    license_name: str,
    license_type: str,
    license_content: bytes,
) -> RegistrationApplication:
    normalized_email = email.strip().lower()
    _ensure_email_available(db, normalized_email)
    university = _get_university(db, university_org_id)
    normalized_tax_code = re.sub(r"\s+", "", tax_code).upper()
    if db.scalar(
        select(PartnerRegistration).where(PartnerRegistration.tax_code == normalized_tax_code)
    ):
        raise AppError(
            code=ErrorCode.CONFLICT,
            message="Tax code already has a registration",
            status_code=409,
        )
    selected_industries = list(
        db.scalars(
            select(Industry).where(
                Industry.id.in_(industry_ids),
                Industry.university_org_id == university.id,
                Industry.is_active.is_(True),
            )
        )
    )
    if len(selected_industries) != len(set(industry_ids)):
        raise AppError(
            code=ErrorCode.BAD_REQUEST,
            message="One or more industries are invalid",
            status_code=400,
        )
    if primary_industry_id not in {item.id for item in selected_industries}:
        raise AppError(
            code=ErrorCode.BAD_REQUEST,
            message="Primary industry must be included in selected industries",
            status_code=400,
        )
    user = User(
        email=normalized_email,
        full_name=full_name.strip(),
        password_hash=hash_password(password),
        is_active=False,
    )
    db.add(user)
    db.flush()
    logo = _store_registration_file(
        db,
        user_id=user.id,
        file_name=logo_name,
        content_type=logo_type,
        content=logo_content,
        allowed_types=LOGO_TYPES,
        category="company-logo",
    )
    license_file = _store_registration_file(
        db,
        user_id=user.id,
        file_name=license_name,
        content_type=license_type,
        content=license_content,
        allowed_types=LEGAL_DOCUMENT_TYPES,
        category="business-license",
    )
    application = RegistrationApplication(
        user_id=user.id,
        university_org_id=university.id,
        registration_type=RegistrationType.PARTNER,
        status=RegistrationStatus.SUBMITTED,
        submitted_at=datetime.now(UTC),
    )
    db.add(application)
    db.flush()
    db.add(
        PartnerRegistration(
            application_id=application.id,
            company_name=company_name.strip(),
            tax_code=normalized_tax_code,
            website=website.strip() if website else None,
            company_size=company_size,
            founded_year=founded_year,
            headquarters_address=headquarters_address.strip(),
            company_description=company_description.strip(),
            representative_name=representative_name.strip(),
            representative_title=representative_title.strip(),
            representative_phone=representative_phone.strip(),
            representative_email=representative_email.strip().lower(),
            logo_file_id=logo.id,
            business_license_file_id=license_file.id,
        )
    )
    for industry_id in set(industry_ids):
        db.add(
            RegistrationIndustry(
                application_id=application.id,
                industry_id=industry_id,
                is_primary=industry_id == primary_industry_id,
            )
        )
    db.flush()
    _record_initial_verification(db, application, user)
    db.commit()
    db.refresh(application)
    return application


def registration_queue(
    db: Session,
    *,
    university_org_id: str,
    status: RegistrationStatus | None = None,
) -> list[RegistrationQueueItem]:
    stmt = (
        select(RegistrationApplication, User)
        .join(User, User.id == RegistrationApplication.user_id)
        .where(RegistrationApplication.university_org_id == university_org_id)
        .order_by(RegistrationApplication.submitted_at.desc())
    )
    if status:
        stmt = stmt.where(RegistrationApplication.status == status)
    result: list[RegistrationQueueItem] = []
    for application, user in db.execute(stmt):
        summary = _registration_summary(application)
        result.append(
            RegistrationQueueItem(
                id=application.id,
                registration_type=application.registration_type,
                status=application.status,
                university_org_id=application.university_org_id,
                submitted_at=application.submitted_at,
                reviewed_at=application.reviewed_at,
                review_note=application.review_note,
                version=application.version,
                checklist=application.checklist or [],
                assessment=application.assessment or {},
                policy_snapshot=application.policy_snapshot or {},
                applicant_name=user.full_name,
                applicant_email=user.email,
                summary=summary,
                evidence=list(application.evidence),
            )
        )
    return result


def review_registration(
    db: Session,
    *,
    application_id: str,
    university_org_id: str,
    reviewer_id: str,
    payload: RegistrationReviewRequest,
) -> RegistrationApplication:
    application = db.get(RegistrationApplication, application_id)
    if not application or application.university_org_id != university_org_id:
        raise AppError(
            code=ErrorCode.NOT_FOUND,
            message="Registration application not found",
            status_code=404,
        )
    status_by_decision = {
        RegistrationDecision.START_REVIEW: RegistrationStatus.UNDER_REVIEW,
        RegistrationDecision.REQUEST_CHANGES: RegistrationStatus.CHANGES_REQUESTED,
        RegistrationDecision.REJECT: RegistrationStatus.REJECTED,
        RegistrationDecision.APPROVE: RegistrationStatus.APPROVED,
    }
    next_status = status_by_decision[payload.decision]
    if payload.decision in {
        RegistrationDecision.REQUEST_CHANGES,
        RegistrationDecision.REJECT,
    } and not payload.note:
        raise AppError(
            code=ErrorCode.BAD_REQUEST,
            message="A review note is required for this decision",
            status_code=400,
        )
    if payload.decision == RegistrationDecision.REQUEST_CHANGES and not payload.checklist:
        raise AppError(
            code=ErrorCode.BAD_REQUEST,
            message="A field or document checklist is required when requesting changes",
            status_code=400,
        )
    allowed = {
        RegistrationStatus.SUBMITTED: {
            RegistrationDecision.START_REVIEW,
            RegistrationDecision.REQUEST_CHANGES,
            RegistrationDecision.APPROVE,
            RegistrationDecision.REJECT,
        },
        RegistrationStatus.RESUBMITTED: {
            RegistrationDecision.START_REVIEW,
            RegistrationDecision.REQUEST_CHANGES,
            RegistrationDecision.APPROVE,
            RegistrationDecision.REJECT,
        },
        RegistrationStatus.UNDER_REVIEW: {
            RegistrationDecision.REQUEST_CHANGES,
            RegistrationDecision.APPROVE,
            RegistrationDecision.REJECT,
        },
        # Compatibility for records created before the V2 workflow.
        RegistrationStatus.PENDING: {
            RegistrationDecision.START_REVIEW,
            RegistrationDecision.REQUEST_CHANGES,
            RegistrationDecision.APPROVE,
            RegistrationDecision.REJECT,
        },
        RegistrationStatus.NEEDS_CHANGES: set(),
        RegistrationStatus.CHANGES_REQUESTED: set(),
    }
    if payload.decision not in allowed.get(application.status, set()):
        raise AppError(
            code=ErrorCode.CONFLICT,
            message=f"Decision {payload.decision.value} is invalid from {application.status.value}",
            status_code=409,
        )
    previous_status = application.status
    if payload.decision == RegistrationDecision.APPROVE:
        _approve_registration(db, application)
    application.status = next_status
    application.review_note = payload.note
    application.checklist = (
        [item.model_dump() for item in payload.checklist]
        if payload.decision == RegistrationDecision.REQUEST_CHANGES
        else application.checklist
    )
    application.reviewed_by_id = reviewer_id
    application.reviewed_at = datetime.now(UTC)
    _append_history(
        db,
        application,
        from_status=previous_status,
        to_status=next_status,
        actor_id=reviewer_id,
        note=payload.note,
    )
    db.commit()
    db.refresh(application)
    return application


def pending_registration_for_user(db: Session, user_id: str) -> PendingRegistrationView:
    application = db.scalar(
        select(RegistrationApplication)
        .where(RegistrationApplication.user_id == user_id)
        .order_by(RegistrationApplication.submitted_at.desc())
    )
    if not application:
        raise AppError(
            code=ErrorCode.NOT_FOUND,
            message="Registration application not found",
            status_code=404,
        )
    user = db.get(User, user_id)
    if not user:
        raise AppError(
            code=ErrorCode.NOT_FOUND,
            message="Applicant user not found",
            status_code=404,
        )
    allowed_actions = ["view_status"]
    if application.status in {
        RegistrationStatus.CHANGES_REQUESTED,
        RegistrationStatus.NEEDS_CHANGES,
    }:
        allowed_actions.append("resubmit")
    if application.status not in {
        RegistrationStatus.APPROVED,
        RegistrationStatus.REJECTED,
        RegistrationStatus.WITHDRAWN,
    }:
        allowed_actions.append("withdraw")
    return PendingRegistrationView(
        id=application.id,
        registration_type=application.registration_type,
        status=application.status,
        university_org_id=application.university_org_id,
        submitted_at=application.submitted_at,
        reviewed_at=application.reviewed_at,
        review_note=application.review_note,
        version=application.version,
        checklist=application.checklist or [],
        assessment=application.assessment or {},
        policy_snapshot=application.policy_snapshot or {},
        applicant_name=user.full_name,
        applicant_email=user.email,
        summary=_registration_summary(application),
        evidence=[
            RegistrationEvidenceView.model_validate(item)
            for item in application.evidence
        ],
        allowed_actions=allowed_actions,
    )


def resubmit_registration(
    db: Session,
    *,
    user_id: str,
    payload: RegistrationResubmitRequest,
) -> RegistrationApplication:
    application = db.scalar(
        select(RegistrationApplication).where(RegistrationApplication.user_id == user_id)
    )
    if not application:
        raise AppError(
            code=ErrorCode.NOT_FOUND,
            message="Registration application not found",
            status_code=404,
        )
    if application.status not in {
        RegistrationStatus.CHANGES_REQUESTED,
        RegistrationStatus.NEEDS_CHANGES,
    }:
        raise AppError(
            code=ErrorCode.CONFLICT,
            message="Only an application with requested changes can be resubmitted",
            status_code=409,
        )
    checklist = application.checklist or []
    requested = {item.get("code") for item in checklist}
    resolved = set(payload.checklist_codes)
    if not requested or not requested.issubset(resolved):
        raise AppError(
            code=ErrorCode.BAD_REQUEST,
            message="All requested checklist items must be confirmed before resubmission",
            status_code=400,
        )
    previous_status = application.status
    application.version += 1
    application.status = RegistrationStatus.RESUBMITTED
    application.submitted_at = datetime.now(UTC)
    application.reviewed_at = None
    application.reviewed_by_id = None
    application.review_note = payload.note
    application.checklist = [{**item, "resolved": True} for item in checklist]
    user = db.get(User, user_id)
    if user:
        _record_initial_verification(db, application, user)
    _append_history(
        db,
        application,
        from_status=previous_status,
        to_status=RegistrationStatus.RESUBMITTED,
        actor_id=user_id,
        note=payload.note,
    )
    db.commit()
    db.refresh(application)
    return application


def get_or_create_verification_policy(
    db: Session,
    *,
    university_org_id: str,
    registration_type: RegistrationType,
) -> VerificationPolicy:
    policy = db.scalar(
        select(VerificationPolicy).where(
            VerificationPolicy.university_org_id == university_org_id,
            VerificationPolicy.registration_type == registration_type,
        )
    )
    if policy:
        return policy
    policy = VerificationPolicy(
        university_org_id=university_org_id,
        registration_type=registration_type,
        mode=VerificationPolicyMode.SHADOW,
        confidence_threshold=90,
        required_providers=["student_roster"]
        if registration_type == RegistrationType.STUDENT
        else ["business_registry"],
        required_documents=[]
        if registration_type == RegistrationType.STUDENT
        else ["business_license"],
        sample_rate=100,
        model_version="deterministic-v1",
    )
    db.add(policy)
    db.flush()
    return policy


def update_verification_policy(
    db: Session,
    *,
    university_org_id: str,
    registration_type: RegistrationType,
    payload: VerificationPolicyUpdate,
) -> VerificationPolicy:
    policy = get_or_create_verification_policy(
        db,
        university_org_id=university_org_id,
        registration_type=registration_type,
    )
    for key, value in payload.model_dump().items():
        setattr(policy, key, value)
    db.commit()
    db.refresh(policy)
    return policy


def _approve_registration(db: Session, application: RegistrationApplication) -> None:
    user = db.get(User, application.user_id)
    if not user:
        raise AppError(
            code=ErrorCode.NOT_FOUND,
            message="Applicant user not found",
            status_code=404,
        )
    if application.registration_type == RegistrationType.STUDENT:
        student_detail = application.student_detail
        if not student_detail:
            raise AppError(
                code=ErrorCode.BAD_REQUEST,
                message="Student registration details are missing",
                status_code=400,
            )
        role = _get_or_create_role(db, application.university_org_id, "student")
        _attach_permissions(db, role, [("student", "create"), ("cv", "mask"), ("ai", "use")])
        if not db.get(StudentProfile, user.id):
            db.add(
                StudentProfile(
                    id=user.id,
                    org_id=application.university_org_id,
                    major_id=student_detail.major_id,
                    student_code=student_detail.student_code,
                    enrollment_year=student_detail.enrollment_year,
                    graduation_year=student_detail.expected_graduation_year,
                    degree_level=student_detail.degree_level,
                    phone_number=student_detail.phone_number,
                    privacy_settings={
                        "blind_hiring": True,
                        "pii_unmask_requires_consent": True,
                    },
                )
            )
        _attach_identity(db, user.id, application.university_org_id, role.id)
    else:
        partner_detail = application.partner_detail
        if not partner_detail:
            raise AppError(
                code=ErrorCode.BAD_REQUEST,
                message="Partner registration details are missing",
                status_code=400,
            )
        organization = Organization(
            name=partner_detail.company_name,
            type=OrgType.PARTNER,
            is_verified_partner=True,
            metadata_json={
                "tax_code": partner_detail.tax_code,
                "website": partner_detail.website,
                "company_size": partner_detail.company_size,
                "founded_year": partner_detail.founded_year,
                "headquarters_address": partner_detail.headquarters_address,
                "description": partner_detail.company_description,
                "representative": {
                    "name": partner_detail.representative_name,
                    "title": partner_detail.representative_title,
                    "phone": partner_detail.representative_phone,
                    "email": partner_detail.representative_email,
                },
                "logo_file_id": partner_detail.logo_file_id,
                "business_license_file_id": partner_detail.business_license_file_id,
                "verified_from_registration_id": application.id,
            },
        )
        db.add(organization)
        db.flush()
        for selection in application.industries:
            db.add(
                OrganizationIndustry(
                    org_id=organization.id,
                    industry_id=selection.industry_id,
                    is_primary=selection.is_primary,
                )
            )
        role = _get_or_create_role(db, organization.id, "company_hr")
        _attach_permissions(db, role, [("job", "create"), ("ai", "use")])
        _attach_identity(db, user.id, organization.id, role.id)
    user.is_active = True


def _store_registration_file(
    db: Session,
    *,
    user_id: str,
    file_name: str,
    content_type: str,
    content: bytes,
    allowed_types: set[str],
    category: str,
) -> File:
    if content_type not in allowed_types:
        raise AppError(
            code=ErrorCode.BAD_REQUEST,
            message=f"Unsupported {category} file type",
            status_code=400,
        )
    max_bytes = settings.max_upload_mb * 1024 * 1024
    if not content or len(content) > max_bytes:
        raise AppError(
            code=ErrorCode.BAD_REQUEST,
            message=f"{category} must be between 1 byte and {settings.max_upload_mb}MB",
            status_code=400,
        )
    clean_name = re.sub(r"[^A-Za-z0-9._-]", "_", file_name or category)
    key = f"registrations/{user_id}/{category}/{uuid4()}-{clean_name}"
    stored = get_storage().put_bytes(key, content, content_type)
    file = File(
        uploader_id=user_id,
        file_name=file_name or clean_name,
        file_url=stored.url,
        is_public=False,
        file_type=content_type,
    )
    db.add(file)
    db.flush()
    return file


def _ensure_email_available(db: Session, email: str) -> None:
    if db.scalar(select(User).where(User.email == email.strip().lower())):
        raise AppError(
            code=ErrorCode.CONFLICT,
            message="Email already registered",
            status_code=409,
        )


def _get_university(db: Session, org_id: str) -> Organization:
    university = db.get(Organization, org_id)
    if not university or university.type != OrgType.UNIVERSITY:
        raise AppError(
            code=ErrorCode.BAD_REQUEST,
            message="Invalid university",
            status_code=400,
        )
    return university


def _get_or_create_role(db: Session, org_id: str, name: str) -> Role:
    role = db.scalar(select(Role).where(Role.org_id == org_id, Role.name == name))
    if not role:
        role = Role(org_id=org_id, name=name)
        db.add(role)
        db.flush()
    return role


def _attach_permissions(
    db: Session,
    role: Role,
    pairs: list[tuple[str, str]],
) -> None:
    for resource, action in pairs:
        permission = db.scalar(
            select(Permission).where(
                Permission.resource == resource,
                Permission.action == action,
            )
        )
        if not permission:
            permission = Permission(resource=resource, action=action)
            db.add(permission)
            db.flush()
        if not db.get(
            RolePermission,
            {"role_id": role.id, "permission_id": permission.id},
        ):
            db.add(RolePermission(role_id=role.id, permission_id=permission.id))


def _attach_identity(db: Session, user_id: str, org_id: str, role_id: str) -> None:
    existing = db.scalar(
        select(UserOrgRole).where(
            UserOrgRole.user_id == user_id,
            UserOrgRole.org_id == org_id,
            UserOrgRole.role_id == role_id,
        )
    )
    if not existing:
        db.add(UserOrgRole(user_id=user_id, org_id=org_id, role_id=role_id))


def _registration_summary(application: RegistrationApplication) -> dict:
    if application.registration_type == RegistrationType.STUDENT:
        student_detail = application.student_detail
        return {
            "student_code": student_detail.student_code if student_detail else None,
            "major_id": student_detail.major_id if student_detail else None,
            "enrollment_year": student_detail.enrollment_year if student_detail else None,
        }
    partner_detail = application.partner_detail
    return {
        "company_name": partner_detail.company_name if partner_detail else None,
        "tax_code": partner_detail.tax_code if partner_detail else None,
        "primary_industry_id": next(
            (item.industry_id for item in application.industries if item.is_primary),
            None,
        ),
    }


def _record_initial_verification(
    db: Session,
    application: RegistrationApplication,
    user: User,
) -> None:
    policy = get_or_create_verification_policy(
        db,
        university_org_id=application.university_org_id,
        registration_type=application.registration_type,
    )
    evidence: list[RegistrationEvidence] = []
    reasons: list[str] = []
    missing_items: list[RegistrationChecklistItem] = []
    confidence = 0
    low_risk = False

    if application.registration_type == RegistrationType.STUDENT:
        student_detail = application.student_detail
        domain_match = user.email.endswith("@vinuni.edu.vn")
        code_match = bool(
            student_detail
            and re.fullmatch(r"[A-Z]{2}\d{4}-\d{2,4}", student_detail.student_code)
        )
        evidence.extend(
            [
                RegistrationEvidence(
                    application_id=application.id,
                    version=application.version,
                    provider="email_domain",
                    field_name="email",
                    authority="institution_domain",
                    trust_weight=80,
                    confidence=100 if domain_match else 20,
                    extracted_value={"email": user.email, "domain_match": domain_match},
                    provenance={"method": "deterministic"},
                    mismatch=not domain_match,
                ),
                RegistrationEvidence(
                    application_id=application.id,
                    version=application.version,
                    provider="student_roster",
                    field_name="student_code",
                    authority="institution_roster",
                    trust_weight=95,
                    confidence=96 if code_match else 35,
                    extracted_value={
                        "student_code": student_detail.student_code if student_detail else None,
                        "format_match": code_match,
                    },
                    provenance={"method": "local_roster_adapter", "version": "demo-v1"},
                    mismatch=not code_match,
                ),
            ]
        )
        confidence = 96 if domain_match and code_match else 45
        low_risk = domain_match and code_match
        if not domain_match:
            missing_items.append(
                RegistrationChecklistItem(
                    code="institution_email",
                    label="Use or verify a VinUniversity email address",
                    field="email",
                )
            )
        if not code_match:
            missing_items.append(
                RegistrationChecklistItem(
                    code="student_code",
                    label="Confirm the student code with the registrar",
                    field="student_code",
                )
            )
        reasons.append("Student identity checked against institution domain and roster adapter.")
    else:
        partner_detail = application.partner_detail
        license_present = bool(partner_detail and partner_detail.business_license_file_id)
        evidence.extend(
            [
                RegistrationEvidence(
                    application_id=application.id,
                    version=application.version,
                    provider="document_store",
                    field_name="business_license",
                    authority="uploaded_document",
                    trust_weight=70,
                    confidence=90 if license_present else 0,
                    extracted_value={"document_present": license_present},
                    provenance={"method": "private_object_storage"},
                    mismatch=not license_present,
                ),
                RegistrationEvidence(
                    application_id=application.id,
                    version=application.version,
                    provider="business_registry",
                    field_name="tax_code",
                    authority="government_registry",
                    trust_weight=100,
                    confidence=0,
                    extracted_value={
                        "tax_code": partner_detail.tax_code if partner_detail else None
                    },
                    provenance={"status": "provider_unavailable"},
                    mismatch=False,
                ),
            ]
        )
        confidence = 62 if license_present else 20
        reasons.append(
            "Business registry is unavailable; the application is routed to human review."
        )
        if not license_present:
            missing_items.append(
                RegistrationChecklistItem(
                    code="business_license",
                    label="Upload a valid business registration document",
                    document="business_license",
                )
            )

    for item in evidence:
        db.add(item)

    outcome = (
        VerificationOutcome.APPROVE
        if low_risk and confidence >= policy.confidence_threshold and not missing_items
        else VerificationOutcome.REQUEST_CHANGES
        if missing_items
        else VerificationOutcome.MANUAL_REVIEW
    )
    assessment = VerificationAssessment(
        outcome=outcome,
        confidence=confidence,
        low_risk=low_risk,
        reasons=reasons,
        missing_items=missing_items,
    )
    application.assessment = assessment.model_dump(mode="json")
    application.policy_snapshot = {
        "mode": policy.mode.value,
        "global_kill_switch": policy.global_kill_switch,
        "confidence_threshold": policy.confidence_threshold,
        "required_providers": policy.required_providers,
        "required_documents": policy.required_documents,
        "sample_rate": policy.sample_rate,
        "model_version": policy.model_version,
    }
    if not application.history:
        _append_history(
            db,
            application,
            from_status=None,
            to_status=application.status,
            actor_id=user.id,
            note="Application submitted",
        )

    if (
        policy.mode == VerificationPolicyMode.AUTO_LOW_RISK
        and not policy.global_kill_switch
        and outcome == VerificationOutcome.APPROVE
    ):
        previous_status = application.status
        _approve_registration(db, application)
        application.status = RegistrationStatus.APPROVED
        application.review_note = "Automatically approved by low-risk verification policy."
        application.reviewed_at = datetime.now(UTC)
        _append_history(
            db,
            application,
            from_status=previous_status,
            to_status=RegistrationStatus.APPROVED,
            actor_id=None,
            note=application.review_note,
        )


def _append_history(
    db: Session,
    application: RegistrationApplication,
    *,
    from_status: RegistrationStatus | None,
    to_status: RegistrationStatus,
    actor_id: str | None,
    note: str | None,
) -> None:
    db.add(
        RegistrationHistory(
            application_id=application.id,
            version=application.version,
            from_status=from_status.value if from_status else None,
            to_status=to_status.value,
            actor_id=actor_id,
            note=note,
            snapshot={
                "checklist": application.checklist or [],
                "assessment": application.assessment or {},
            },
        )
    )


def run_verification_and_maybe_approve(db: Session, *, application_id: str) -> None:
    """
    Public entry point called by the outbox workflow activity.

    Re-runs the verification policy on an already-submitted application.
    Used when the initial verification was deferred to the async worker.
    Safe to call multiple times (idempotent on already-approved applications).
    """

    application = db.get(RegistrationApplication, application_id)
    if not application:
        return  # Already cleaned up or wrong ID
    if application.status in {
        RegistrationStatus.APPROVED,
        RegistrationStatus.REJECTED,
        RegistrationStatus.WITHDRAWN,
    }:
        return  # Terminal state — nothing to do

    user = db.get(User, application.user_id)
    if not user:
        return

    # Re-run the deterministic evidence collection and policy evaluation
    _record_initial_verification(db, application, user)
    db.commit()
