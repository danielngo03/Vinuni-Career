"""Knowledge base REST API.

Endpoints:
  Admin/staff:
    POST   /knowledge-bases                             create KB
    GET    /knowledge-bases                             list accessible KBs
    POST   /knowledge-bases/{kb_id}/documents           upload document
    GET    /knowledge-bases/{kb_id}/documents           list documents
    GET    /knowledge-bases/{kb_id}/documents/{doc_id}  document status

  All authenticated users (scope-gated):
    POST   /knowledge-bases/query                       RAG search

Partner-upload and platform-staff upload use the same endpoints; access is
gated by scope inside the service layer (not duplicated in routers).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.modules.auth.api.deps import CurrentAuth, get_current_auth

router = APIRouter(prefix="/knowledge-bases", tags=["knowledge_base"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class CreateKbRequest(BaseModel):
    name: str = Field(..., max_length=200)
    description: str | None = None
    scope: str = Field("platform", pattern="^(platform|partner|job)$")
    org_id: uuid.UUID | None = None
    job_id: uuid.UUID | None = None
    # Partner-scope only: 'internal' (org members) vs 'applicant_facing'.
    # Defaults to 'internal' — the safest choice (never exposed to applicants).
    audience: str = Field("internal", pattern="^(internal|applicant_facing)$")
    department_id: uuid.UUID | None = None


class KbQueryRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=500)
    kb_ids: list[uuid.UUID] | None = None


# ---------------------------------------------------------------------------
# Admin endpoints (create KB, upload docs)
# ---------------------------------------------------------------------------


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_knowledge_base(
    body: CreateKbRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """Create a KB. RBAC (``knowledge_base:manage``) is enforced in the service.

    Platform-scope KBs are platform-superadmin governed here so an ordinary
    partner/university admin (who holds ``*:*`` on THEIR org) cannot seed a
    platform-wide KB. Org-scope create is tenant-checked by the service.
    """
    from app.modules.knowledge_base.application import kb_service

    principal = auth.principal
    if body.scope == "platform" and not principal.is_superadmin:
        raise HTTPException(status_code=403, detail="platform_kb_superadmin_only")

    kb = await kb_service.create_kb(
        session,
        principal=principal,
        name=body.name,
        description=body.description,
        scope=body.scope,
        org_id=body.org_id or principal.org_id,
        job_id=body.job_id,
        audience=body.audience,
        department_id=body.department_id,
        ctx=auth.ctx,
    )
    await session.commit()
    return kb


@router.get("")
async def list_knowledge_bases(
    scope: str | None = None,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
):
    from app.modules.knowledge_base.application import kb_service

    return await kb_service.list_kbs(session, principal=auth.principal, scope=scope)


@router.post("/{kb_id}/documents", status_code=status.HTTP_201_CREATED)
async def upload_document(
    kb_id: uuid.UUID,
    file: UploadFile,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """Upload a KB document. RBAC (``knowledge_base:manage``) enforced in service.

    The bytes are read + validated here (HTTP concern) then PERSISTED to shared
    storage; the returned internal storage key is stored as the document's
    ``file_path`` so async ingestion can actually load and extract it. The key is
    never returned to the client.
    """
    from app.modules.knowledge_base.application import kb_service
    from app.shared.exceptions import ValidationFailedError
    from app.shared.storage import save_bytes

    principal = auth.principal

    allowed_mime = {
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "text/plain",
        "text/markdown",
    }
    if file.content_type not in allowed_mime:
        raise ValidationFailedError(
            "Định dạng tệp không được hỗ trợ. Vui lòng tải lên PDF, Word hoặc tệp văn bản."
        )

    MAX_BYTES = 20 * 1024 * 1024  # 20 MB
    content = await file.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES:
        raise ValidationFailedError("Tệp quá lớn. Kích thước tối đa là 20 MB.")
    if not content:
        raise ValidationFailedError("Tệp rỗng. Vui lòng tải lên tài liệu có nội dung.")

    # Persist bytes BEFORE registering the row: ingestion loads them by key.
    storage_key = save_bytes(
        folder=f"kb/{kb_id}", filename=file.filename or "document", data=content
    )

    try:
        doc = await kb_service.upload_document(
            session,
            principal=principal,
            kb_id=kb_id,
            title=file.filename or "Untitled",
            file_path=storage_key,
            mime_type=file.content_type,
            file_size_bytes=len(content),
            ctx=auth.ctx,
        )
    except ValueError as exc:
        # Unknown KB → clean up the orphaned blob and surface a user-safe 404.
        _safe_delete_blob(storage_key)
        raise HTTPException(status_code=404, detail="knowledge_base_not_found") from exc
    except Exception:
        # Permission denied / duplicate / any other failure: never leave an
        # orphaned blob behind, then let the (user-safe) error propagate.
        _safe_delete_blob(storage_key)
        raise

    await session.commit()
    return doc


def _safe_delete_blob(key: str) -> None:
    try:
        from app.modules.documents.infrastructure.storage import get_storage

        get_storage().delete(key)
    except Exception:  # noqa: BLE001 — best-effort cleanup only
        pass


@router.get("/{kb_id}/documents")
async def list_documents(
    kb_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
):
    from app.modules.knowledge_base.application import kb_service

    return await kb_service.list_documents(session, kb_id=kb_id, principal=auth.principal)


@router.get("/{kb_id}/documents/{doc_id}")
async def get_document(
    kb_id: uuid.UUID,
    doc_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
):
    from app.modules.knowledge_base.application import kb_service

    try:
        return await kb_service.get_document(session, document_id=doc_id, principal=auth.principal)
    except ValueError as err:
        raise HTTPException(status_code=404, detail="document_not_found") from err


@router.delete("/{kb_id}/documents/{doc_id}")
async def delete_document(
    kb_id: uuid.UUID,
    doc_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """Soft-delete a KB document. RBAC (``knowledge_base:manage``) in service."""
    from app.modules.knowledge_base.application import kb_service

    try:
        result = await kb_service.delete_document(
            session, principal=auth.principal, document_id=doc_id, ctx=auth.ctx
        )
    except ValueError as err:
        raise HTTPException(status_code=404, detail="document_not_found") from err
    await session.commit()
    return result


# ---------------------------------------------------------------------------
# RAG query endpoint (all authenticated users, scope-gated in service)
# ---------------------------------------------------------------------------


@router.post("/query")
async def kb_query(
    body: KbQueryRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
):
    from app.ai.safety.input_guard import sanitize_instruction
    from app.modules.knowledge_base.application import kb_service

    safe_query, blocked = sanitize_instruction(body.query)
    if blocked or not safe_query:
        raise HTTPException(status_code=422, detail="query_blocked")

    kb_ids = body.kb_ids or await kb_service.get_kb_ids_for_query(session, principal=auth.principal)
    if not kb_ids:
        return {"found": False, "context": "", "source_count": 0}

    chunks = await kb_service.search_chunks(session, query=safe_query, kb_ids=kb_ids, limit=5)
    context = kb_service.assemble_rag_context(chunks)
    return {
        "found": bool(chunks),
        "context": context,
        "source_count": len(chunks),
    }
