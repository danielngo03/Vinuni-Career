"""Jobs HTTP routes: public discovery, partner management, university moderation.

Routers are HTTP-only: validate, delegate to services (which enforce RBAC +
audit + tenant isolation), and shape the response envelope.

Design note (documented in ``docs/API_CONTRACTS.md``): ``GET /jobs`` is the
*public discovery* list (RBAC-aware; guests + any auth; visible/published only),
while ``GET /jobs/mine`` is the *partner-scoped* list of the caller org's own
jobs in any status. This keeps the two concerns on unambiguous paths instead of
overloading one route by principal.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Header, Query, Request, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.modules.auth.api.deps import CurrentAuth, get_current_auth
from app.modules.documents.application import job_fit_batch_service, job_fit_service
from app.modules.opportunities.api.events_router import (
    admin_events_router,
    events_router,
)
from app.modules.opportunities.api.industries_router import (
    admin_industries_router,
    industries_router,
)
from app.modules.opportunities.api.schemas import (
    BatchFitScoresRequest,
    JobApproveRequest,
    JobBulkApproveRequest,
    JobBulkRejectRequest,
    JobCloseRequest,
    JobCreateRequest,
    JobEscalateRequest,
    JobModerationRejectRequest,
    JobUpdateRequest,
)
from app.modules.opportunities.application import (
    competition_service,
    cover_letter_service,
    interview_sim_service,
    jd_ai_service,
    jd_upload_service,
    job_alert_service,
    job_service,
    moderation_service,
    saved_jobs_service,
    student_intelligence_service,
    translation_service,
)
from app.shared.permissions import GUEST, Principal
from app.shared.responses import paginated, success


async def _get_redis():
    """FastAPI dependency: yield a redis.asyncio client for the request lifetime.

    Redis is optional in local dev (no Redis -> endpoint returns HTTP 503).
    The client is closed in the finally block so connections are not leaked.
    """
    import redis.asyncio as aioredis

    from app.core.config import get_settings

    client = aioredis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        yield client
    finally:
        await client.aclose()

router = APIRouter(tags=["opportunities"])

jobs_router = APIRouter(prefix="/jobs")
# Static student-scoped GET routes (``/jobs/saved``, ``/jobs/alerts``) MUST be
# registered BEFORE the dynamic ``GET /jobs/{job_id}`` — otherwise Starlette
# matches ``/jobs/saved`` against ``/{job_id}`` (job_id="saved") and returns a
# 422 UUID-validation error, making both list pages dead end-to-end. This
# sub-router is included ahead of ``jobs_router`` at the bottom of this module.
jobs_me_router = APIRouter(prefix="/jobs")
admin_jobs_router = APIRouter(prefix="/admin/jobs")


# --------------------------------------------------------------------------- #
# Public discovery                                                            #
# --------------------------------------------------------------------------- #


@jobs_router.get("/config", summary="Job filter configuration (enum values)")
async def jobs_config() -> dict:
    """Return stable enum arrays for employment_type and location_type filters.

    These mirror DB enum columns. Frontend must call this and wait before
    rendering filter chips — do not render any filter chips from static frontend arrays.
    """
    return success({
        "employment_types": ["full_time", "part_time", "internship", "contract"],
        "location_types": ["onsite", "remote", "hybrid"],
    })


@jobs_router.get("", summary="Public job discovery (RBAC-aware, visible only)")
async def list_jobs(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    cursor: str | None = Query(default=None),
    page: int | None = Query(default=None, ge=1),
    limit: int | None = Query(default=None),
    q: str | None = Query(default=None),
    employment_type: str | None = Query(default=None),
    location_type: str | None = Query(default=None),
    location_types: str | None = Query(
        default=None, description="Comma-separated work modes (multi-select); OR-matched."
    ),
    province_code: str | None = Query(default=None),
    ward_code: str | None = Query(default=None),
    province_codes: str | None = Query(default=None),
    ward_codes: str | None = Query(default=None),
    # Deprecated free-text industry search — kept for backward compat only.
    # Prefer the canonical deepest-scope params below (mutually exclusive).
    industry_terms: str | None = Query(default=None),
    industry_group_id: uuid.UUID | None = Query(
        default=None, description="Level-0 industry scope (matches all descendants)."
    ),
    industry_id: uuid.UUID | None = Query(
        default=None, description="Level-1 industry scope (matches its level-2 children)."
    ),
    specialization_id: uuid.UUID | None = Query(
        default=None, description="Level-2 industry scope (exact match, no expansion)."
    ),
    salary_min: int | None = Query(default=None, ge=0),
    salary_max: int | None = Query(default=None, ge=0),
    experience_min_years: int | None = Query(default=None, ge=0, le=60),
    experience_max_years: int | None = Query(default=None, ge=0, le=60),
    posted_within_days: int | None = Query(default=None, ge=1, le=365),
    sort: str | None = Query(default=None),
) -> dict:
    principal: Principal = GUEST
    if request.headers.get("authorization"):
        try:
            auth = await get_current_auth(request, session)
            principal = auth.principal
        except Exception:  # noqa: BLE001
            principal = GUEST
    items, next_cursor, page_limit, total = await job_service.list_public_jobs(
        session, principal=principal, cursor=cursor, page=page, limit=limit,
        q=q, employment_type=employment_type, location_type=location_type,
        location_types=location_types,
        province_code=province_code, ward_code=ward_code,
        province_codes=province_codes, ward_codes=ward_codes,
        industry_terms=industry_terms,
        industry_group_id=industry_group_id,
        industry_id=industry_id,
        specialization_id=specialization_id,
        salary_min=salary_min, salary_max=salary_max,
        experience_min_years=experience_min_years,
        experience_max_years=experience_max_years,
        posted_within_days=posted_within_days,
        sort=sort,
    )
    body = paginated(items, next_cursor=next_cursor, limit=page_limit)
    body["page"]["total"] = total
    return body


@jobs_router.get("/mine", summary="Partner-scoped list of the caller org's jobs")
async def list_my_jobs(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    cursor: str | None = Query(default=None),
    limit: int | None = Query(default=None),
    job_status: str | None = Query(default=None, alias="status"),
) -> dict:
    items, next_cursor, page_limit = await job_service.list_my_jobs(
        session, principal=auth.principal, status=job_status,
        cursor=cursor, limit=limit,
    )
    return paginated(items, next_cursor=next_cursor, limit=page_limit)


# NOTE: the two interview-sim history routes are static sub-paths and MUST be
# declared before the ``/{job_id}`` param route below, otherwise FastAPI would
# try to parse "interview-sim" as a job UUID and 422 the request.
@jobs_router.get(
    "/interview-sim/history",
    summary="My interview practice history + deterministic readiness signal (student)",
)
async def interview_sim_history(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Return the caller's own interview practice attempts + readiness signal.

    Student-scoped: only the caller's own attempts are visible. The readiness
    signal is a deterministic aggregate over evaluated answers — below the
    minimum it honestly reports ``status="not_enough_data"`` (no fabricated
    number). Returns ``{ data: { readiness, sessions } }``.
    """
    from app.modules.opportunities.application import interview_history_service

    data = await interview_history_service.get_history(
        session, principal=auth.principal
    )
    return success(data)


