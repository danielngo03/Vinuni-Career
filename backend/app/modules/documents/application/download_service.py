"""Signed-file download resolution + access audit.

The ``/api/v1/cv-files/{token}`` endpoint is authorized by the signed token itself
(a short-lived bearer capability), not by a session. This module verifies the
token, resolves the referenced resource (export or snapshot), loads/render the
bytes, writes a ``signed_file_accesses`` audit row, and returns the payload.

Storage paths never appear in the token or the response; watermark is applied at
render time for partner snapshot access.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.application.context import RequestContext
from app.modules.documents.domain.models import (
    ApplicationCvSnapshot,
    CvExport,
    Document,
    SignedFileAccess,
)
from app.modules.documents.infrastructure import pdf_render, storage
from app.shared.exceptions import ResourceNotFoundError
from app.shared.hashing import hash_ip


class InvalidDownloadTokenError(ResourceNotFoundError):
    """A signed download token is missing, tampered, or expired.

    Surfaced as ``404`` so a bad token is indistinguishable from a missing file.
    """


@dataclass(slots=True)
class DownloadResult:
    content: bytes
    media_type: str
    filename: str


async def resolve_download(
    session: AsyncSession, *, token: str, ctx: RequestContext
) -> DownloadResult:
    try:
        payload = storage.verify_signed_token(token)
    except storage.SignedTokenError as exc:
        raise InvalidDownloadTokenError() from exc

    kind = payload.get("kind")
    resource_id = payload.get("id")
    accessor_raw = payload.get("uid")
    wm = payload.get("wm")
    watermark = wm if isinstance(wm, str) and wm else None
    if not resource_id or not accessor_raw:
        raise InvalidDownloadTokenError()
    resource_uuid = uuid.UUID(str(resource_id))
    accessor_id = uuid.UUID(str(accessor_raw))

    media_type = "application/pdf"
    filename = "cv.pdf"
    if kind == "export":
        content, document_id = await _export_bytes(session, export_id=resource_uuid)
    elif kind == "snapshot":
        content, document_id = await _snapshot_bytes(
            session, snapshot_id=resource_uuid, watermark=watermark
        )
    elif kind == "document":
        # Original uploaded-file preview (owner-scoped via the token ``uid``).
        content, media_type, filename = await _document_bytes(
            session, document_id=resource_uuid, accessor_id=accessor_id
        )
        document_id = resource_uuid
    else:
        raise InvalidDownloadTokenError()

    session.add(
        SignedFileAccess(
            resource_kind=str(kind),
            resource_id=resource_uuid,
            document_id=document_id,
            accessor_id=accessor_id,
            purpose=str(payload.get("purpose") or "download"),
            has_watermark=watermark is not None,
            watermark_text=watermark,
            signed_url_hash=storage.token_hash(token),
            ip_hash=hash_ip(ctx.ip),
        )
    )
    await session.commit()
    return DownloadResult(content=content, media_type=media_type, filename=filename)


async def _document_bytes(
    session: AsyncSession, *, document_id: uuid.UUID, accessor_id: uuid.UUID
) -> tuple[bytes, str, str]:
    document = (
        await session.execute(
            select(Document).where(Document.id == document_id, Document.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    # Preview is owner-scoped: the token's ``uid`` must own the document, and a
    # security-rejected file (no stored bytes) is treated as missing.
    if document is None or document.user_id != accessor_id or not document.storage_path:
        raise InvalidDownloadTokenError()
    try:
        content = storage.get_storage().load(document.storage_path)
    except storage.StorageError as exc:
        raise InvalidDownloadTokenError() from exc
    media_type = document.mime_type or "application/octet-stream"
    return content, media_type, document.original_name or "upload"


async def _export_bytes(
    session: AsyncSession, *, export_id: uuid.UUID
) -> tuple[bytes, uuid.UUID | None]:
    export = (
        await session.execute(select(CvExport).where(CvExport.id == export_id))
    ).scalar_one_or_none()
    if export is None or export.status != "ready" or not export.storage_key:
        raise InvalidDownloadTokenError()
    try:
        content = storage.get_storage().load(export.storage_key)
    except storage.StorageError as exc:
        raise InvalidDownloadTokenError() from exc
    return content, export.document_id


async def _snapshot_bytes(
    session: AsyncSession, *, snapshot_id: uuid.UUID, watermark: str | None
) -> tuple[bytes, uuid.UUID | None]:
    snap = (
        await session.execute(
            select(ApplicationCvSnapshot).where(ApplicationCvSnapshot.id == snapshot_id)
        )
    ).scalar_one_or_none()
    if snap is None:
        raise InvalidDownloadTokenError()
    # Snapshots are immutable; render the stored snapshot JSON (watermarked for partners).
    content = pdf_render.render_cv_pdf(snap.snapshot_json or {}, watermark=watermark)
    return content, snap.uploaded_document_id
