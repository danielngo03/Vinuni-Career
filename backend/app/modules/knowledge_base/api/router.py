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
    from app.modules.knowledge_base.application import kb_service

    principal = auth.principal
    is_staff = getattr(principal, "is_staff", False) or getattr(principal, "is_superadmin", False)
    if not is_staff:
        if body.scope == "platform":
            raise HTTPException(status_code=403, detail="staff_only")
        if body.scope == "partner" and principal.org_id is None:
            raise HTTPException(status_code=403, detail="partner_required")

    try:
        kb = await kb_service.create_kb(
            session,
            principal=principal,
            name=body.name,
            description=body.description,
            scope=body.scope,
            org_id=body.org_id or principal.org_id,
            job_id=body.job_id,
        )
        await session.commit()
        return kb
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


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
    from app.modules.knowledge_base.application import kb_service

    principal = auth.principal
    is_staff = getattr(principal, "is_staff", False) or getattr(principal, "is_superadmin", False)
    if not is_staff and principal.org_id is None:
        raise HTTPException(status_code=403, detail="upload_not_permitted")

    allowed_mime = {
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "text/plain",
        "text/markdown",
    }
    if file.content_type not in allowed_mime:
        raise HTTPException(status_code=415, detail="unsupported_file_type")

    MAX_BYTES = 20 * 1024 * 1024  # 20 MB
    content = await file.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="file_too_large")

    storage_path = f"kb/{kb_id}/{uuid.uuid4()}/{file.filename}"

    try:
        doc = await kb_service.upload_document(
            session,
            principal=principal,
            kb_id=kb_id,
            title=file.filename or "Untitled",
            file_path=storage_path,
            mime_type=file.content_type,
            file_size_bytes=len(content),
        )
        await session.commit()
        return doc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


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
