"""CV export service: render a CV version to PDF and serve it via a signed URL.

Rendering is deterministic and pure-Python (``infrastructure.pdf_render``). The
job is created, then executed inline in local mode (the same call is later wrapped
by an idempotent Celery task behind ``app.core.worker`` without changing callers).

Downloads are authorized by a short-lived HMAC signed token that references the
export id (never a storage path). The student's own download is unwatermarked
(``docs/SECURITY_PRIVACY.md``).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.analytics.application import ingestion_service as analytics
from app.modules.auth.application.context import RequestContext
from app.modules.documents.api import presenters
from app.modules.documents.application import _shared
from app.modules.documents.domain.models import CvExport, CvProfile, CvVersion
from app.modules.documents.infrastructure import pdf_render, storage
from app.shared.audit import write_audit
from app.shared.exceptions import ResourceNotFoundError, ValidationFailedError
from app.shared.permissions import Principal, permission_checker

_RESOURCE = _shared.RESOURCE


async def _load_owned_cv(
    session: AsyncSession, *, principal: Principal, cv_id: uuid.UUID
) -> CvProfile:
    cv = (
        await session.execute(
            select(CvProfile).where(CvProfile.id == cv_id, CvProfile.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if cv is None or cv.user_id != principal.user_id:
        raise ResourceNotFoundError()
    return cv


async def create_export(
    session: AsyncSession,
    *,
    principal: Principal,
    cv_id: uuid.UUID,
    version_id: uuid.UUID,
    export_format: str,
    idempotency_key: str | None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    permission_checker.require(principal, _RESOURCE, "export")
    assert principal.user_id is not None
    if export_format != "pdf":
        raise ValidationFailedError("Chỉ hỗ trợ xuất PDF trong phiên bản này.")

    cv = await _load_owned_cv(session, principal=principal, cv_id=cv_id)

    version = (
        await session.execute(
            select(CvVersion).where(CvVersion.id == version_id, CvVersion.cv_id == cv.id)
        )
    ).scalar_one_or_none()
    if version is None:
        raise ResourceNotFoundError()

    if idempotency_key:
        prior = (
            await session.execute(
                select(CvExport).where(
                    CvExport.cv_id == cv.id,
                    CvExport.idempotency_key == idempotency_key,
                )
            )
        ).scalar_one_or_none()
        if prior is not None:
            return presenters.export(prior, download_url=None, locale=locale)

    export = CvExport(
        cv_id=cv.id,
        version_id=version.id,
        export_format="pdf",
        status="queued",
        idempotency_key=idempotency_key,
        requested_by=principal.user_id,
    )
    session.add(export)
    await session.flush()

    await write_audit(
        session,
        action="cv.export.requested",
        resource_type="cv_export",
        resource_id=export.id,
        context=_shared.audit_ctx(principal, ctx),
        after={"cv_id": str(cv.id), "version_id": str(version.id)},
    )

    # Inline render (Celery-task seam): produce the PDF and mark ready.
    await _execute_export(session, export=export, version=version, principal=principal, ctx=ctx)

    await session.commit()
    await session.refresh(export)
    # POST returns no download_url (per API_CONTRACTS); fetch via GET when ready.
    return presenters.export(export, download_url=None, locale=locale)


async def _execute_export(
    session: AsyncSession,
    *,
    export: CvExport,
    version: CvVersion,
    principal: Principal,
    ctx: RequestContext,
) -> None:
    """Render + store the PDF for an export. Idempotent: safe to re-run."""

    export.status = "running"
    await session.flush()
    try:
        pdf_bytes = pdf_render.render_cv_pdf(version.snapshot_json, watermark=None)
        key = f"cv-exports/{export.requested_by}/{export.id}.pdf"
        storage.get_storage().save(key, pdf_bytes)
        export.storage_key = key
        export.status = "ready"
        export.completed_at = _shared.now()
    except Exception as exc:  # noqa: BLE001 - record failure, never leak detail
        export.status = "failed"
        export.error_message = type(exc).__name__
        await session.flush()
        await write_audit(
            session,
            action="cv.export.failed",
            resource_type="cv_export",
            resource_id=export.id,
            context=_shared.audit_ctx(principal, ctx),
            after={"reason": "render_failed"},
        )
        await analytics.record_event_safe(
            session,
            event_type="cv.export.failed",
            aggregate_type="cv_export",
            aggregate_id=export.id,
            actor_id=principal.user_id,
            actor_type="student",
            properties={"reason": type(exc).__name__},
        )
        return
    await session.flush()
    await write_audit(
        session,
        action="cv.export.completed",
        resource_type="cv_export",
        resource_id=export.id,
        context=_shared.audit_ctx(principal, ctx),
        after={"status": "ready"},
    )
    await analytics.record_event_safe(
        session,
        event_type="cv.export.completed",
        aggregate_type="cv_export",
        aggregate_id=export.id,
        actor_id=principal.user_id,
        actor_type="student",
    )


async def get_export(
    session: AsyncSession, *, principal: Principal, export_id: uuid.UUID, locale: str = "vi"
) -> dict:
    permission_checker.require(principal, _RESOURCE, "read")
    export = (
        await session.execute(select(CvExport).where(CvExport.id == export_id))
    ).scalar_one_or_none()
    if export is None:
        raise ResourceNotFoundError()
    cv = (
        await session.execute(select(CvProfile).where(CvProfile.id == export.cv_id))
    ).scalar_one_or_none()
    if cv is None or cv.user_id != principal.user_id:
        raise ResourceNotFoundError()

    download_url: str | None = None
    if export.status == "ready" and export.storage_key:
        token = storage.make_signed_token(
            {
                "kind": "export",
                "id": str(export.id),
                "uid": str(principal.user_id),
                "purpose": "download",
                "wm": False,
            }
        )
        base = get_settings().app_url.rstrip("/")
        download_url = f"{base}/api/v1/cv-files/{token}"
    return presenters.export(export, download_url=download_url, locale=locale)
