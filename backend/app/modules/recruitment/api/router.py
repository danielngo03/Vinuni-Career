"""Applications HTTP routes: student apply/list/detail/withdraw, partner views,
anonymous-reveal handshake, and watermarked partner CV download.

Routers are HTTP-only: validate, delegate to services (which enforce RBAC + audit
+ tenant isolation + idempotency), and shape the response envelope.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, Query, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.modules.auth.api.deps import CurrentAuth, get_current_auth
from app.modules.recruitment.api.schemas import (
    AdvanceRequestBody,
    ApplyRequest,
    BulkRejectRequestBody,
    BulkReviewRequestBody,
    InterviewAssigneesBody,
    InterviewCancelBody,
    InterviewCompleteBody,
    InterviewRescheduleBody,
    InterviewScheduleBody,
    InviteRespondBody,
    InviteToApplyBody,
    OfferApproveBody,
    OfferCreateBody,
    OfferNegotiationBody,
    OfferRescindBody,
    OfferRespondBody,
    OfferSendBody,
    OfferSubmitBody,
    OfferUpdateBody,
    RejectRequestBody,
    RevealRequestBody,
    RevealRespondBody,
    ReviewRequestBody,
    RollbackRequestBody,
    ScorecardSubmitBody,
    WithdrawRequest,
)
from app.modules.recruitment.application import (
    apply_service,
    decision_service,
    export_service,
    interview_service,
    invitation_service,
    offer_compare_service,
    offer_service,
    pipeline_board,
    reveal_service,
    scorecard_ai_service,
    scorecard_service,
    screening_brief_service,
    stage_service,
)
from app.shared.responses import paginated, success

router = APIRouter(tags=["recruitment"])

applications_router = APIRouter(prefix="/applications")
job_applications_router = APIRouter(prefix="/jobs")
offers_router = APIRouter(prefix="/offers")


# --------------------------------------------------------------------------- #
# Student: submit / list / detail / withdraw                                  #
# --------------------------------------------------------------------------- #


@applications_router.post("", status_code=status.HTTP_201_CREATED, summary="Apply to a job")
async def apply(
    body: ApplyRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await apply_service.apply_to_job(
        session, principal=auth.principal, payload=body.model_dump(), ctx=auth.ctx,
    )
    return success(data)


@applications_router.get("", summary="List my applications (student)")
async def list_my_applications(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    cursor: str | None = Query(default=None),
    limit: int | None = Query(default=None),
) -> dict:
    items, next_cursor, page_limit = await apply_service.list_my_applications(
        session, principal=auth.principal, cursor=cursor, limit=limit,
    )
    return paginated(items, next_cursor=next_cursor, limit=page_limit)


@applications_router.get("/{application_id}", summary="Application detail (applicant or partner)")
async def get_application(
    application_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await apply_service.get_application(
        session, principal=auth.principal, application_id=application_id,
    )
    return success(data)


@applications_router.post(
    "/{application_id}/withdraw", summary="Withdraw an application (idempotent)"
)
async def withdraw_application(
    application_id: uuid.UUID,
    body: WithdrawRequest | None = None,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    # Body is optional: a bare withdraw needs no payload; ``version``/``reason``
    # are opt-in.
    data = await apply_service.withdraw_application(
        session,
        principal=auth.principal,
        application_id=application_id,
        version=body.version if body else None,
        reason=body.reason if body else None,
        ctx=auth.ctx,
    )
    return success(data)


@applications_router.get(
    "/{application_id}/cv-download", summary="Signed CV download (owner / watermarked partner)"
)
async def cv_download(
    application_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await apply_service.get_application_cv_download(
        session, principal=auth.principal, application_id=application_id,
    )
    return success(data)


# --------------------------------------------------------------------------- #
# Partner decision status: review / reject                                     #
# --------------------------------------------------------------------------- #


@applications_router.post(
    "/{application_id}/review", summary="Start reviewing an application (partner)"
)
async def review_application(
    application_id: uuid.UUID,
    body: ReviewRequestBody | None = None,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    # Body is optional: "start review" needs no payload. Mirrors the jobs
    # lifecycle endpoints (submit/close/reopen) which accept an optional body
    # carrying only the optimistic ``version``.
    data = await decision_service.review_application(
        session, principal=auth.principal, application_id=application_id,
        version=body.version if body else None, ctx=auth.ctx,
    )
    return success(data)


@applications_router.post(
    "/{application_id}/reject", summary="Reject an application (partner)"
)
async def reject_application(
    application_id: uuid.UUID,
    body: RejectRequestBody,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await decision_service.reject_application(
        session, principal=auth.principal, application_id=application_id,
        reason=body.reason, note=body.note, version=body.version, ctx=auth.ctx,
    )
    return success(data)


# --------------------------------------------------------------------------- #
# Pipeline stage engine: advance / rollback (partner)                          #
# --------------------------------------------------------------------------- #


@applications_router.post(
    "/{application_id}/advance", summary="Advance an application to the next stage (partner)"
)
async def advance_application(
    application_id: uuid.UUID,
    body: AdvanceRequestBody | None = None,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    # Body is optional ("advance" needs no payload beyond the optional optimistic
    # version); the Idempotency-Key header dedupes a true network retry.
    data = await stage_service.advance_application_stage(
        session, principal=auth.principal, application_id=application_id,
        version=body.version if body else None,
        idempotency_key=idempotency_key, ctx=auth.ctx,
    )
    return success(data)


@applications_router.post(
    "/{application_id}/rollback", summary="Roll an application back to a prior stage (partner)"
)
async def rollback_application(
    application_id: uuid.UUID,
    body: RollbackRequestBody,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await stage_service.rollback_application_stage(
        session, principal=auth.principal, application_id=application_id,
        target_stage_id=body.target_stage_id, reason=body.reason,
        version=body.version, idempotency_key=idempotency_key, ctx=auth.ctx,
    )
    return success(data)


# --------------------------------------------------------------------------- #
# Scorecards (partner-internal evaluation; ADR-0005)                           #
# --------------------------------------------------------------------------- #


@applications_router.post(
    "/{application_id}/scorecards",
    status_code=status.HTTP_201_CREATED,
    summary="Submit / upsert the caller's scorecard (partner)",
)
async def submit_scorecard(
    application_id: uuid.UUID,
    body: ScorecardSubmitBody,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await scorecard_service.submit_scorecard(
        session, principal=auth.principal, application_id=application_id,
        recommendation=body.recommendation,
        scores=[s.model_dump() for s in body.scores],
        comment=body.comment, version=body.version, ctx=auth.ctx,
    )
    return success(data)


@applications_router.get(
    "/{application_id}/scorecards",
    summary="List scorecards for a stage (partner; anchoring-aware)",
)
async def list_scorecards(
    application_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    stage_id: uuid.UUID | None = Query(default=None),
) -> dict:
    data = await scorecard_service.list_scorecards(
        session, principal=auth.principal, application_id=application_id,
        stage_id=stage_id,
    )
    return success(data)


@applications_router.post(
    "/{application_id}/scorecards/{scorecard_id}/withdraw",
    summary="Withdraw the caller's own scorecard (partner)",
)
async def withdraw_scorecard(
    application_id: uuid.UUID,
    scorecard_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await scorecard_service.withdraw_scorecard(
        session, principal=auth.principal, application_id=application_id,
        scorecard_id=scorecard_id, ctx=auth.ctx,
    )
    return success(data)


@applications_router.post(
    "/{application_id}/ai-scorecard-suggest",
    summary="AI-suggested criterion scores from interview notes (partner; human_review tier)",
)
async def ai_scorecard_suggest(
    application_id: uuid.UUID,
    body: dict,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    accept_language: str | None = Header(default=None),
) -> dict:
    """Generate AI score suggestions for the 4 standard criteria.

    Takes free-text ``notes`` from the interviewer and returns suggested scores
    per criterion plus an overall recommendation. These are DRAFT suggestions —
    the partner must review and explicitly submit via ``POST …/scorecards``.

    Body fields:
    - ``notes``: str (required, max 2000 chars)
    - ``job_title``: str (optional, for context)
    - ``interview_stage``: str (optional, e.g. "technical", "final")

    Returns ``{ data: { criteria, recommendation, overall_reasoning,
                         confidence, prompt_version, is_fallback } }``.
    """
    locale = (accept_language or "vi").split(",")[0].split("-")[0].strip()
    data = await scorecard_ai_service.suggest_scorecard(
        session,
        principal=auth.principal,
        application_id=application_id,
        notes=body.get("notes", ""),
        job_title=body.get("job_title"),
        interview_stage=body.get("interview_stage"),
        locale=locale,
    )
    return success(data)


@router.get(
    "/{application_id}/ai-screening-brief",
    summary="AI screening brief for a candidate (partner; advisory only)",
)
async def ai_screening_brief(
    application_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Generate a 3-4 bullet screening brief comparing the candidate CV to the role.

    Advisory only — the recruiter makes the final hire/reject decision.
    No PII is included in the AI prompt; privacy is enforced server-side.

    Returns ``{ data: { bullets, suitability, is_fallback, prompt_version } }``.
    """
    data = await screening_brief_service.generate_screening_brief(
        session,
        principal=auth.principal,
        application_id=application_id,
    )
    return success(data)


