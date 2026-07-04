"""CV upload + deterministic parse service.

Pipeline (``docs/CV_STUDIO_SPEC.md`` §5A, reusing the Phase 0 deterministic
validator + extractor — no LLM here):

1. RBAC (``cv:create``) + idempotency (return the prior run for a repeated key).
2. Validate size/type/security/duplicate -> user-safe ``quality_code``.
3. Persist a ``documents`` row (originals are stored unless security-rejected,
   in which case the bytes are NEVER written to storage).
4. Persist a ``cv_parse_runs`` row; on acceptance, deterministically structure the
   extracted text into ``extracted_data`` + ``review_fields`` (no silent import).
5. Audit + return ``{document_id, parse_run_id, status, next_action}``.

Internal parser details (provider alias, confidence, error text, storage key) are
never returned. ``extracted_data`` / ``review_fields`` are surfaced only by the
owner-only parse-run endpoint.
"""

from __future__ import annotations

import uuid
from pathlib import PurePosixPath

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.extraction import cv_validation
from app.ai.extraction.adapters import resolve_policy
from app.ai.extraction.cv_ingestion_cascade import run_cascade
from app.core.config import get_settings
from app.modules.auth.application.context import RequestContext
from app.modules.documents.api import presenters
from app.modules.documents.application import _shared
from app.modules.documents.domain.models import CvParseRun, Document
from app.modules.documents.infrastructure import storage
from app.shared.audit import write_audit
from app.shared.exceptions import ResourceNotFoundError
from app.shared.permissions import Principal, permission_checker

_RESOURCE = _shared.RESOURCE

# Hard pre-storage gates -> never store bytes.
_SECURITY_REJECT = "FILE_REJECTED_SECURITY"

# quality_code -> next_action surfaced on the upload response.
_ACCEPTED_NEXT = "review_fields"


def _ext(filename: str) -> str:
    suffix = PurePosixPath(filename).suffix.lower()
    return suffix if len(suffix) <= 10 else ""


async def _existing_checksums(session: AsyncSession, *, user_id: uuid.UUID) -> list[str]:
    rows = (
        await session.execute(
            select(Document.checksum_sha256).where(
                Document.user_id == user_id, Document.deleted_at.is_(None)
            )
        )
    ).scalars().all()
    return list(rows)


async def upload_cv(
    session: AsyncSession,
    *,
    principal: Principal,
    filename: str,
    data: bytes,
    content_type: str | None,
    idempotency_key: str | None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    permission_checker.require(principal, _RESOURCE, "create")
    assert principal.user_id is not None
    settings = get_settings()

    # Idempotency: a repeated key returns the original document + its latest run.
    if idempotency_key:
        prior = (
            await session.execute(
                select(Document).where(
                    Document.user_id == principal.user_id,
                    Document.idempotency_key == idempotency_key,
                )
            )
        ).scalar_one_or_none()
        if prior is not None:
            run = (
                await session.execute(
                    select(CvParseRun)
                    .where(CvParseRun.document_id == prior.id)
                    .order_by(CvParseRun.created_at.desc())
                )
            ).scalars().first()
            return {
                "document_id": str(prior.id),
                "parse_run_id": str(run.id) if run else None,
                "status": run.status if run else "failed",
                "next_action": _ACCEPTED_NEXT if run and run.status == "review_required"
                else "upload_another",
            }

    existing = await _existing_checksums(session, user_id=principal.user_id)
    outcome = run_cascade(
        filename,
        data,
        max_bytes=settings.max_upload_bytes,
        existing_checksums=existing,
        policy=resolve_policy(),
    )

    document_id = uuid.uuid4()
    is_security_reject = outcome.quality_code == _SECURITY_REJECT
    storage_key = ""
    if not is_security_reject:
        storage_key = f"cv-uploads/{principal.user_id}/{document_id}{_ext(filename)}"
        storage.get_storage().save(storage_key, data)

    document = Document(
        id=document_id,
        user_id=principal.user_id,
        doc_type="cv",
        original_name=filename[:500],
        storage_path=storage_key,
        mime_type=(content_type or "application/octet-stream")[:100],
        file_size_bytes=len(data),
        checksum_sha256=outcome.checksum or cv_validation.compute_checksum(data),
        virus_scan_status="infected" if is_security_reject else "clean",
        virus_scan_at=_shared.now(),
        idempotency_key=idempotency_key,
    )
    session.add(document)
    await session.flush()

    run = CvParseRun(
        document_id=document.id,
        status="review_required" if outcome.accepted else "failed",
        quality_code=outcome.quality_code,
        started_at=_shared.now(),
        completed_at=_shared.now(),
    )

    if outcome.accepted:
        run.extracted_data = outcome.extracted_data
        run.review_fields = outcome.review_fields
        run.detected_language = outcome.detected_language
        run.page_count = outcome.page_count
        run.text_length = outcome.text_length

    session.add(run)
    await session.flush()

    await write_audit(
        session, action="cv.uploaded", resource_type="document", resource_id=document.id,
        context=_shared.audit_ctx(principal, ctx),
        after={"quality_code": outcome.quality_code, "status": run.status},
    )
    await session.commit()

    _, _, _recover, actions = cv_validation.copy_for(outcome.quality_code)
    if outcome.accepted:
        next_action = _ACCEPTED_NEXT
    else:
        next_action = actions[0] if actions else "upload_another"
    return {
        "document_id": str(document.id),
        "parse_run_id": str(run.id),
        "status": run.status,
        "next_action": next_action,
    }


async def get_parse_run(
    session: AsyncSession, *, principal: Principal, parse_run_id: uuid.UUID, locale: str = "vi"
) -> dict:
    """Owner-only parse-run status with friendly message + review fields."""

    permission_checker.require(principal, _RESOURCE, "read")
    run = (
        await session.execute(select(CvParseRun).where(CvParseRun.id == parse_run_id))
    ).scalar_one_or_none()
    if run is None:
        raise ResourceNotFoundError()
    document = (
        await session.execute(select(Document).where(Document.id == run.document_id))
    ).scalar_one_or_none()
    # Cross-owner access is indistinguishable from missing -> 404.
    if document is None or document.user_id != principal.user_id:
        raise ResourceNotFoundError()
    return presenters.parse_run(run, locale=locale)