@jobs_router.get(
    "/interview-sim/history/{sim_session_id}",
    summary="One interview practice attempt with its answered turns (student)",
)
async def interview_sim_session_detail(
    sim_session_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Return one owned practice attempt with its Q/answer/feedback turns.

    Owner-checked + student-scoped: a missing attempt is 404, another student's
    attempt is 403. Returns ``{ data: { session, turns } }``.
    """
    from app.modules.opportunities.application import interview_history_service

    data = await interview_history_service.get_session_detail(
        session, principal=auth.principal, session_id=sim_session_id
    )
    return success(data)


@jobs_router.get("/{job_id}", summary="Job detail (owner full / public visible / 404)")
async def get_job(
    job_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    principal: Principal = GUEST
    if request.headers.get("authorization"):
        try:
            auth = await get_current_auth(request, session)
            principal = auth.principal
        except Exception:  # noqa: BLE001
            principal = GUEST
    data = await job_service.get_job(
        session, principal=principal, job_id=job_id,
        user_agent=request.headers.get("user-agent"),
    )
    return success(data)


# --------------------------------------------------------------------------- #
# Competition signal (public; RBAC-aware visibility)                          #
# --------------------------------------------------------------------------- #


@jobs_router.get(
    "/{job_id}/competition-signal",
    summary="Competition level signal for a visible job (public, no auth required)",
)
async def get_competition_signal(
    job_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Return an on-the-fly competition level signal for a publicly visible job.

    The signal is computed deterministically from the job's JD complexity
    (experience requirement, skill count, employment type) plus a count of
    active applications. An optional one-sentence Vietnamese AI explanation is
    appended when real AI calls are enabled; it degrades to ``explanation: null``
    under the default offline provider.

    Public endpoint — no ``Authorization`` header required. Authenticated callers
    can access jobs beyond the ``public`` visibility tier. Hidden, closed, or
    non-existent jobs are indistinguishable: both return ``404``.

    Response shape::

        {
          "data": {
            "level": "medium",
            "label": "Trung bình",
            "explanation": "...",
            "ai_explanation_available": true,
            "basis": "estimated",
            "jd_complexity_score": 20,
            "application_count": null,
            "updated_at": "2026-06-30T12:00:00+00:00"
          }
        }
    """

    principal: Principal = GUEST
    if request.headers.get("authorization"):
        try:
            auth = await get_current_auth(request, session)
            principal = auth.principal
        except Exception:  # noqa: BLE001
            principal = GUEST

    data = await competition_service.competition_signal(
        session, principal=principal, job_id=job_id
    )
    return success(data)


# --------------------------------------------------------------------------- #
# Student job intelligence (authenticated-student only; E35 B-535..B-540)     #
# --------------------------------------------------------------------------- #


@jobs_router.get(
    "/{job_id}/student-intelligence",
    summary="Combined student job intelligence: best CV, fit, competition, next actions",
)
async def get_student_intelligence(
    job_id: uuid.UUID,
    cv_id: uuid.UUID | None = Query(default=None),
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    accept_language: str | None = Header(default=None),
) -> dict:
    """Authenticated-student-only combined job-detail intelligence.

    Guests must use public job detail (``GET /jobs/{job_id}``) and never reach
    this endpoint — ``get_current_auth`` returns ``401`` with no
    ``Authorization`` header, and a non-student persona is rejected with
    ``403`` in the service layer. See ``docs/API_CONTRACTS.md`` "Student Job
    Intelligence" for the response contract.

    Personalized guidance strings (improvement actions, learning-gap
    suggestions, next-action labels, competition guidance) are localized
    server-side because the frontend renders them as raw backend strings.
    """

    locale = (accept_language or "vi").split(",")[0].split("-")[0].strip()
    data = await student_intelligence_service.student_intelligence_for_job(
        session, principal=auth.principal, job_id=job_id, cv_id=cv_id,
        locale=locale,
    )
    return success(data)


@jobs_router.get(
    "/{job_id}/fit-explanation",
    summary="Async AI fit explanation for the recommended (or chosen) CV (student only)",
)
async def get_fit_explanation(
    job_id: uuid.UUID,
    cv_id: uuid.UUID | None = Query(default=None),
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    accept_language: str | None = Header(default=None),
) -> dict:
    """Authenticated-student-only AI explanation for the CV-to-job fit.

    Split from ``GET /jobs/{job_id}/student-intelligence`` so the deterministic
    score/bands render immediately: that endpoint no longer waits on the LLM,
    and the frontend fires THIS separately, showing an "evaluating" state until
    it returns.

    Guests / non-student personas are rejected the same way as
    ``get_student_intelligence`` (``get_current_auth`` -> 401 without a token; a
    non-student persona -> 403 in the service layer). ``cv_id`` (optional)
    explains that CV when it belongs to the caller and is scored; otherwise the
    recommended CV. Hidden/closed/missing jobs -> 404.

    Returns ``{ data: { cv_id, explanation, analysis, improvements,
    learning_resources, ai_explanation_available } }``. ``analysis`` is the
    STRUCTURED matching detail (per-requirement matched evidence + confirmed gaps
    with advisory suggestions + overall suggestion), ``null`` when the AI narrative
    is unavailable. ``improvements`` are confirmation-gated CV-Studio edit-command
    hand-offs (one per fit gap); ``learning_resources`` are internal curated
    learning foci (one per fit gap, ``{skill, resource_type, suggestion}``) — a
    pure deterministic mapping with no external URLs. Both are present even when the
    AI is off. On AI-off / provider failure -> ``explanation: null`` +
    ``analysis: null`` + ``ai_explanation_available: false`` (never an error).
    Provider/model/token/prompt/cost internals are never exposed.
    """
    locale = (accept_language or "vi").split(",")[0].split("-")[0].strip()
    data = await job_fit_service.fit_explanation_for_job(
        session, principal=auth.principal, job_id=job_id, cv_id=cv_id, locale=locale
    )
    return success(data)


@jobs_router.get(
    "/{job_id}/competition-explanation",
    summary="On-demand AI competition narrative for the Competition drawer (student only)",
)
async def get_competition_explanation(
    job_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    accept_language: str | None = Header(default=None),
    redis=Depends(_get_redis),
) -> dict:
    """Authenticated-student-only AI narrative that explains the competition bands.

    Fired ONLY when the student opens the Competition drawer (not on the default
    job-detail load — the deterministic bands from
    ``GET /jobs/{job_id}/student-intelligence`` render immediately and free). The
    narrative is grounded in the pre-computed level, cached, and metered: a fresh
    generation charges the student's AI energy once (idempotent per ``(job,
    level)``); a cache hit charges nothing. AI never moves the numbers.

    Guests / non-student personas are rejected the same way as
    ``get_fit_explanation`` (``get_current_auth`` -> 401 without a token; a
    non-student persona -> 403 in the service layer). Hidden/closed/missing jobs
    -> 404. On AI-off / provider failure / weekly-energy exhaustion / low signal
    -> ``explanation: null`` + ``ai_explanation_available: false`` (never an
    error). Provider/model/token/prompt/cost internals are never exposed.

    Returns ``{ data: { level, label, explanation, ai_explanation_available } }``.
    """

    locale = (accept_language or "vi").split(",")[0].split("-")[0].strip()
    data = await competition_service.competition_explanation(
        session, principal=auth.principal, job_id=job_id, locale=locale, redis=redis
    )
    return success(data)


@jobs_router.post(
    "/fit-scores",
    summary="Batch CV fit scores for a list of jobs (authenticated student only)",
)
async def batch_fit_scores(
    body: BatchFitScoresRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    redis=Depends(_get_redis),
) -> dict:
    """Return deterministic CV-job fit scores for up to 50 jobs in one call.

    Intended for job-list page loads: the frontend fires this after receiving a
    paginated job list and uses the scores to hydrate the fit-score badges on each
    card without a separate per-job request.

    - Cache hit (Redis): score returned instantly, no DB read.
    - Cache miss: job + CV data loaded from DB, score computed in pure Python
      (<1 ms / job), result written to Redis (TTL 4 h).
    - No active CVs: empty scores dict returned (200).
    - Non-student or missing auth: 401/403.

    Response::

        {
          "data": {
            "scores": {
              "<job_id>": {
                "score": 72,
                "recommended_cv_id": "<uuid>",
                "signal": "ok",
                "stale": false
              }
            }
          }
        }

    Jobs that are not found or not visible to the student are silently omitted
    (no entry in the scores dict); the frontend renders no badge for those cards.
    """
    scores = await job_fit_batch_service.batch_fit_for_jobs(
        session,
        redis,
        principal=auth.principal,
        job_ids=body.job_ids,
    )
    return success({"scores": scores})


# --------------------------------------------------------------------------- #
# Partner management                                                          #
# --------------------------------------------------------------------------- #


@jobs_router.post("", status_code=status.HTTP_201_CREATED, summary="Create a draft job")
async def create_job(
    body: JobCreateRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await job_service.create_job(
        session, principal=auth.principal,
        payload=body.model_dump(), ctx=auth.ctx,
    )
    return success(data)


@jobs_router.patch(
    "/{job_id}", summary="Update a draft/rejected job, or amend a published job"
)
async def update_job(
    job_id: uuid.UUID,
    body: JobUpdateRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await job_service.update_job(
        session, principal=auth.principal, job_id=job_id,
        payload=body.model_dump(exclude_unset=True), ctx=auth.ctx,
    )
    return success(data)


@jobs_router.post("/{job_id}/submit", summary="Submit a job for moderation")
async def submit_job(
    job_id: uuid.UUID,
    body: JobCloseRequest | None = None,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    version = body.version if body else None
    data = await job_service.submit_job(
        session, principal=auth.principal, job_id=job_id, ctx=auth.ctx, version=version,
    )
    return success(data)


@jobs_router.get(
    "/{job_id}/quality-check",
    summary="Preview the JD quality-check rubric before submitting (partner only)",
)
async def quality_check_job(
    job_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await job_service.check_jd_quality(
        session, principal=auth.principal, job_id=job_id,
    )
    return success(data)


@jobs_router.get(
    "/{job_id}/preview",
    summary="Preview the job as a guest or logged-in student would see it (partner only)",
)
async def preview_job(
    job_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    as_persona: str = Query(default="guest", alias="as"),
) -> dict:
    data = await job_service.preview_job(
        session, principal=auth.principal, job_id=job_id, as_persona=as_persona,
    )
    return success(data)


@jobs_router.post("/{job_id}/close", summary="Close an active job")
async def close_job(
    job_id: uuid.UUID,
    body: JobCloseRequest | None = None,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    version = body.version if body else None
    data = await job_service.close_job(
        session, principal=auth.principal, job_id=job_id, ctx=auth.ctx, version=version,
    )
    return success(data)


@jobs_router.post("/{job_id}/reopen", summary="Reopen a closed job")
async def reopen_job(
    job_id: uuid.UUID,
    body: JobCloseRequest | None = None,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    version = body.version if body else None
    data = await job_service.reopen_job(
        session, principal=auth.principal, job_id=job_id, ctx=auth.ctx, version=version,
    )
    return success(data)


@jobs_router.delete("/{job_id}", summary="Soft-delete / archive a job")
async def delete_job(
    job_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    await job_service.delete_job(
        session, principal=auth.principal, job_id=job_id, ctx=auth.ctx,
    )
    return success({"status": "deleted"})


@jobs_router.post(
    "/{job_id}/duplicate",
    status_code=status.HTTP_201_CREATED,
    summary="Create a draft copy of an existing job (partner only)",
)
async def duplicate_job(
    job_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    accept_language: str | None = Header(default=None),
) -> dict:
    locale = (accept_language or "vi").split(",")[0].split("-")[0].strip()
    return await job_service.duplicate_job(
        session,
        principal=auth.principal,
        job_id=job_id,
        ctx=auth.ctx,
        locale=locale,
    )


# --------------------------------------------------------------------------- #
# AI: Interview Simulator (student — read_only; returns static bank on failure)#
# --------------------------------------------------------------------------- #


@jobs_router.post(
    "/{job_id}/ai-interview-prep",
    summary="Generate tailored interview questions for student prep (read-only advisory)",
)
async def ai_interview_prep(
    job_id: uuid.UUID,
    body: dict,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    accept_language: str | None = Header(default=None),
) -> dict:
    """Generates N interview questions + prep tips for a publicly visible job.

    The job must be published and visible to the caller. Output is ephemeral —
    never stored and never sent to the hiring partner. On AI failure the service
    returns a static fallback question bank so students always get useful output.

    Request body (all optional):
    - ``num_questions``: int (3-10, default 6)
    - ``student_instruction``: str (optional free-text context, e.g. background)

    Returns ``{ data: { questions, prep_tips, prompt_version, is_fallback } }``.
    """
    locale = (accept_language or "vi").split(",")[0].split("-")[0].strip()
    data = await interview_sim_service.generate_interview_prep(
        session,
        principal=auth.principal,
        job_id=job_id,
        num_questions=int(body.get("num_questions", 6)),
        student_instruction=body.get("student_instruction"),
        locale=locale,
        ctx=auth.ctx,
    )
    return success(data)


@jobs_router.post(
    "/{job_id}/interview-sim/answer-feedback",
    summary=(
        "Evaluate a student's practice interview answer and return coaching "
        "feedback (read-only advisory)"
    ),
)
async def interview_sim_answer_feedback(
    job_id: uuid.UUID,
    body: dict,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Returns AI coaching feedback on a student's practice interview answer.

    The job must be published and publicly visible. The Q/answer/feedback are
    saved to the student's own practice history (never sent to the hiring
    partner). On AI failure a static fallback coaching tip is returned
    (is_fallback=True).

    Request body (required):
    - ``question``: str — the interview question text
    - ``question_type``: str — behavioral|technical|situational|motivation
    - ``rubric``: str — the rubric from the question set
    - ``answer``: str — the student's practice answer

    Request body (optional):
    - ``session_id``: uuid — the practice attempt to attach this turn to
    - ``question_number``: int — the question index within the attempt

    Returns ``{ data: { score, praise, improve, hint, prompt_version, is_fallback } }``.
    """
    raw_session_id = body.get("session_id")
    session_id: uuid.UUID | None = None
    if raw_session_id:
        try:
            session_id = uuid.UUID(str(raw_session_id))
        except (ValueError, TypeError):
            session_id = None
    try:
        question_number = int(body.get("question_number", 0))
    except (ValueError, TypeError):
        question_number = 0
    data = await interview_sim_service.evaluate_answer(
        session,
        principal=auth.principal,
        job_id=job_id,
        question=str(body.get("question") or "")[:400],
        question_type=str(body.get("question_type") or "behavioral")[:30],
        rubric=str(body.get("rubric") or "")[:300],
        answer=str(body.get("answer") or "")[:600],
        session_id=session_id,
        question_number=question_number,
        ctx=auth.ctx,
    )
    return success(data)


@jobs_router.post(
    "/{job_id}/ai-cover-letter",
    summary="Generate a cover letter draft for a student applying to a job (read-only advisory)",
)
async def ai_cover_letter(
    job_id: uuid.UUID,
    body: dict,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Generates a personalised cover letter draft for the authenticated student.

    The job must be published and publicly visible. Output is ephemeral — never
    stored and never sent to the partner. The student must review and paste it
    into their application manually. On AI failure a template-based draft is
    returned (is_fallback=True).

    Request body (all optional):
    - ``student_note``: str — extra context from the student (e.g. why they want this role)

    Returns ``{ data: { draft, prompt_version, is_fallback } }``.
    """
    data = await cover_letter_service.generate_cover_letter(
        session,
        principal=auth.principal,
        job_id=job_id,
        student_note=body.get("student_note"),
    )
    return success(data)


# --------------------------------------------------------------------------- #
# Saved jobs (student favourites — Heart affordance)                          #
# --------------------------------------------------------------------------- #


@jobs_me_router.get(
    "/saved",
    summary="List the authenticated student's saved jobs (cursor-paginated)",
)
async def list_saved_jobs(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    cursor: str | None = Query(default=None),
    limit: int | None = Query(default=None),
    accept_language: str | None = Header(default=None),
) -> dict:
    locale = (accept_language or "vi").split(",")[0].split("-")[0].strip()
    items, next_cursor, page_limit = await saved_jobs_service.list_saved_jobs(
        session,
        principal=auth.principal,
        cursor=cursor,
        limit=limit,
        locale=locale,
    )
    return paginated(items, next_cursor=next_cursor, limit=page_limit)


@jobs_router.post(
    "/{job_id}/save",
    status_code=status.HTTP_200_OK,
    summary="Save a job (idempotent heart-affordance; student only)",
)
async def save_job(
    job_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await saved_jobs_service.save_job(
        session, principal=auth.principal, job_id=job_id
    )
    return success(data)


@jobs_router.delete(
    "/{job_id}/save",
    status_code=status.HTTP_200_OK,
    summary="Unsave a job (idempotent; student only)",
)
async def unsave_job(
    job_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await saved_jobs_service.unsave_job(
        session, principal=auth.principal, job_id=job_id
    )
    return success(data)


# --------------------------------------------------------------------------- #
# Job Alerts (student subscriptions to new-job notifications)                 #
# --------------------------------------------------------------------------- #


@jobs_me_router.get(
    "/alerts",
    summary="List the authenticated student's job alerts",
)
async def list_job_alerts(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Returns all active job alerts for the authenticated student."""
    data = await job_alert_service.list_alerts(session, principal=auth.principal)
    return success(data)


@jobs_router.post(
    "/alerts",
    summary="Create a new job alert for the authenticated student",
    status_code=status.HTTP_201_CREATED,
)
async def create_job_alert(
    body: dict,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Creates a new job alert subscription.

    Request body:
    - ``name``: str (required) — short descriptive label
    - ``keywords``: str (optional) — keyword filter
    - ``employment_type``: str (optional) — full_time / part_time / internship / ...
    - ``location_type``: str (optional) — onsite / remote / hybrid
    - ``province_code``: str (optional) — province code from the location list

    Returns the created alert. Max 10 active alerts per student.
    """
    data = await job_alert_service.create_alert(
        session,
        principal=auth.principal,
        name=str(body.get("name") or "")[:120],
        keywords=body.get("keywords") or None,
        employment_type=body.get("employment_type") or None,
        location_type=body.get("location_type") or None,
        province_code=body.get("province_code") or None,
        ctx=auth.ctx,
    )
    return success(data)


@jobs_router.delete(
    "/alerts/{alert_id}",
    summary="Delete (deactivate) a job alert owned by the authenticated student",
)
async def delete_job_alert(
    alert_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Deactivates a job alert. The alert is soft-deleted and will no longer
    trigger notifications. Returns ``{"status": "deleted"}``."""
    await job_alert_service.delete_alert(
        session, principal=auth.principal, alert_id=alert_id, ctx=auth.ctx
    )
    return success({"status": "deleted"})


# --------------------------------------------------------------------------- #
# JD Upload: extract fields from partner-uploaded PDF/DOCX                    #
# --------------------------------------------------------------------------- #


@jobs_router.post(
    "/upload-jd",
    summary="Upload a job description (PDF/DOCX/TXT/image) and extract structured fields",
)
async def upload_jd_document(
    file: UploadFile = File(..., description="PDF, DOCX, TXT, or image job description"),
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Extract structured job fields from an uploaded document for form prefill.

    Supports digital PDFs/DOCX/TXT and images/scans (OCR + vision). Returns
    prefill-ready fields on success, a raw-text fallback when AI is unavailable,
    and a user-safe validation error for blank/not-a-JD/corrupt files. Never
    writes to the database.

    Metering: extraction that spends LLM/vision tokens debits the partner org's
    AI energy (weekly-energy preflight gate + per-tier charge). The commit
    persists the energy-ledger row.
    """
    data = await file.read()
    result = await jd_upload_service.extract_jd_from_upload(
        filename=file.filename or "upload",
        data=data,
        content_type=file.content_type,
        db=session,
        principal=auth.principal,
    )
    await session.commit()
    return result


# --------------------------------------------------------------------------- #
# JD Translation (public — AI + DB cache; no auth required)                   #
# --------------------------------------------------------------------------- #


@jobs_router.post(
    "/{job_id}/translate",
    summary="Translate a job description to the target language (AI + DB cache)",
)
async def translate_job(
    job_id: uuid.UUID,
    target_lang: str = Query(default="vi", pattern="^(vi|en)$"),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """On-demand JD translation with AI enrichment and persistent DB cache.

    - Returns cached result instantly when a prior translation exists.
    - Calls the AI gateway (``chat_cheap`` alias) when no cache entry exists.
    - Returns HTTP 503 when AI is offline; the frontend should render an
      'unavailable' state rather than an error message.
    - No authentication required — public jobs are translatable by anyone.
    - Translating a job that is already in ``target_lang`` returns HTTP 422.
    """
    from sqlalchemy import select as _select

    from app.modules.opportunities.domain.models import Job
    from app.shared.exceptions import ResourceNotFoundError, ValidationFailedError

    job = (
        await session.execute(
            _select(Job).where(Job.id == job_id, Job.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if job is None:
        raise ResourceNotFoundError("Không tìm thấy tin tuyển dụng.")

    result = await translation_service.get_or_create_translation(
        session, job=job, target_lang=target_lang
    )
    if result is None:
        from fastapi import HTTPException

        # Distinguish "same language" from "AI unavailable" in the response
        source_lang = job.language_code or "en"
        if source_lang == target_lang:
            raise ValidationFailedError(
                f"Tin tuyển dụng đã ở ngôn ngữ '{target_lang}'."
            )
        raise HTTPException(
            status_code=503,
            detail="translation_unavailable",
        )

    return success(result)


# --------------------------------------------------------------------------- #
# AI: JD Writer (partner only — draft, no auto-publish)                       #
# --------------------------------------------------------------------------- #


@jobs_router.post(
    "/ai-draft-description",
    summary="Generate a JD draft from form inputs only (no existing job required)",
)
async def ai_draft_description_standalone(
    body: dict,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    accept_language: str | None = Header(default=None),
) -> dict:
    """Standalone JD Writer — useful during new-job creation before a job exists.

    Returns ``{ data: { draft, prompt_version } }``. Advisory only; the partner
    applies the draft via the standard ``POST /jobs`` or ``PATCH /jobs/{id}`` flow.
    """
    locale = (accept_language or "vi").split(",")[0].split("-")[0].strip()
    data = await jd_ai_service.draft_description_standalone(
        session,
        principal=auth.principal,
        payload=body,
        locale=locale,
    )
    return success(data)


@jobs_router.post(
    "/{job_id}/ai-draft-description",
    summary="Generate a JD draft anchored to an existing job (carries job title/context)",
)
async def ai_draft_description(
    job_id: uuid.UUID,
    body: dict,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    accept_language: str | None = Header(default=None),
) -> dict:
    """AI-assisted JD draft. Returns ``{ data: { draft, prompt_version } }``.

    The draft is NOT stored and does NOT modify the job. Partners review and
    apply it via the standard ``PATCH /jobs/{id}`` update endpoint.
    """
    locale = (accept_language or "vi").split(",")[0].split("-")[0].strip()
    data = await jd_ai_service.draft_description(
        session,
        principal=auth.principal,
        job_id=job_id,
        payload=body,
        locale=locale,
    )
    return success(data)


# --------------------------------------------------------------------------- #
# University moderation                                                       #
# --------------------------------------------------------------------------- #


@admin_jobs_router.get("", summary="Job moderation queue (university only)")
async def moderation_queue(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    job_status: str | None = Query(default=None, alias="status"),
    limit: int | None = Query(default=None),
) -> dict:
    items, total = await moderation_service.list_moderation_queue(
        session, principal=auth.principal, status=job_status, limit=limit,
    )
    return success(items, meta={"count": total})


@admin_jobs_router.post("/{job_id}/approve", summary="Approve + publish a job")
async def approve_job(
    job_id: uuid.UUID,
    body: JobApproveRequest | None = None,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    version = body.version if body else None
    note = body.note if body else None
    data = await moderation_service.approve_job(
        session, principal=auth.principal, job_id=job_id, version=version,
        note=note, ctx=auth.ctx,
    )
    return success(data)


@admin_jobs_router.post("/{job_id}/reject", summary="Reject a job")
async def reject_job(
    job_id: uuid.UUID,
    body: JobModerationRejectRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await moderation_service.reject_job(
        session, principal=auth.principal, job_id=job_id,
        reason=body.reason, reason_code=body.reason_code, version=body.version,
        ctx=auth.ctx,
    )
    return success(data)


@admin_jobs_router.post("/{job_id}/claim", summary="Claim a job for review")
async def claim_job(
    job_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await moderation_service.claim_job(
        session, principal=auth.principal, job_id=job_id, ctx=auth.ctx,
    )
    return success(data)


@admin_jobs_router.post(
    "/{job_id}/escalate", summary="Escalate a job to the human review queue"
)
async def escalate_job(
    job_id: uuid.UUID,
    body: JobEscalateRequest | None = None,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    reason_code = body.reason_code if body else None
    note = body.note if body else None
    data = await moderation_service.escalate_job(
        session, principal=auth.principal, job_id=job_id,
        reason_code=reason_code, note=note, ctx=auth.ctx,
    )
    return success(data)


@admin_jobs_router.post("/bulk-approve", summary="Approve multiple jobs")
async def bulk_approve_jobs(
    body: JobBulkApproveRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    results = await moderation_service.bulk_approve_jobs(
        session, principal=auth.principal, job_ids=body.job_ids, ctx=auth.ctx,
    )
    return success(results)


@admin_jobs_router.post("/bulk-reject", summary="Reject multiple jobs")
async def bulk_reject_jobs(
    body: JobBulkRejectRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    items = [item.model_dump() for item in body.items]
    results = await moderation_service.bulk_reject_jobs(
        session, principal=auth.principal, items=items, ctx=auth.ctx,
    )
    return success(results)


router.include_router(jobs_me_router)  # static /jobs/saved,/jobs/alerts before /jobs/{job_id}
router.include_router(jobs_router)
router.include_router(admin_jobs_router)
router.include_router(events_router)
router.include_router(admin_events_router)
router.include_router(industries_router)
router.include_router(admin_industries_router)
