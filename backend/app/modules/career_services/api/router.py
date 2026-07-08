"""University career-services counselor workspace routes (``/career-services``).

HTTP-only: validate the request, delegate to the application service (which
enforces RBAC, tenant isolation, and audit), and wrap the result in the
standard envelope (``docs/API_CONTRACTS.md``).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.modules.auth.api.deps import CurrentAuth, get_current_auth
from app.modules.career_services.api.schemas import (
    AppointmentCreateRequest,
    AppointmentStatusRequest,
    AtRiskFlagCreateRequest,
    AtRiskFlagStatusRequest,
    CohortCreateRequest,
    CohortMemberRequest,
    CohortUpdateRequest,
    CvReviewAssignRequest,
    CvReviewCreateRequest,
    CvReviewStatusRequest,
    EmployerNoteCreateRequest,
    EmployerNoteUpdateRequest,
    InterventionCreateRequest,
    InterventionOutcomeRequest,
)
from app.modules.career_services.application import (
    appointment_service,
    at_risk_service,
    cohort_service,
    cv_review_service,
    employer_note_service,
    intervention_service,
    reporting_service,
)
from app.shared.responses import success

router = APIRouter(prefix="/career-services", tags=["career-services"])


# --------------------------------------------------------------------------- #
# Cohorts                                                                     #
# --------------------------------------------------------------------------- #


@router.post(
    "/cohorts", status_code=status.HTTP_201_CREATED, summary="Create a cohort"
)
async def create_cohort(
    body: CohortCreateRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    locale: str = Query(default="vi"),
) -> dict:
    data = await cohort_service.create_cohort(
        session,
        principal=auth.principal,
        name=body.name,
        description=body.description,
        department_id=body.department_id,
        ctx=auth.ctx,
        locale=locale,
    )
    return success(data)


@router.get("/cohorts", summary="List cohorts")
async def list_cohorts(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    locale: str = Query(default="vi"),
) -> dict:
    data = await cohort_service.list_cohorts(
        session, principal=auth.principal, locale=locale
    )
    return success(data)


@router.patch("/cohorts/{cohort_id}", summary="Update a cohort")
async def update_cohort(
    cohort_id: uuid.UUID,
    body: CohortUpdateRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    locale: str = Query(default="vi"),
) -> dict:
    data = await cohort_service.update_cohort(
        session,
        principal=auth.principal,
        cohort_id=cohort_id,
        name=body.name,
        description=body.description,
        status=body.status,
        ctx=auth.ctx,
        locale=locale,
    )
    return success(data)


@router.delete(
    "/cohorts/{cohort_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Archive-delete a cohort",
)
async def delete_cohort(
    cohort_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    await cohort_service.delete_cohort(
        session, principal=auth.principal, cohort_id=cohort_id, ctx=auth.ctx
    )


@router.get("/cohorts/{cohort_id}/members", summary="List cohort members")
async def list_members(
    cohort_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await cohort_service.list_members(
        session, principal=auth.principal, cohort_id=cohort_id
    )
    return success(data)


@router.post(
    "/cohorts/{cohort_id}/members",
    status_code=status.HTTP_201_CREATED,
    summary="Add a student to a cohort (idempotent)",
)
async def add_member(
    cohort_id: uuid.UUID,
    body: CohortMemberRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await cohort_service.add_member(
        session,
        principal=auth.principal,
        cohort_id=cohort_id,
        student_id=body.student_id,
        ctx=auth.ctx,
    )
    return success(data)


@router.delete(
    "/cohorts/{cohort_id}/members/{student_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a student from a cohort (idempotent)",
)
async def remove_member(
    cohort_id: uuid.UUID,
    student_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    await cohort_service.remove_member(
        session,
        principal=auth.principal,
        cohort_id=cohort_id,
        student_id=student_id,
        ctx=auth.ctx,
    )


# --------------------------------------------------------------------------- #
# At-risk flags                                                               #
# --------------------------------------------------------------------------- #


@router.post(
    "/at-risk-flags",
    status_code=status.HTTP_201_CREATED,
    summary="Raise an at-risk flag for a student",
)
async def create_at_risk_flag(
    body: AtRiskFlagCreateRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    locale: str = Query(default="vi"),
) -> dict:
    data = await at_risk_service.create_flag(
        session,
        principal=auth.principal,
        student_id=body.student_id,
        reason=body.reason,
        severity=body.severity,
        notes=body.notes,
        cohort_id=body.cohort_id,
        ctx=auth.ctx,
        locale=locale,
    )
    return success(data)


@router.get("/at-risk-flags", summary="List at-risk flags")
async def list_at_risk_flags(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    student_id: uuid.UUID | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    locale: str = Query(default="vi"),
) -> dict:
    data = await at_risk_service.list_flags(
        session,
        principal=auth.principal,
        student_id=student_id,
        status=status_filter,
        locale=locale,
    )
    return success(data)


@router.patch(
    "/at-risk-flags/{flag_id}/status", summary="Update an at-risk flag's status"
)
async def update_at_risk_flag_status(
    flag_id: uuid.UUID,
    body: AtRiskFlagStatusRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    locale: str = Query(default="vi"),
) -> dict:
    data = await at_risk_service.update_flag_status(
        session,
        principal=auth.principal,
        flag_id=flag_id,
        status=body.status,
        resolution_notes=body.resolution_notes,
        ctx=auth.ctx,
        locale=locale,
    )
    return success(data)


# --------------------------------------------------------------------------- #
# CV review queue                                                             #
# --------------------------------------------------------------------------- #


@router.post(
    "/cv-review-items",
    status_code=status.HTTP_201_CREATED,
    summary="Queue a student CV for counselor review",
)
async def create_cv_review_item(
    body: CvReviewCreateRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    locale: str = Query(default="vi"),
) -> dict:
    data = await cv_review_service.create_item(
        session,
        principal=auth.principal,
        student_id=body.student_id,
        cv_id=body.cv_id,
        priority=body.priority,
        ctx=auth.ctx,
        locale=locale,
    )
    return success(data)


@router.get("/cv-review-items", summary="List CV review queue items")
async def list_cv_review_items(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    status_filter: str | None = Query(default=None, alias="status"),
    assigned_counselor_id: uuid.UUID | None = Query(default=None),
    locale: str = Query(default="vi"),
) -> dict:
    data = await cv_review_service.list_items(
        session,
        principal=auth.principal,
        status=status_filter,
        assigned_counselor_id=assigned_counselor_id,
        locale=locale,
    )
    return success(data)


@router.post(
    "/cv-review-items/{item_id}/assign", summary="Assign a counselor to a CV review"
)
async def assign_cv_review(
    item_id: uuid.UUID,
    body: CvReviewAssignRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    locale: str = Query(default="vi"),
) -> dict:
    data = await cv_review_service.assign_counselor(
        session,
        principal=auth.principal,
        item_id=item_id,
        counselor_id=body.counselor_id,
        ctx=auth.ctx,
        locale=locale,
    )
    return success(data)


@router.patch(
    "/cv-review-items/{item_id}/status", summary="Update a CV review item's status"
)
async def update_cv_review_status(
    item_id: uuid.UUID,
    body: CvReviewStatusRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    locale: str = Query(default="vi"),
) -> dict:
    data = await cv_review_service.update_status(
        session,
        principal=auth.principal,
        item_id=item_id,
        status=body.status,
        feedback=body.feedback,
        ctx=auth.ctx,
        locale=locale,
    )
    return success(data)


# --------------------------------------------------------------------------- #
# Appointments                                                                #
# --------------------------------------------------------------------------- #


@router.post(
    "/appointments", status_code=status.HTTP_201_CREATED, summary="Book an appointment"
)
async def book_appointment(
    body: AppointmentCreateRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    locale: str = Query(default="vi"),
) -> dict:
    data = await appointment_service.book_appointment(
        session,
        principal=auth.principal,
        student_id=body.student_id,
        counselor_id=body.counselor_id,
        scheduled_at=body.scheduled_at,
        duration_minutes=body.duration_minutes,
        mode=body.mode,
        location=body.location,
        notes=body.notes,
        ctx=auth.ctx,
        locale=locale,
    )
    return success(data)


@router.get("/appointments", summary="List appointments")
async def list_appointments(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    counselor_id: uuid.UUID | None = Query(default=None),
    student_id: uuid.UUID | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    locale: str = Query(default="vi"),
) -> dict:
    data = await appointment_service.list_appointments(
        session,
        principal=auth.principal,
        counselor_id=counselor_id,
        student_id=student_id,
        status=status_filter,
        locale=locale,
    )
    return success(data)


@router.patch(
    "/appointments/{appointment_id}/status", summary="Update an appointment's status"
)
async def update_appointment_status(
    appointment_id: uuid.UUID,
    body: AppointmentStatusRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    locale: str = Query(default="vi"),
) -> dict:
    data = await appointment_service.update_status(
        session,
        principal=auth.principal,
        appointment_id=appointment_id,
        status=body.status,
        cancel_reason=body.cancel_reason,
        ctx=auth.ctx,
        locale=locale,
    )
    return success(data)


# --------------------------------------------------------------------------- #
# Employer relationship notes                                                 #
# --------------------------------------------------------------------------- #


@router.post(
    "/employer-notes",
    status_code=status.HTTP_201_CREATED,
    summary="Create an employer relationship note",
)
async def create_employer_note(
    body: EmployerNoteCreateRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    locale: str = Query(default="vi"),
) -> dict:
    data = await employer_note_service.create_note(
        session,
        principal=auth.principal,
        employer_org_id=body.employer_org_id,
        category=body.category,
        visibility=body.visibility,
        note_text=body.note_text,
        ctx=auth.ctx,
        locale=locale,
    )
    return success(data)


@router.get("/employer-notes", summary="List employer relationship notes")
async def list_employer_notes(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    employer_org_id: uuid.UUID | None = Query(default=None),
    locale: str = Query(default="vi"),
) -> dict:
    data = await employer_note_service.list_notes(
        session,
        principal=auth.principal,
        employer_org_id=employer_org_id,
        locale=locale,
    )
    return success(data)


@router.patch("/employer-notes/{note_id}", summary="Update an employer relationship note")
async def update_employer_note(
    note_id: uuid.UUID,
    body: EmployerNoteUpdateRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    locale: str = Query(default="vi"),
) -> dict:
    data = await employer_note_service.update_note(
        session,
        principal=auth.principal,
        note_id=note_id,
        note_text=body.note_text,
        category=body.category,
        visibility=body.visibility,
        ctx=auth.ctx,
        locale=locale,
    )
    return success(data)


# --------------------------------------------------------------------------- #
# Intervention history                                                        #
# --------------------------------------------------------------------------- #


@router.post(
    "/interventions",
    status_code=status.HTTP_201_CREATED,
    summary="Log a counselor intervention",
)
async def create_intervention(
    body: InterventionCreateRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    locale: str = Query(default="vi"),
) -> dict:
    data = await intervention_service.create_intervention(
        session,
        principal=auth.principal,
        student_id=body.student_id,
        intervention_type=body.intervention_type,
        description=body.description,
        linked_appointment_id=body.linked_appointment_id,
        linked_at_risk_flag_id=body.linked_at_risk_flag_id,
        ctx=auth.ctx,
        locale=locale,
    )
    return success(data)


@router.get("/interventions", summary="List intervention history")
async def list_interventions(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    student_id: uuid.UUID | None = Query(default=None),
    locale: str = Query(default="vi"),
) -> dict:
    data = await intervention_service.list_interventions(
        session, principal=auth.principal, student_id=student_id, locale=locale
    )
    return success(data)


@router.patch(
    "/interventions/{record_id}/outcome", summary="Update an intervention's outcome"
)
async def update_intervention_outcome(
    record_id: uuid.UUID,
    body: InterventionOutcomeRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    locale: str = Query(default="vi"),
) -> dict:
    data = await intervention_service.update_outcome(
        session,
        principal=auth.principal,
        record_id=record_id,
        outcome=body.outcome,
        ctx=auth.ctx,
        locale=locale,
    )
    return success(data)


# --------------------------------------------------------------------------- #
# Outcomes reporting                                                          #
# --------------------------------------------------------------------------- #


@router.get("/reporting/summary", summary="Counselor workspace outcomes reporting")
async def get_reporting_summary(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    locale: str = Query(default="vi"),
) -> dict:
    data = await reporting_service.get_reporting_summary(
        session, principal=auth.principal, locale=locale
    )
    return success(data)
