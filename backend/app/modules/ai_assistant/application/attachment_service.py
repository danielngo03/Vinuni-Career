"""Chat-attachment upload + AI analysis service.

Two use cases behind the ``POST /ai/chat/sessions/{id}/attachments`` endpoint and
the ``analyze_attachment`` assistant tool:

- :func:`upload_attachment` — validate (size/type/security), store the bytes via
  the shared signed blob storage, and create an owner-scoped ``ChatAttachment``
  row (``status=uploaded``). Returns a SAFE descriptor only — never the storage
  key/path, never provider/model internals.
- :func:`analyze_attachment` — load the caller's OWN attachment (owner + org
  scoped), run the cost-tiered analysis cascade OFFLOADED off the event loop,
  cache the structured, leakage-safe result on ``analysis_json``, and meter the
  energy ledger exactly once on a genuine result. Re-analysing a stored result
  returns the cache without re-charging (idempotent).

RBAC: the endpoint requires session ownership; the tool additionally requires the
partner persona (enforced at dispatch). Both paths only ever touch the caller's
own attachment — a cross-user / cross-org attachment id is indistinguishable from
a missing one (404), matching the tenant-isolation convention.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from pathlib import PurePosixPath

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.energy.constants import FEATURE_ATTACHMENT_ANALYSIS
from app.ai.energy.service import build_usage_context, charge_units
from app.ai.extraction import attachment as analysis
from app.ai.extraction import cv_validation
from app.ai.extraction.text_extraction import FileKind, sniff_kind
from app.ai.observability.billable_usage import RESULT_SUCCESS, record_billable_usage
from app.core.config import get_settings
from app.modules.ai_assistant.application.session_history import require_session
from app.modules.ai_assistant.domain.models import ChatAttachment
from app.modules.documents.application import documents_storage_facade as storage
from app.shared.exceptions import AuthRequiredError, ResourceNotFoundError, ValidationFailedError
from app.shared.permissions import Principal

_logger = logging.getLogger("ai.attachment")

# Extensions we accept for chat analysis (in addition to a supported sniffed kind).
# CSV is analysed as text. Spreadsheet/presentation office formats are explicitly
# out of scope for this slice (a zip container would mis-sniff as DOCX).
_ALLOWED_EXTS = frozenset(
    {".pdf", ".png", ".jpg", ".jpeg", ".docx", ".txt", ".csv"}
)
_BLOCKED_EXTS = frozenset({".xlsx", ".xls", ".pptx", ".ppt", ".zip", ".exe"})
_SUPPORTED_KINDS = {FileKind.PDF, FileKind.DOCX, FileKind.TXT, FileKind.IMAGE}

_STATUS_UPLOADED = "uploaded"
_STATUS_ANALYZED = "analyzed"
_STATUS_REJECTED = "rejected"


def _ext(filename: str) -> str:
    suffix = PurePosixPath(filename).suffix.lower()
    return suffix if len(suffix) <= 10 else ""


def _safe_descriptor(row: ChatAttachment) -> dict:
    """Client-safe attachment view — NEVER the storage key/path."""

    return {
        "id": str(row.id),
        "session_id": str(row.session_id),
        "filename": row.filename,
        "content_type": row.content_type,
        "size": row.size_bytes,
        "status": row.status,
        "created_at": row.created_at.isoformat(),
    }


async def upload_attachment(
    session: AsyncSession,
    *,
    principal: Principal,
    session_id: uuid.UUID,
    filename: str,
    data: bytes,
    content_type: str | None,
) -> dict:
    """Validate + store a chat attachment; return a safe descriptor.

    Cheap (no model call) — analysis is a separate, metered tool call. Rejects
    blank / oversized / unsupported / security-failed files with a user-safe 4xx
    and NEVER writes bytes for a security-rejected file.
    """

    if not principal.is_authenticated:
        raise AuthRequiredError()
    # Session ownership: raises ResourceNotFoundError (404) for a non-owned session.
    chat = await require_session(session, principal, session_id)

    settings = get_settings()
    if not data:
        raise ValidationFailedError(
            "Tệp trống hoặc không đọc được. Hãy chọn một tệp khác.",
            details={"reason": "blank_file"},
        )
    if len(data) > settings.max_upload_bytes:
        raise ValidationFailedError(
            "Tệp quá lớn. Hãy nén hoặc chia nhỏ tệp rồi tải lại.",
            details={"reason": "file_too_large"},
        )

    ext = _ext(filename)
    kind = sniff_kind(filename, data)
    if ext in _BLOCKED_EXTS or kind not in _SUPPORTED_KINDS or (ext and ext not in _ALLOWED_EXTS):
        raise ValidationFailedError(
            "Định dạng tệp không được hỗ trợ. Hãy tải lên PDF, ảnh, DOCX, TXT hoặc CSV.",
            details={"reason": "unsupported_file_type"},
        )

    # Security gate BEFORE storing — a rejected file's bytes are never written.
    if cv_validation.security_gate(data, filename) is not None:
        raise ValidationFailedError(
            "Tệp không vượt qua kiểm tra an toàn. Hãy tải lên một tệp sạch.",
            details={"reason": "file_rejected_security"},
        )

    attachment_id = uuid.uuid4()
    storage_key = f"chat-attachments/{principal.user_id}/{attachment_id}{ext}"
    storage.save(storage_key, data)

    row = ChatAttachment(
        id=attachment_id,
        session_id=chat.id,
        user_id=principal.user_id,
        org_id=principal.org_id,
        filename=filename[:500],
        content_type=(content_type or "application/octet-stream")[:100],
        size_bytes=len(data),
        storage_key=storage_key,
        status=_STATUS_UPLOADED,
        created_at=datetime.now(UTC),
        version=1,
    )
    session.add(row)
    await session.flush()
    await session.commit()
    return _safe_descriptor(row)


async def _load_owned(
    session: AsyncSession, *, principal: Principal, attachment_id: uuid.UUID
) -> ChatAttachment:
    """Load the caller's OWN attachment (owner + org scoped) or 404."""

    conds = [
        ChatAttachment.id == attachment_id,
        ChatAttachment.user_id == principal.user_id,
    ]
    # A partner attachment is org-scoped; a cross-org id is indistinguishable from
    # missing. For a principal without an org this is a plain owner check.
    if principal.org_id is not None:
        conds.append(ChatAttachment.org_id == principal.org_id)
    row = (
        await session.execute(select(ChatAttachment).where(*conds))
    ).scalar_one_or_none()
    if row is None:
        raise ResourceNotFoundError()
    return row


