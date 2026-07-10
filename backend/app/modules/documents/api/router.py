"""CV Studio HTTP routes (documents module).

Routers are HTTP-only: validate, delegate to services (which enforce RBAC +
ownership + audit), and shape the response envelope. The signed-file download
endpoint is authorized by the signed token itself, not a session.

Route order note: the static ``/cvs/upload`` and ``/cvs/parse-runs/...`` routes are
declared BEFORE ``/cvs/{cv_id}`` so the dynamic segment does not capture them.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db_session
from app.modules.auth.api.deps import CurrentAuth, get_current_auth, get_request_context
from app.modules.auth.application.context import RequestContext
from app.modules.documents.api.schemas import (
    AcceptAiSuggestionRequest,
    AiEditCommandRequest,
    AiSuggestionRequest,
    CreateCvRequest,
    CreateSectionRequest,
    CvTemplateCreateRequest,
    CvTemplateUpdateRequest,
    DuplicateCvRequest,
    ExportCvRequest,
    ImportIngestionRequest,
    IngestRequest,
    RestoreVersionRequest,
    SectionUpsertRequest,
    UpdateCvCanvasRequest,
    UpdateCvRequest,
)
from app.modules.documents.application import (
    cv_ai_service,
    cv_canvas_service,
    cv_creation_service,
    cv_lifecycle_service,
    cv_photo_service,
    cv_section_service,
    cv_service,
    download_service,
    export_service,
    ingestion_service,
    job_fit_service,
    template_admin_service,
    upload_service,
)
from app.shared.exceptions import ValidationFailedError
from app.shared.responses import paginated, success

router = APIRouter(tags=["documents"])

cvs_router = APIRouter(prefix="/cvs")
templates_router = APIRouter(prefix="/cv-templates")
admin_templates_router = APIRouter(prefix="/admin/cv-templates")
exports_router = APIRouter(prefix="/cv-exports")
files_router = APIRouter(prefix="/cv-files")
uploads_router = APIRouter(prefix="/cv-uploads")
ingestions_router = APIRouter(prefix="/cv-ingestions")


# --------------------------------------------------------------------------- #
# Templates                                                                   #
# --------------------------------------------------------------------------- #


@templates_router.get("", summary="List active CV templates")
async def list_templates(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    items = await cv_service.list_templates(session)
    return success(items)


@admin_templates_router.get("", summary="Admin: list all CV templates")
async def list_templates_admin(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    items = await template_admin_service.list_templates_admin(session, principal=auth.principal)
    return success(items, meta={"count": len(items)})


@admin_templates_router.post(
    "", status_code=status.HTTP_201_CREATED, summary="Admin: create a CV template"
)
async def create_template_admin(
    body: CvTemplateCreateRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await template_admin_service.create_template(
        session,
        principal=auth.principal,
        payload=body.model_dump(mode="json"),
        ctx=auth.ctx,
    )
    return success(data)


@admin_templates_router.patch("/{template_id}", summary="Admin: update a CV template")
async def update_template_admin(
    template_id: uuid.UUID,
    body: CvTemplateUpdateRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await template_admin_service.update_template(
        session,
        principal=auth.principal,
        template_id=template_id,
        payload=body.model_dump(exclude_unset=True, mode="json"),
        ctx=auth.ctx,
    )
    return success(data)


# --------------------------------------------------------------------------- #
# Upload + parse                                                              #
# --------------------------------------------------------------------------- #


@cvs_router.post("/upload", summary="Upload a CV file and start a parse run")
async def upload_cv(
    file: UploadFile = File(...),
    idempotency_key: str = Form(...),
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    settings = get_settings()
    data = await file.read()
    if len(data) > settings.max_upload_bytes:
        # Fail fast before buffering more; the validator also enforces this.
        raise ValidationFailedError(
            "Tệp quá lớn. Hãy nén hoặc chia nhỏ tệp rồi tải lại.",
            details={"reason": "file_too_large"},
        )
    result = await upload_service.upload_cv(
        session,
        principal=auth.principal,
        filename=file.filename or "upload",
        data=data,
        content_type=file.content_type,
        idempotency_key=idempotency_key,
        ctx=auth.ctx,
    )
    return success(result)


@cvs_router.get("/parse-runs/{parse_run_id}", summary="Get parse-run status (owner only)")
async def get_parse_run(
    parse_run_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await upload_service.get_parse_run(
        session, principal=auth.principal, parse_run_id=parse_run_id
    )
    return success(data)


# --------------------------------------------------------------------------- #
# CV ingestion (adapter cascade): upload preview -> ingest -> review -> import #
# --------------------------------------------------------------------------- #


@uploads_router.post("", summary="Upload a CV file and get preview/upload metadata")
async def create_upload(
    file: UploadFile = File(...),
    idempotency_key: str | None = Form(default=None),
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    settings = get_settings()
    data = await file.read()
    if len(data) > settings.max_upload_bytes:
        raise ValidationFailedError(
            "Tệp quá lớn. Hãy nén hoặc chia nhỏ tệp rồi tải lại.",
            details={"reason": "file_too_large"},
        )
    result = await ingestion_service.create_upload(
        session,
        principal=auth.principal,
        filename=file.filename or "upload",
        data=data,
        content_type=file.content_type,
        idempotency_key=idempotency_key,
        ctx=auth.ctx,
    )
    return success(result)


@uploads_router.post("/{document_id}/ingest", summary="Start or resume CV ingestion")
async def ingest_upload(
    document_id: uuid.UUID,
    body: IngestRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    result = await ingestion_service.start_ingestion(
        session,
        principal=auth.principal,
        document_id=document_id,
        idempotency_key=body.idempotency_key,
        ctx=auth.ctx,
    )
    return success(result)


@ingestions_router.get("/{ingestion_id}", summary="Get ingestion status (owner only)")
async def get_ingestion(
    ingestion_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    result = await ingestion_service.get_ingestion(
        session, principal=auth.principal, ingestion_id=ingestion_id
    )
    return success(result)


@ingestions_router.post(
    "/{ingestion_id}/import",
    status_code=status.HTTP_201_CREATED,
    summary="Import a reviewed ingestion into a new/draft CV",
)
async def import_ingestion(
    ingestion_id: uuid.UUID,
    body: ImportIngestionRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    result = await ingestion_service.import_ingestion(
        session,
        principal=auth.principal,
        ingestion_id=ingestion_id,
        payload=body.model_dump(mode="json"),
        ctx=auth.ctx,
    )
    return success(result)


# --------------------------------------------------------------------------- #
# CV-to-job fit scoring + best-CV recommendation                              #
# (declared before ``/{cv_id}`` so the static path is not captured)           #
# --------------------------------------------------------------------------- #


@cvs_router.get("/job-fit", summary="Score the caller's active CVs against a job")
async def cv_job_fit(
    job_id: uuid.UUID = Query(...),
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    # DETERMINISTIC-ONLY (fast): return every active CV's score/bands with NO LLM
    # wait. Both consumers (the job-detail intelligence panel and the CV-studio
    # fit rail) render the deterministic fit immediately and load the AI narrative
    # separately via ``GET /jobs/{job_id}/fit-explanation`` — so blocking this call
    # on the 20s explanation LLM was the source of the job-detail stall.
    data = await job_fit_service.job_fit_for_job(
        session, principal=auth.principal, job_id=job_id, with_explanation=False
    )
    return success(data)


# --------------------------------------------------------------------------- #
# Builder CRUD                                                                #
# --------------------------------------------------------------------------- #


@cvs_router.post("", status_code=status.HTTP_201_CREATED, summary="Create a CV")
async def create_cv(
    body: CreateCvRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    payload = body.model_dump()
    data = await cv_creation_service.create_cv(
        session, principal=auth.principal, payload=payload, ctx=auth.ctx
    )
    return success(data)


@cvs_router.get("", summary="List the caller's CVs")
async def list_cvs(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    cursor: str | None = Query(default=None),
    limit: int | None = Query(default=None),
) -> dict:
    items, next_cursor, page_limit = await cv_service.list_cvs(
        session, principal=auth.principal, cursor=cursor, limit=limit
    )
    quota = await cv_service.cv_library_quota(session, principal=auth.principal)
    return paginated(items, next_cursor=next_cursor, limit=page_limit, meta=quota)


@cvs_router.get("/{cv_id}", summary="Get a CV detail (owner only)")
async def get_cv(
    cv_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await cv_service.get_cv(session, principal=auth.principal, cv_id=cv_id)
    return success(data)


@cvs_router.patch("/{cv_id}", summary="Update CV metadata")
async def update_cv(
    cv_id: uuid.UUID,
    body: UpdateCvRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await cv_service.update_cv(
        session,
        principal=auth.principal,
        cv_id=cv_id,
        payload=body.model_dump(exclude_unset=True),
        ctx=auth.ctx,
    )
    return success(data)


@cvs_router.delete(
    "/{cv_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a CV (owner only, soft-delete)",
)
async def delete_cv(
    cv_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    await cv_service.delete_cv(session, principal=auth.principal, cv_id=cv_id, ctx=auth.ctx)


@cvs_router.get("/{cv_id}/versions", summary="List a CV's version history (owner only)")
async def list_cv_versions(
    cv_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    items = await cv_service.list_versions(session, principal=auth.principal, cv_id=cv_id)
    return success(items)


@cvs_router.post(
    "/{cv_id}/sections",
    status_code=status.HTTP_201_CREATED,
    summary="Add a new CV section (versioned)",
)
async def create_section(
    cv_id: uuid.UUID,
    body: CreateSectionRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await cv_section_service.create_section(
        session,
        principal=auth.principal,
        cv_id=cv_id,
        payload=body.model_dump(exclude_unset=True),
        ctx=auth.ctx,
    )
    return success(data)


@cvs_router.post(
    "/{cv_id}/versions/{version_id}/restore",
    summary="Restore a prior CV version (creates a new version)",
)
async def restore_cv_version(
    cv_id: uuid.UUID,
    version_id: uuid.UUID,
    body: RestoreVersionRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await cv_section_service.restore_version(
        session,
        principal=auth.principal,
        cv_id=cv_id,
        version_id=version_id,
        payload=body.model_dump(exclude_unset=True),
        ctx=auth.ctx,
    )
    return success(data)


@cvs_router.patch("/{cv_id}/sections/{section_id}", summary="Upsert a CV section (versioned)")
async def upsert_section(
    cv_id: uuid.UUID,
    section_id: uuid.UUID,
    body: SectionUpsertRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await cv_section_service.upsert_section(
        session,
        principal=auth.principal,
        cv_id=cv_id,
        section_id=section_id,
        payload=body.model_dump(exclude_unset=True),
        ctx=auth.ctx,
    )
    return success(data)


@cvs_router.patch(
    "/{cv_id}/canvas", summary="Update CV canvas layout (blocks/page; versioned, non-destructive)"
)
async def update_cv_canvas(
    cv_id: uuid.UUID,
    body: UpdateCvCanvasRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await cv_canvas_service.update_canvas(
        session,
        principal=auth.principal,
        cv_id=cv_id,
        payload=body.model_dump(exclude_unset=True, mode="json"),
        ctx=auth.ctx,
    )
    return success(data)


@cvs_router.patch(
    "/{cv_id}/photo", summary="Replace/crop the CV profile photo, or remove it (no file)"
)
async def update_cv_photo(
    cv_id: uuid.UUID,
    file: UploadFile | None = File(default=None),
    crop_x: float | None = Form(default=None),
    crop_y: float | None = Form(default=None),
    crop_width: float | None = Form(default=None),
    crop_height: float | None = Form(default=None),
    shape: str | None = Form(default=None),
    expected_version: int | None = Form(default=None),
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    if file is None:
        data = await cv_photo_service.remove_photo(
            session,
            principal=auth.principal,
            cv_id=cv_id,
            expected_version=expected_version,
            ctx=auth.ctx,
        )
        return success(data)

    settings = get_settings()
    raw = await file.read()
    if len(raw) > settings.max_upload_bytes:
        raise ValidationFailedError(
            "Tệp quá lớn. Hãy nén hoặc chọn ảnh nhỏ hơn.",
            details={"reason": "file_too_large"},
        )
    crop = None
    if any(v is not None for v in (crop_x, crop_y, crop_width, crop_height)):
        crop = {
            "x": crop_x if crop_x is not None else 0,
            "y": crop_y if crop_y is not None else 0,
            "width": crop_width if crop_width is not None else 1,
            "height": crop_height if crop_height is not None else 1,
        }
    data = await cv_photo_service.update_photo(
        session,
        principal=auth.principal,
        cv_id=cv_id,
        data=raw,
        content_type=file.content_type,
        filename=file.filename or "photo",
        crop=crop,
        shape=shape,
        expected_version=expected_version,
        ctx=auth.ctx,
    )
    return success(data)


@cvs_router.post(
    "/{cv_id}/duplicate",
    status_code=status.HTTP_201_CREATED,
    summary="Duplicate a CV (never mutates the source)",
)
async def duplicate_cv(
    cv_id: uuid.UUID,
    body: DuplicateCvRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await cv_creation_service.duplicate_cv(
        session,
        principal=auth.principal,
        cv_id=cv_id,
        payload=body.model_dump(),
        ctx=auth.ctx,
    )
    return success(data)


@cvs_router.post("/{cv_id}/finalize", summary="Commit a draft CV into the library (draft -> ready)")
async def finalize_cv(
    cv_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await cv_lifecycle_service.finalize_cv(
        session,
        principal=auth.principal,
        cv_id=cv_id,
        ctx=auth.ctx,
    )
    return success(data)


# --------------------------------------------------------------------------- #
# AI suggestions (write-pending diffs; accept creates a new version)          #
# --------------------------------------------------------------------------- #


@cvs_router.post(
    "/{cv_id}/ai-edit-command",
    status_code=status.HTTP_201_CREATED,
    summary="Natural-language AI CV edit (pending diff; never mutates the CV)",
)
async def request_ai_edit_command(
    cv_id: uuid.UUID,
    body: AiEditCommandRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await cv_ai_service.request_edit_command(
        session,
        principal=auth.principal,
        cv_id=cv_id,
        payload=body.model_dump(mode="json"),
        ctx=auth.ctx,
    )
    return success(data)


@cvs_router.post(
    "/{cv_id}/ai-suggestions",
    status_code=status.HTTP_201_CREATED,
    summary="Request an AI CV suggestion (pending diff, no mutation)",
)
async def request_ai_suggestion(
    cv_id: uuid.UUID,
    body: AiSuggestionRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await cv_ai_service.request_suggestion(
        session,
        principal=auth.principal,
        cv_id=cv_id,
        payload=body.model_dump(mode="json"),
        ctx=auth.ctx,
    )
    return success(data)


@cvs_router.get(
    "/{cv_id}/ai-suggestions/{suggestion_id}",
    summary="Get the current status and diff of an AI suggestion (owner-only)",
)
async def get_ai_suggestion(
    cv_id: uuid.UUID,
    suggestion_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await cv_ai_service.get_suggestion(
        session,
        principal=auth.principal,
        cv_id=cv_id,
        suggestion_id=suggestion_id,
    )
    return success(data)


@cvs_router.post(
    "/{cv_id}/ai-suggestions/{suggestion_id}/accept",
    summary="Accept an AI suggestion (requires confirmation; new version)",
)
async def accept_ai_suggestion(
    cv_id: uuid.UUID,
    suggestion_id: uuid.UUID,
    body: AcceptAiSuggestionRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await cv_ai_service.accept_suggestion(
        session,
        principal=auth.principal,
        cv_id=cv_id,
        suggestion_id=suggestion_id,
        payload=body.model_dump(mode="json"),
        ctx=auth.ctx,
    )
    return success(data)


@cvs_router.post(
    "/{cv_id}/ai-suggestions/{suggestion_id}/reject", summary="Reject a pending AI suggestion"
)
async def reject_ai_suggestion(
    cv_id: uuid.UUID,
    suggestion_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await cv_ai_service.reject_suggestion(
        session,
        principal=auth.principal,
        cv_id=cv_id,
        suggestion_id=suggestion_id,
        ctx=auth.ctx,
    )
    return success(data)


# --------------------------------------------------------------------------- #
# Export                                                                      #
# --------------------------------------------------------------------------- #


@cvs_router.post("/{cv_id}/export", summary="Export a CV version to PDF")
async def export_cv(
    cv_id: uuid.UUID,
    body: ExportCvRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await export_service.create_export(
        session,
        principal=auth.principal,
        cv_id=cv_id,
        version_id=body.version_id,
        export_format=body.format,
        idempotency_key=body.idempotency_key,
        ctx=auth.ctx,
    )
    return success(data)


@exports_router.get("/{export_id}", summary="Get export status + signed download URL")
async def get_export(
    export_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await export_service.get_export(session, principal=auth.principal, export_id=export_id)
    return success(data)


# --------------------------------------------------------------------------- #
# Signed file download (token-authorized, no session)                         #
# --------------------------------------------------------------------------- #


def _content_disposition(disposition: str, filename: str) -> str:
    """Build a header-injection-safe ``Content-Disposition`` value.

    Strips CR/LF/control chars + quotes/backslash from the name (header-injection
    guard) and adds an RFC 5987 ``filename*`` for non-ASCII names so a Vietnamese
    CV name survives without breaking the header.
    """

    from urllib.parse import quote

    safe = "".join(
        ch for ch in (filename or "") if ord(ch) >= 0x20 and ord(ch) != 0x7F and ch not in '"\\'
    ).strip()
    if not safe:
        safe = "cv"
    ascii_name = safe.encode("ascii", "ignore").decode("ascii").strip() or "cv"
    encoded = quote(safe, safe="")
    return f"{disposition}; filename=\"{ascii_name}\"; filename*=UTF-8''{encoded}"


def _cv_file_security_headers(disposition: str, filename: str) -> dict[str, str]:
    """Stored-XSS-safe response headers for the signed file-serve path.

    - ``X-Content-Type-Options: nosniff`` — the browser must not MIME-sniff a
      served PDF into HTML.
    - ``Content-Security-Policy: sandbox …`` — the KEY control: the served
      document runs in a maximally-restrictive sandbox (no script execution),
      neutralizing any hostile CV even when embedded in the recruiter's iframe.
      Works cross-origin (the file is served from the API origin, the FE embeds
      it from a different origin), so ``frame-ancestors`` (NOT ``X-Frame-Options``,
      which would block the legitimate cross-origin iframe) restricts WHO may
      frame it to the app's own FE origins.
    """

    settings = get_settings()
    frame_ancestors = ["'self'", settings.frontend_url.rstrip("/")]
    for origin in settings.cors_origins_list:
        origin = origin.strip().rstrip("/")
        if origin and origin != "*" and origin not in frame_ancestors:
            frame_ancestors.append(origin)
    csp = "sandbox; frame-ancestors " + " ".join(frame_ancestors)
    return {
        "Content-Disposition": _content_disposition(disposition, filename),
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": csp,
        "Referrer-Policy": "no-referrer",
    }


@files_router.get("/{token}", summary="Download a file via a signed token")
async def download_file(
    token: str,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    ctx: RequestContext = Depends(get_request_context),
) -> Response:
    result = await download_service.resolve_download(session, token=token, ctx=ctx)
    # ``inline`` lets the FE embed an ALLOWLISTED (PDF/PNG/JPEG/WebP) CV in an
    # <iframe>/PDF viewer; anything else was force-downgraded to ``attachment`` +
    # octet-stream by ``resolve_download``. Every response is sandboxed + nosniff.
    return Response(
        content=result.content,
        media_type=result.media_type,
        headers=_cv_file_security_headers(result.disposition, result.filename),
    )


router.include_router(cvs_router)
router.include_router(templates_router)
router.include_router(admin_templates_router)
router.include_router(exports_router)
router.include_router(files_router)
router.include_router(uploads_router)
router.include_router(ingestions_router)
