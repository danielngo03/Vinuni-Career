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
from app.modules.documents.infrastructure import pdf_render, pdf_watermark, storage
from app.shared.exceptions import ResourceNotFoundError
from app.shared.hashing import hash_ip


class InvalidDownloadTokenError(ResourceNotFoundError):
    """A signed download token is missing, tampered, or expired.

    Surfaced as ``404`` so a bad token is indistinguishable from a missing file.
    """


# Stored-XSS hardening (owner/security decision 2026-07-10): a student can upload
# a hostile "CV" (HTML / SVG / a file whose stored ``mime_type`` is spoofed).
# Only these types may EVER be rendered inline in the recruiter's browser; every
# other type is forced to ``attachment`` and served as an opaque octet-stream so
# it cannot execute script in-session. ``text/html`` / ``image/svg+xml`` /
# ``application/xhtml+xml`` are deliberately absent.
_INLINE_ALLOWLIST = frozenset(
    {"application/pdf", "image/png", "image/jpeg", "image/webp"}
)


def _magic_matches(content: bytes, base_media: str) -> bool:
    """Best-effort magic-number check that ``content`` really is ``base_media``.

    Guards against a spoofed ``document.mime_type`` (e.g. an HTML file stored as
    ``application/pdf``). Conservative: unknown/empty content returns False so a
    mismatch downgrades to a safe attachment rather than trusting the label.
    """

    if not content:
        return False
    head = content[:16]
    if base_media == "application/pdf":
        # A leading BOM/whitespace before %PDF is tolerated by viewers.
        return b"%PDF" in content[:1024]
    if base_media == "image/png":
        return head.startswith(b"\x89PNG\r\n\x1a\n")
    if base_media == "image/jpeg":
        return head.startswith(b"\xff\xd8\xff")
    if base_media == "image/webp":
        return head[:4] == b"RIFF" and head[8:12] == b"WEBP"
    return False


def _safe_serving(
    content: bytes, media_type: str, requested_disposition: str
) -> tuple[str, str]:
    """Resolve the (served_media_type, disposition) safe to return to a browser.

    - Inline is allowed ONLY for an allowlisted type whose bytes match its magic
      number. Anything else is forced to ``attachment`` + ``application/octet-stream``
      so a hostile upload can never render/execute inline.
    - An explicit ``attachment`` request is always honoured (never upgraded to
      inline).
    """

    base_media = (media_type or "").split(";")[0].strip().lower()
    # An allowlisted type is only TRUSTED when its bytes match the magic number,
    # so a spoofed ``mime_type`` (HTML stored as ``application/pdf``) can neither be
    # rendered inline NOR served under the claimed content-type.
    trusted = base_media in _INLINE_ALLOWLIST and _magic_matches(content, base_media)
    if requested_disposition == "inline" and trusted:
        return base_media, "inline"
    # Attachment path: keep the real content-type only for a trusted allowlisted
    # type; serve everything else as an opaque octet-stream.
    served_media = base_media if trusted else "application/octet-stream"
    return served_media, "attachment"