# --------------------------------------------------------------------------- #
# Interviews (partner-internal; ADR-0006)                                      #
# --------------------------------------------------------------------------- #


@applications_router.post(
    "/{application_id}/interviews",
    status_code=status.HTTP_201_CREATED,
    summary="Schedule the candidate's current-stage interview (partner)",
)
async def schedule_interview(
    application_id: uuid.UUID,
    body: InterviewScheduleBody,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await interview_service.schedule_interview(
        session, principal=auth.principal, application_id=application_id,
        mode=body.mode, scheduled_at=body.scheduled_at,
        assignee_ids=body.assignee_ids, duration_minutes=body.duration_minutes,
        location=body.location, meeting_link=body.meeting_link,
        title=body.title, notes=body.notes, ctx=auth.ctx,
    )
    return success(data)


@applications_router.get(
    "/{application_id}/interviews",
    summary="List the application's interviews (partner)",
)
async def list_interviews(
    application_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await interview_service.list_interviews(
        session, principal=auth.principal, application_id=application_id,
    )
    return success(data)


@applications_router.patch(
    "/{application_id}/interviews/{interview_id}",
    summary="Reschedule / edit an interview (partner)",
)
async def reschedule_interview(
    application_id: uuid.UUID,
    interview_id: uuid.UUID,
    body: InterviewRescheduleBody,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await interview_service.reschedule_interview(
        session, principal=auth.principal, application_id=application_id,
        interview_id=interview_id, scheduled_at=body.scheduled_at, mode=body.mode,
        location=body.location, meeting_link=body.meeting_link, title=body.title,
        notes=body.notes, version=body.version, ctx=auth.ctx,
    )
    return success(data)


@applications_router.put(
    "/{application_id}/interviews/{interview_id}/assignees",
    summary="Replace the interview assignee set (partner)",
)
async def set_interview_assignees(
    application_id: uuid.UUID,
    interview_id: uuid.UUID,
    body: InterviewAssigneesBody,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await interview_service.set_assignees(
        session, principal=auth.principal, application_id=application_id,
        interview_id=interview_id, assignee_ids=body.assignee_ids, ctx=auth.ctx,
    )
    return success(data)


@applications_router.post(
    "/{application_id}/interviews/{interview_id}/cancel",
    summary="Cancel an interview (partner)",
)
async def cancel_interview(
    application_id: uuid.UUID,
    interview_id: uuid.UUID,
    body: InterviewCancelBody | None = None,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await interview_service.cancel_interview(
        session, principal=auth.principal, application_id=application_id,
        interview_id=interview_id, version=body.version if body else None,
        ctx=auth.ctx,
    )
    return success(data)


@applications_router.post(
    "/{application_id}/interviews/{interview_id}/complete",
    summary="Complete an interview (completed / no_show) (partner)",
)
async def complete_interview(
    application_id: uuid.UUID,
    interview_id: uuid.UUID,
    body: InterviewCompleteBody,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await interview_service.complete_interview(
        session, principal=auth.principal, application_id=application_id,
        interview_id=interview_id, outcome=body.outcome, version=body.version,
        ctx=auth.ctx,
    )
    return success(data)


# --------------------------------------------------------------------------- #
# Anonymous reveal handshake                                                   #
# --------------------------------------------------------------------------- #


@applications_router.post("/{application_id}/reveal", summary="Request identity reveal (partner)")
async def request_reveal(
    application_id: uuid.UUID,
    body: RevealRequestBody,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await reveal_service.request_reveal(
        session, principal=auth.principal, application_id=application_id,
        reason=body.reason, ctx=auth.ctx,
    )
    return success(data)


@applications_router.post(
    "/{application_id}/reveal/respond", summary="Respond to a reveal request (student)"
)
async def respond_reveal(
    application_id: uuid.UUID,
    body: RevealRespondBody,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await reveal_service.respond_reveal(
        session, principal=auth.principal, application_id=application_id,
        decision=body.decision, ctx=auth.ctx,
    )
    return success(data)


# --------------------------------------------------------------------------- #
# Offers — partner management (ADR-0007 §8)                                     #
# --------------------------------------------------------------------------- #


@applications_router.post(
    "/{application_id}/offers",
    status_code=status.HTTP_201_CREATED,
    summary="Create a draft offer at the candidate's current stage (partner)",
)
async def create_offer(
    application_id: uuid.UUID,
    body: OfferCreateBody,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await offer_service.create_offer(
        session, principal=auth.principal, application_id=application_id,
        position_title=body.position_title, expiry_date=body.expiry_date,
        department=body.department, start_date=body.start_date,
        salary_amount=body.salary_amount, salary_currency=body.salary_currency,
        salary_period=body.salary_period, benefits_summary=body.benefits_summary,
        terms_notes=body.terms_notes, ctx=auth.ctx,
    )
    return success(data)


@applications_router.get(
    "/{application_id}/offers", summary="List an application's offers (partner)"
)
async def list_application_offers(
    application_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await offer_service.list_offers_partner(
        session, principal=auth.principal, application_id=application_id,
    )
    return success(data)


@applications_router.patch(
    "/{application_id}/offers/{offer_id}",
    summary="Edit a draft offer (partner; draft only)",
)
async def update_offer(
    application_id: uuid.UUID,
    offer_id: uuid.UUID,
    body: OfferUpdateBody,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await offer_service.update_draft(
        session, principal=auth.principal, offer_id=offer_id,
        position_title=body.position_title, department=body.department,
        start_date=body.start_date, salary_amount=body.salary_amount,
        salary_currency=body.salary_currency, salary_period=body.salary_period,
        benefits_summary=body.benefits_summary, terms_notes=body.terms_notes,
        expiry_date=body.expiry_date, version=body.version, ctx=auth.ctx,
    )
    return success(data)


@offers_router.post("/{offer_id}/submit", summary="Submit a draft offer for approval (partner)")
async def submit_offer(
    offer_id: uuid.UUID,
    body: OfferSubmitBody | None = None,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await offer_service.submit_offer(
        session, principal=auth.principal, offer_id=offer_id,
        version=body.version if body else None, ctx=auth.ctx,
    )
    return success(data)


@offers_router.post("/{offer_id}/approve", summary="Approve or reject-back an offer (partner)")
async def approve_offer(
    offer_id: uuid.UUID,
    body: OfferApproveBody,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await offer_service.approve_offer(
        session, principal=auth.principal, offer_id=offer_id,
        decision=body.decision, version=body.version, ctx=auth.ctx,
    )
    return success(data)


@offers_router.post("/{offer_id}/send", summary="Send an approved offer to the candidate (partner)")
async def send_offer(
    offer_id: uuid.UUID,
    body: OfferSendBody | None = None,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await offer_service.send_offer(
        session, principal=auth.principal, offer_id=offer_id,
        version=body.version if body else None, ctx=auth.ctx,
    )
    return success(data)


@offers_router.post("/{offer_id}/rescind", summary="Rescind an offer (partner)")
async def rescind_offer(
    offer_id: uuid.UUID,
    body: OfferRescindBody | None = None,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await offer_service.rescind_offer(
        session, principal=auth.principal, offer_id=offer_id,
        version=body.version if body else None, ctx=auth.ctx,
    )
    return success(data)


# --------------------------------------------------------------------------- #
# Offers — student (own offers; ADR-0007 §8 / API_CONTRACTS /offers)            #
# --------------------------------------------------------------------------- #


@offers_router.get("", summary="List my offers (student)")
async def list_my_offers(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await offer_service.list_offers_student(
        session, principal=auth.principal,
    )
    return success({"offers": data})


# NOTE: the static ``/compare`` + ``/negotiation-guidance`` routes MUST be declared
# before the dynamic ``/{offer_id}`` route so they are not captured as an offer id.


@offers_router.get("/compare", summary="Side-by-side comparison of my offers (student)")
async def compare_my_offers(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    accept_language: str | None = Header(default=None),
) -> dict:
    locale = (accept_language or "vi").split(",")[0].split("-")[0].strip()
    data = await offer_compare_service.compare_offers(
        session, principal=auth.principal, locale=locale,
    )
    return success(data)


@offers_router.post(
    "/negotiation-guidance",
    summary="On-demand AI negotiation guidance for my offers (student; metered)",
)
async def offer_negotiation_guidance(
    body: OfferNegotiationBody,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    accept_language: str | None = Header(default=None),
) -> dict:
    locale = (accept_language or "vi").split(",")[0].split("-")[0].strip()
    data = await offer_compare_service.negotiation_guidance(
        session, principal=auth.principal, confirm=body.confirm,
        ctx=auth.ctx, locale=locale,
    )
    return success(data)


@offers_router.get("/{offer_id}", summary="My offer detail (student; owner)")
async def get_my_offer(
    offer_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await offer_service.get_offer_student(
        session, principal=auth.principal, offer_id=offer_id,
    )
    return success(data)


@offers_router.post("/{offer_id}/respond", summary="Accept or decline an offer (student)")
async def respond_offer(
    offer_id: uuid.UUID,
    body: OfferRespondBody,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await offer_service.respond_offer(
        session, principal=auth.principal, offer_id=offer_id,
        decision=body.decision, notes=body.notes,
        idempotency_key=body.idempotency_key, ctx=auth.ctx,
    )
    return success(data)


# --------------------------------------------------------------------------- #
# Partner: applications to one of the org's jobs                               #
# --------------------------------------------------------------------------- #


@job_applications_router.get(
    "/{job_id}/applications", summary="Applications to a job (partner, org-scoped)"
)
async def list_job_applications(
    job_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    cursor: str | None = Query(default=None),
    limit: int | None = Query(default=None),
) -> dict:
    items, next_cursor, page_limit = await apply_service.list_job_applications(
        session, principal=auth.principal, job_id=job_id, cursor=cursor, limit=limit,
    )
    return paginated(items, next_cursor=next_cursor, limit=page_limit)


@job_applications_router.get(
    "/{job_id}/pipeline", summary="Pipeline kanban board for a job (partner, org-scoped)"
)
async def job_pipeline_board(
    job_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await pipeline_board.get_job_pipeline_board(
        session, principal=auth.principal, job_id=job_id,
    )
    return success(data)


@job_applications_router.get(
    "/{job_id}/applications/export",
    summary="Export all applications for a job as CSV (partner, org-scoped)",
)
async def export_job_applications(
    job_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    accept_language: str | None = Header(default=None),
) -> Response:
    locale = (accept_language or "vi").split(",")[0].split("-")[0].strip()
    csv_body = await export_service.export_applications_csv(
        session, principal=auth.principal, job_id=job_id, locale=locale,
    )
    filename = f"applications_{job_id}.csv"
    return Response(
        content=csv_body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# --------------------------------------------------------------------------- #
# Bulk partner decisions (ATS batch convenience; ADR-0004 §7)                  #
# --------------------------------------------------------------------------- #


@job_applications_router.post(
    "/{job_id}/applications/bulk-review",
    summary="Bulk-move submitted applications to under_review (partner)",
)
async def bulk_review_applications(
    job_id: uuid.UUID,
    body: BulkReviewRequestBody,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Move up to 100 submitted applications to ``under_review`` in one call.

    Each application is processed independently (idempotent per item). The
    ``job_id`` in the path is used for RBAC context but the service also validates
    per-application org ownership. Returns ``{reviewed, skipped, errors}`` counts.
    """
    data = await decision_service.bulk_review_applications(
        session,
        principal=auth.principal,
        application_ids=body.application_ids,
        ctx=auth.ctx,
    )
    return success(data)


@job_applications_router.post(
    "/{job_id}/applications/bulk-reject",
    summary="Bulk-reject applications (partner)",
)
async def bulk_reject_applications(
    job_id: uuid.UUID,
    body: BulkRejectRequestBody,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Reject up to 100 applications in one call (idempotent per item).

    ``reason`` is the same coded enum as the single-reject endpoint. Already
    hired / rejected / withdrawn applications are silently counted as skipped.
    Returns ``{rejected, skipped, errors}`` counts.
    """
    data = await decision_service.bulk_reject_applications(
        session,
        principal=auth.principal,
        application_ids=body.application_ids,
        reason=body.reason,
        note=body.note,
        ctx=auth.ctx,
    )
    return success(data)


invitations_router = APIRouter(prefix="/invitations", tags=["recruitment"])
student_invitations_router = APIRouter(prefix="/student", tags=["recruitment"])


@job_applications_router.post(
    "/{job_id}/invitations",
    status_code=status.HTTP_201_CREATED,
    summary="Partner invites a student to apply (job outreach)",
)
async def send_job_invitation(
    job_id: uuid.UUID,
    body: InviteToApplyBody,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await invitation_service.send_invite(
        session,
        principal=auth.principal,
        job_id=job_id,
        student_id=body.student_id,
        message=body.message,
    )
    return success(data)


@student_invitations_router.get(
    "/invitations",
    summary="List my job invitations (student)",
)
async def list_my_invitations(
    status: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await invitation_service.list_student_invitations(
        session,
        principal=auth.principal,
        status=status,
        limit=limit,
    )
    return success(data)


@student_invitations_router.get(
    "/invitations/{invitation_id}",
    summary="Get a single invitation detail (student)",
)
async def get_my_invitation(
    invitation_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await invitation_service.get_invitation(
        session, principal=auth.principal, invitation_id=invitation_id,
    )
    return success(data)


@invitations_router.post(
    "/{invitation_id}/respond",
    summary="Student accepts or declines a job invitation",
)
async def respond_invitation(
    invitation_id: uuid.UUID,
    body: InviteRespondBody,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await invitation_service.respond_invitation(
        session,
        principal=auth.principal,
        invitation_id=invitation_id,
        response=body.response,
        ctx=auth.ctx,
    )
    return success(data)


router.include_router(applications_router)
router.include_router(job_applications_router)
router.include_router(offers_router)
router.include_router(invitations_router)
router.include_router(student_invitations_router)