async def analyze_attachment(
    session: AsyncSession,
    *,
    principal: Principal,
    attachment_id: uuid.UUID,
) -> dict:
    """Analyse the caller's own attachment; cache + meter the result.

    Returns the leakage-safe analysis dict (``cached`` flags a stored result).
    Charges ``FEATURE_ATTACHMENT_ANALYSIS`` exactly once per genuine analysis
    (idempotent on the attachment id); a re-analysis of a stored result returns
    the cache without charging, and a rejected/blank file is never charged.
    """

    if not principal.is_authenticated:
        raise AuthRequiredError()

    row = await _load_owned(session, principal=principal, attachment_id=attachment_id)

    # Idempotent: a previously analysed attachment returns its cache, no re-charge.
    if row.status == _STATUS_ANALYZED and isinstance(row.analysis_json, dict):
        return {**row.analysis_json, "cached": True}

    try:
        data = storage.load(row.storage_key)
    except Exception:  # noqa: BLE001 — missing/unreadable object → clean failure
        _logger.warning("attachment_bytes_unavailable", exc_info=True)
        return {
            "status": "not_analyzable",
            "kind": "unknown",
            "analyzed": False,
            "degraded": False,
            "summary": "",
            "extracted_text_preview": "",
            "cached": False,
        }

    # Offload the CPU/IO-heavy cascade (PDF raster, PIL, OCR, blocking vision HTTP)
    # off the event loop so it never stalls other requests on this worker.
    outcome = await asyncio.to_thread(
        analysis.analyze_document, row.filename, data, policy=analysis.resolve_policy()
    )
    public = outcome.to_public()

    if outcome.chargeable:
        row.analysis_json = public
        row.status = _STATUS_ANALYZED
        row.version += 1
        await _meter(session, principal=principal, row=row)
    else:
        # Rejected / blank / not-analyzable — store the safe result, never charge.
        row.analysis_json = public
        row.status = _STATUS_REJECTED

    await session.flush()
    return {**public, "cached": False}


async def _meter(
    session: AsyncSession, *, principal: Principal, row: ChatAttachment
) -> None:
    """Debit one ``FEATURE_ATTACHMENT_ANALYSIS`` charge (best-effort, idempotent).

    Scope resolves to the partner ORG pool for a recruiter, the user scope
    otherwise. Idempotent on the attachment id so a retry never double-charges.
    Accounting must never break the tool result, so failures are swallowed.
    """

    try:
        ctx = build_usage_context(
            principal,
            feature_key=FEATURE_ATTACHMENT_ANALYSIS,
            task_type="attachment_analysis",
            session_id=row.session_id,
            resource_type="attachment",
            resource_id=row.id,
            idempotency_parts=(row.id,),
        )
        await record_billable_usage(
            session,
            ctx=ctx,
            result_status=RESULT_SUCCESS,
            base_units=charge_units(FEATURE_ATTACHMENT_ANALYSIS),
        )
    except Exception:  # noqa: BLE001 — accounting must never break the reply
        _logger.warning("attachment_analysis_metering_failed", exc_info=True)


__all__ = ["upload_attachment", "analyze_attachment"]