@dataclass(slots=True)
class DownloadResult:
    content: bytes
    media_type: str
    filename: str
    # "inline" (embeddable in an <iframe> / PDF viewer) or "attachment" (download).
    # Always resolved through ``_safe_serving`` — never trusted from the token alone.
    disposition: str = "inline"


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
    elif kind == "snapshot_original":
        # Partner CV view/download: serve the STUDENT'S ORIGINAL stored file (the
        # uploaded PDF/image, or the template-CV's rendered PDF) — NOT a
        # watermarked derivative (owner decision 2026-07-10). The token was minted
        # only after the recruitment service verified org ownership + CV-access
        # RBAC, so it is the capability; no owner check here (unlike ``document``).
        content, media_type, filename, document_id = await _snapshot_original_bytes(
            session, snapshot_id=resource_uuid
        )
    elif kind == "document":
        # Original uploaded-file preview (owner-scoped via the token ``uid``).
        content, media_type, filename = await _document_bytes(
            session, document_id=resource_uuid, accessor_id=accessor_id
        )
        document_id = resource_uuid
    else:
        raise InvalidDownloadTokenError()

    # ``disp`` on the token REQUESTS a disposition, but the final decision is made
    # by ``_safe_serving`` against the type allowlist + magic number — a hostile
    # (HTML/SVG/spoofed) upload is force-downgraded to a sandboxed attachment and
    # can never be rendered inline, regardless of the token.
    requested = "attachment" if payload.get("disp") == "attachment" else "inline"
    served_media, disposition = _safe_serving(content, media_type, requested)

    # Partner CV DOWNLOAD is watermarked (owner decision 2026-07-10;
    # ``docs/SECURITY_PRIVACY.md``): the inline VIEW stays the clean original, but
    # the attachment DOWNLOAD of a partner-accessed candidate CV (``snapshot_original``)
    # is stamped with the VinUni logo + "VinUni Career". Guard on a trusted PDF so a
    # spoofed/non-PDF upload (force-downgraded to octet-stream) is left untouched.
    stamped_watermark = watermark
    if (
        kind == "snapshot_original"
        and disposition == "attachment"
        and served_media == "application/pdf"
    ):
        content = pdf_watermark.stamp_watermark(content)
        stamped_watermark = pdf_watermark.WATERMARK_TEXT

    session.add(
        SignedFileAccess(
            resource_kind=str(kind),
            resource_id=resource_uuid,
            document_id=document_id,
            accessor_id=accessor_id,
            purpose=str(payload.get("purpose") or "download"),
            has_watermark=stamped_watermark is not None,
            watermark_text=stamped_watermark,
            signed_url_hash=storage.token_hash(token),
            ip_hash=hash_ip(ctx.ip),
        )
    )
    await session.commit()
    return DownloadResult(
        content=content,
        media_type=served_media,
        filename=filename,
        disposition=disposition,
    )


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


async def _snapshot_original_bytes(
    session: AsyncSession, *, snapshot_id: uuid.UUID
) -> tuple[bytes, str, str, uuid.UUID | None]:
    """Serve the ORIGINAL CV a candidate submitted (owner decision 2026-07-10).

    Two snapshot shapes:

    - Uploaded-CV snapshot (``uploaded_document_id`` set): serve the STUDENT'S
      ORIGINAL uploaded bytes (PDF/image) with their real mime + filename — no
      re-render, no watermark. The recruiter sees exactly what the student
      submitted.
    - Builder-CV snapshot (no uploaded document): there is no stored source file,
      so render the immutable snapshot JSON to a PDF (the template CV's rendered
      PDF) — still WITHOUT a watermark.

    Raises ``InvalidDownloadTokenError`` (→ 404) when the snapshot is missing, has
    been retention-tombstoned, or its original bytes are gone.
    """

    snap = (
        await session.execute(
            select(ApplicationCvSnapshot).where(ApplicationCvSnapshot.id == snapshot_id)
        )
    ).scalar_one_or_none()
    if snap is None:
        raise InvalidDownloadTokenError()
    body = snap.snapshot_json if isinstance(snap.snapshot_json, dict) else {}
    if body.get("_retention_anonymized"):
        # PII scrubbed by the retention sweep — nothing renderable.
        raise InvalidDownloadTokenError()

    if snap.uploaded_document_id is not None:
        document = (
            await session.execute(
                select(Document).where(
                    Document.id == snap.uploaded_document_id, Document.deleted_at.is_(None)
                )
            )
        ).scalar_one_or_none()
        if document is not None and document.storage_path:
            try:
                content = storage.get_storage().load(document.storage_path)
            except storage.StorageError as exc:
                raise InvalidDownloadTokenError() from exc
            media_type = document.mime_type or "application/pdf"
            filename = document.original_name or "cv.pdf"
            return content, media_type, filename, document.id
        # Original bytes gone (security-rejected / purged) — fall through to render.

    # Builder-CV snapshot (or missing upload bytes): render the immutable JSON,
    # unwatermarked. A title suffix keeps a friendly filename.
    content = pdf_render.render_cv_pdf(body, watermark=None)
    raw_title = str(body.get("title") or "cv").strip() or "cv"
    filename = raw_title if raw_title.lower().endswith(".pdf") else f"{raw_title}.pdf"
    return content, "application/pdf", filename, snap.uploaded_document_id
