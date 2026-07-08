"""Knowledge base application service — CRUD and ingestion lifecycle.

The KB module provides document ingestion (chunking + embedding) and retrieval
(hybrid BM25 + pgvector) for the AI assistant's ``knowledge_base_query`` tool.

Architecture:
- Platform KB (scope="platform"): staff upload, all authenticated users can query.
- Partner KB (scope="partner"): partner staff upload, applicants to that org can query.
- Per-job KB (scope="job"): partner staff upload, applicants to that job can query
  while their application is active (revoked on REJECTED/WITHDRAWN).

Chunk embedding and BM25 index population are async Celery tasks — this service
only manages the synchronous lifecycle state and triggers the async worker.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.knowledge_base.domain.models import (
    DOC_STATUS_PENDING,
    KB_AUDIENCE_APPLICANT_FACING,
    KB_AUDIENCE_INTERNAL,
    KB_AUDIENCES,
    KB_SCOPE_JOB,
    KB_SCOPE_PARTNER,
    KB_SCOPE_PLATFORM,
    KnowledgeBase,
    KnowledgeBaseDocument,
)
from app.shared.audit import AuditContext, write_audit
from app.shared.exceptions import ConflictError, ValidationFailedError
from app.shared.permissions import Principal, permission_checker

if TYPE_CHECKING:
    # Lightweight request-scoped client context (raw ip / user-agent). Imported
    # for typing only — ``write_audit`` hashes ip/ua before persistence, so no
    # runtime coupling to the auth module is introduced here.
    from app.modules.auth.application.context import RequestContext

# Grantable capability that gates create / upload / delete of a KB + its docs.
KB_RESOURCE = "knowledge_base"
KB_ACTION_MANAGE = "manage"


def _audit_ctx(principal: Principal, ctx: RequestContext | None) -> AuditContext:
    """Build the audit context for a KB write from the actor principal.

    ``actor_org_id`` is stamped so an org can page its own KB-management trail via
    the org audit read model. ``ip``/``user_agent`` are optional and hashed by
    ``write_audit`` (raw values are never persisted).
    """

    return AuditContext(
        actor_id=principal.user_id,
        actor_org_id=principal.org_id,
        ip=ctx.ip if ctx is not None else None,
        user_agent=ctx.user_agent if ctx is not None else None,
    )

# ---------------------------------------------------------------------------
# Access control
# ---------------------------------------------------------------------------


async def _can_query_kb(
    session: AsyncSession,
    *,
    kb: KnowledgeBase,
    principal: Principal,
) -> bool:
    """Return True when the principal has read access to this KB scope.

    Isolation model (partner scope, owner decision 2026-07-08):
    - ``applicant_facing``: org members OR students with an ACTIVE application to
      the org (access revoked on REJECTED/WITHDRAWN).
    - ``internal``: org members ONLY (never applicants). When the KB is
      department-scoped, only members of that department (or an org KB manager)
      may read it.
    """
    if not principal.is_authenticated:
        return False
    if principal.is_superadmin:
        return True

    if kb.scope == KB_SCOPE_PLATFORM:
        return True

    if kb.scope == KB_SCOPE_PARTNER:
        return await _can_query_partner_kb(session, kb=kb, principal=principal)

    if kb.scope == KB_SCOPE_JOB:
        return await _has_active_application_to_job(
            session, user_id=principal.user_id, job_id=kb.job_id
        )

    return False


async def _can_query_partner_kb(
    session: AsyncSession, *, kb: KnowledgeBase, principal: Principal
) -> bool:
    audience = kb.audience or KB_AUDIENCE_INTERNAL
    is_org_member = principal.org_id is not None and str(principal.org_id) == str(kb.org_id)

    if audience == KB_AUDIENCE_APPLICANT_FACING:
        if is_org_member:
            return True
        return await _has_active_application_to_org(
            session, user_id=principal.user_id, org_id=kb.org_id
        )

    # audience == internal: org members only — NO applicant branch.
    if not is_org_member:
        return False
    # An org KB manager (Partner Admin holds ``*:*``) reads every internal KB.
    if permission_checker.can(
        principal, KB_RESOURCE, KB_ACTION_MANAGE, resource_org_id=kb.org_id
    ):
        return True
    # Whole-org internal KB: any active member may read it.
    if kb.department_id is None:
        return True
    # Department-scoped internal KB: only members of that department.
    return await _is_member_of_department(
        session,
        user_id=principal.user_id,
        org_id=kb.org_id,
        department_id=kb.department_id,
    )


async def _has_active_application_to_org(
    session: AsyncSession, *, user_id: uuid.UUID | None, org_id: uuid.UUID | None
) -> bool:
    """Active-application check via the recruitment read-model facade (no raw SQL)."""
    try:
        from app.modules.recruitment.application import application_access_facade

        return await application_access_facade.has_active_application_to_org(
            session, user_id=user_id, org_id=org_id
        )
    except Exception:  # noqa: BLE001 — a lookup failure must never grant access
        return False


async def _has_active_application_to_job(
    session: AsyncSession, *, user_id: uuid.UUID | None, job_id: uuid.UUID | None
) -> bool:
    try:
        from app.modules.recruitment.application import application_access_facade

        return await application_access_facade.has_active_application_to_job(
            session, user_id=user_id, job_id=job_id
        )
    except Exception:  # noqa: BLE001
        return False


async def _is_member_of_department(
    session: AsyncSession,
    *,
    user_id: uuid.UUID | None,
    org_id: uuid.UUID | None,
    department_id: uuid.UUID | None,
) -> bool:
    """True if ``user_id`` belongs to ``department_id`` within ``org_id``.

    Uses the organization read-model facade (no ``MembershipDepartment`` import).
    """
    if user_id is None or org_id is None or department_id is None:
        return False
    try:
        from app.modules.organization.application import org_reporting_facade

        dept_ids = await org_reporting_facade.department_ids_for_user_in_org(
            session, org_id=org_id, user_id=user_id
        )
        return department_id in dept_ids
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------------------
# KB CRUD
# ---------------------------------------------------------------------------


async def create_kb(
    session: AsyncSession,
    *,
    principal: Principal,
    name: str,
    description: str | None = None,
    scope: str = KB_SCOPE_PLATFORM,
    org_id: uuid.UUID | None = None,
    job_id: uuid.UUID | None = None,
    audience: str = KB_AUDIENCE_INTERNAL,
    department_id: uuid.UUID | None = None,
    ctx: RequestContext | None = None,
) -> dict:
    """Create a new knowledge base.

    RBAC: requires the ``knowledge_base:manage`` capability (Partner Admin holds
    ``*:*``; platform superadmin bypasses). Enforced at the service layer — not
    only in the router. ``audience``/``department_id`` apply to partner-scoped KBs.
    """
    # Platform KBs are org-agnostic (resource_org_id=None); org KBs are tenant-scoped.
    permission_checker.require(
        principal, KB_RESOURCE, KB_ACTION_MANAGE, resource_org_id=org_id
    )

    if audience not in KB_AUDIENCES:
        raise ValidationFailedError("Invalid knowledge base audience.")
    # Department scoping only makes sense for an org-scoped internal KB.
    if department_id is not None:
        if scope != KB_SCOPE_PARTNER or org_id is None:
            raise ValidationFailedError(
                "Department scoping requires a partner (organization) knowledge base."
            )
        from app.modules.organization.application import org_reporting_facade

        if not await org_reporting_facade.department_in_org(
            session, org_id=org_id, department_id=department_id
        ):
            raise ValidationFailedError("Department does not belong to this organization.")

    kb = KnowledgeBase(
        id=uuid.uuid4(),
        name=name,
        description=description,
        scope=scope,
        org_id=org_id,
        job_id=job_id,
        audience=audience,
        department_id=department_id,
        created_by=principal.user_id,
        created_at=datetime.now(UTC),
    )
    session.add(kb)
    await session.flush()

    # Audit the write in the caller's transaction (commits atomically with the KB
    # row). Metadata only: scope/audience/department/name — never file content.
    await write_audit(
        session,
        action="knowledge_base.create",
        resource_type="knowledge_base",
        resource_id=kb.id,
        context=_audit_ctx(principal, ctx),
        after={
            "scope": kb.scope,
            "audience": kb.audience,
            "org_id": str(kb.org_id) if kb.org_id else None,
            "department_id": str(kb.department_id) if kb.department_id else None,
            "name": kb.name,
        },
    )
    return _serialize_kb(kb)


async def list_kbs(
    session: AsyncSession,
    *,
    principal: Principal,
    scope: str | None = None,
    org_id: uuid.UUID | None = None,
) -> list[dict]:
    """List knowledge bases the principal can see."""
    stmt = select(KnowledgeBase).where(KnowledgeBase.is_active.is_(True))
    if scope:
        stmt = stmt.where(KnowledgeBase.scope == scope)
    if org_id:
        stmt = stmt.where(KnowledgeBase.org_id == org_id)
    rows = (await session.execute(stmt)).scalars().all()
    accessible = [kb for kb in rows if await _can_query_kb(session, kb=kb, principal=principal)]
    return [_serialize_kb(kb) for kb in accessible]


async def get_kb_ids_for_query(
    session: AsyncSession,
    *,
    principal: Principal,
) -> list[uuid.UUID]:
    """Return all KB IDs accessible to the principal for a RAG query.

    Used by the ``knowledge_base_query`` tool to build the scope filter.
    Cross-KB leakage is prevented downstream by filtering every chunk query
    on ``kb_id = ANY(:kb_ids)`` before returning results.
    """
    rows = (
        await session.execute(
            select(KnowledgeBase)
            .where(KnowledgeBase.is_active.is_(True))
            .order_by(KnowledgeBase.scope)
        )
    ).scalars().all()
    result: list[uuid.UUID] = []
    for kb in rows:
        if await _can_query_kb(session, kb=kb, principal=principal):
            result.append(kb.id)
    return result


# ---------------------------------------------------------------------------
# Document lifecycle
# ---------------------------------------------------------------------------


async def upload_document(
    session: AsyncSession,
    *,
    principal: Principal,
    kb_id: uuid.UUID,
    title: str,
    file_path: str,
    mime_type: str | None = None,
    file_size_bytes: int | None = None,
    page_count: int | None = None,
    chunking_mode: str = "auto",
    ctx: RequestContext | None = None,
) -> dict:
    """Register a document upload and kick off the ingest Celery task.

    RBAC: ``knowledge_base:manage`` on the KB's org (Partner Admin ``*:*`` /
    superadmin bypass). The check runs against the KB's real ``org_id`` so a
    member of org A can never seed documents into org B's KB.
    """
    kb = (
        await session.execute(select(KnowledgeBase).where(KnowledgeBase.id == kb_id))
    ).scalar_one_or_none()
    if kb is None:
        raise ValueError("knowledge_base_not_found")

    permission_checker.require(
        principal, KB_RESOURCE, KB_ACTION_MANAGE, resource_org_id=kb.org_id
    )

    # Duplicate guard: same title + size already live in this KB (heuristic, no
    # content hash column). Prevents accidental double-uploads; the caller gets a
    # user-safe conflict rather than a silently duplicated document.
    if file_size_bytes is not None:
        dup = (
            await session.execute(
                select(KnowledgeBaseDocument.id).where(
                    KnowledgeBaseDocument.kb_id == kb_id,
                    KnowledgeBaseDocument.title == title,
                    KnowledgeBaseDocument.file_size_bytes == file_size_bytes,
                    KnowledgeBaseDocument.is_deleted.is_(False),
                ).limit(1)
            )
        ).first()
        if dup is not None:
            raise ConflictError("Tài liệu này đã có trong cơ sở kiến thức.")

    doc = KnowledgeBaseDocument(
        id=uuid.uuid4(),
        kb_id=kb_id,
        title=title,
        file_path=file_path,
        mime_type=mime_type,
        file_size_bytes=file_size_bytes,
        page_count=page_count,
        chunking_mode=chunking_mode,
        status=DOC_STATUS_PENDING,
        uploaded_by=principal.user_id,
        uploaded_at=datetime.now(UTC),
    )
    session.add(doc)
    await session.flush()
    result = _serialize_document(doc)

    # Audit the upload in the same transaction as the document row. Metadata only:
    # filename/mime/size/page-count + KB scope — NEVER the storage key (file_path)
    # or raw bytes/content.
    await write_audit(
        session,
        action="knowledge_base.document.upload",
        resource_type="knowledge_base_document",
        resource_id=doc.id,
        context=_audit_ctx(principal, ctx),
        after={
            "kb_id": str(kb_id),
            "kb_scope": kb.scope,
            "kb_audience": kb.audience,
            "department_id": str(kb.department_id) if kb.department_id else None,
            "filename": title,
            "mime_type": mime_type,
            "file_size_bytes": file_size_bytes,
            "page_count": page_count,
        },
    )

    # Persist the PENDING document before scheduling ingestion: the ingest task
    # runs in its own session and must be able to load it (commit → enqueue,
    # mirroring documents.ingestion_service.start_ingestion). Under inline mode
    # the handler runs here and flips the row to DONE/FAILED.
    await session.commit()
    from app.modules.knowledge_base.application.ingest_task import enqueue_ingest

    await enqueue_ingest(str(doc.id))

    return result


async def get_document(
    session: AsyncSession,
    *,
    document_id: uuid.UUID,
    principal: Principal,
) -> dict:
    doc = (
        await session.execute(
            select(KnowledgeBaseDocument)
            .where(
                KnowledgeBaseDocument.id == document_id,
                KnowledgeBaseDocument.is_deleted.is_(False),
            )
        )
    ).scalar_one_or_none()
    if doc is None:
        raise ValueError("document_not_found")
    return _serialize_document(doc)


async def list_documents(
    session: AsyncSession,
    *,
    kb_id: uuid.UUID,
    principal: Principal,
) -> list[dict]:
    rows = (
        await session.execute(
            select(KnowledgeBaseDocument)
            .where(
                KnowledgeBaseDocument.kb_id == kb_id,
                KnowledgeBaseDocument.is_deleted.is_(False),
            )
            .order_by(KnowledgeBaseDocument.uploaded_at.desc())
        )
    ).scalars().all()
    return [_serialize_document(d) for d in rows]


async def delete_document(
    session: AsyncSession,
    *,
    principal: Principal,
    document_id: uuid.UUID,
    ctx: RequestContext | None = None,
) -> dict:
    """Soft-delete a KB document and its chunks.

    RBAC: ``knowledge_base:manage`` on the owning KB's org. Idempotent — deleting
    an already-deleted doc returns the same user-safe payload. Chunks are marked
    deleted so retrieval never surfaces content from a removed document.
    """
    from sqlalchemy import update

    doc = (
        await session.execute(
            select(KnowledgeBaseDocument).where(KnowledgeBaseDocument.id == document_id)
        )
    ).scalar_one_or_none()
    if doc is None:
        raise ValueError("document_not_found")

    kb = (
        await session.execute(select(KnowledgeBase).where(KnowledgeBase.id == doc.kb_id))
    ).scalar_one_or_none()
    permission_checker.require(
        principal,
        KB_RESOURCE,
        KB_ACTION_MANAGE,
        resource_org_id=kb.org_id if kb is not None else None,
    )

    if not doc.is_deleted:
        doc.is_deleted = True
        from app.modules.knowledge_base.domain.models import KnowledgeBaseChunk

        await session.execute(
            update(KnowledgeBaseChunk)
            .where(KnowledgeBaseChunk.document_id == doc.id)
            .values(is_deleted=True)
        )
        await session.flush()

        # Audit only on a real state change: an idempotent re-delete of an already
        # removed document is a no-op and must not spam the trail. Metadata only:
        # filename + KB scope — never the storage key (file_path) or file content.
        await write_audit(
            session,
            action="knowledge_base.document.delete",
            resource_type="knowledge_base_document",
            resource_id=doc.id,
            context=_audit_ctx(principal, ctx),
            before={
                "kb_id": str(doc.kb_id),
                "kb_scope": kb.scope if kb is not None else None,
                "kb_audience": kb.audience if kb is not None else None,
                "department_id": (
                    str(kb.department_id) if (kb is not None and kb.department_id) else None
                ),
                "filename": doc.title,
            },
        )
    return {"id": str(doc.id), "deleted": True}


# ---------------------------------------------------------------------------
# Chunk retrieval (called by the AI assistant tool)
# ---------------------------------------------------------------------------


async def search_chunks(
    session: AsyncSession,
    *,
    query: str,
    kb_ids: list[uuid.UUID],
    limit: int = 5,
) -> list[dict]:
    """Retrieve the top-K most relevant chunks from the specified KBs.

    Uses simple text containment fallback when pgvector is unavailable.
    Hybrid search (BM25 + pgvector) is used when the extension is enabled.
    Results are capped at ``limit``; cross-KB leakage is prevented via the
    mandatory ``kb_id = ANY(:kb_ids)`` filter.

    After retrieval, a local lexical reranker (§6.3 tier 2 —
    ``app.ai.retrieval.rerank.rerank_kb_chunks``, free/offline/deterministic)
    re-scores the candidate pool against the full query text and returns the
    top ``limit`` — this sharpens ordering beyond what SQL-side RRF alone
    gives, at zero extra cost or latency.
    """
    if not kb_ids:
        return []

    candidate_limit = max(limit * 3, 15)
    if await _pgvector_extension_ready(session):
        candidates = await _hybrid_kb_search(
            session, query=query, kb_ids=kb_ids, limit=candidate_limit
        )
    else:
        # Text-search fallback: BM25-style ts_rank via postgres full-text
        candidates = await _bm25_kb_search(
            session, query=query, kb_ids=kb_ids, limit=candidate_limit
        )

    return _rerank_chunk_candidates(query, candidates, limit=limit)


def _rerank_chunk_candidates(query: str, candidates: list[dict], *, limit: int) -> list[dict]:
    """Apply the local lexical reranker to a retrieved chunk pool (pure, sync)."""
    if len(candidates) <= 1:
        return candidates[:limit]

    from app.ai.retrieval.rerank import rerank_kb_chunks

    by_id = {c["id"]: c for c in candidates if c.get("id") is not None}
    if not by_id:
        return candidates[:limit]

    docs = {cid: (chunk.get("content") or "") for cid, chunk in by_id.items()}
    ranked = rerank_kb_chunks(query, docs, top_k=limit)
    ordered = [by_id[cid] for cid, _score in ranked if cid in by_id]
    # Append any candidate the reranker dropped (defensive — keeps coverage
    # if a malformed id ever slips through) so results are never silently lost.
    seen_ids = {c["id"] for c in ordered}
    for chunk in candidates:
        if chunk.get("id") not in seen_ids:
            ordered.append(chunk)
        if len(ordered) >= limit:
            break
    return ordered[:limit]


async def _pgvector_extension_ready(session: AsyncSession) -> bool:
    from sqlalchemy import text as sa_text

    from app.core.config import get_settings

    if not getattr(get_settings(), "pgvector_enabled", False):
        return False
    bind = session.get_bind()
    if bind.dialect.name != "postgresql":
        return False
    try:
        row = (
            await session.execute(
                sa_text(
                    "SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') AS ready"
                )
            )
        ).first()
        return bool(row and row.ready)
    except Exception:
        return False


async def _bm25_kb_search(
    session: AsyncSession,
    *,
    query: str,
    kb_ids: list[uuid.UUID],
    limit: int,
) -> list[dict]:
    from sqlalchemy import text as sa_text
    sql = sa_text(
        """
        SELECT id, kb_id, document_id, content, section_heading, chunk_index, token_count
        FROM knowledge_base_chunks
        WHERE kb_id = ANY(:kb_ids)
          AND is_deleted = FALSE
          AND content ILIKE :pattern
        ORDER BY LENGTH(content) DESC
        LIMIT :limit
        """
    )
    rows = (
        await session.execute(
            sql.params(
                kb_ids=[str(kid) for kid in kb_ids],
                pattern=f"%{query[:100]}%",
                limit=limit,
            )
        )
    ).fetchall()
    return [_serialize_chunk_row(r) for r in rows]


async def _hybrid_kb_search(
    session: AsyncSession,
    *,
    query: str,
    kb_ids: list[uuid.UUID],
    limit: int,
) -> list[dict]:
    """Hybrid BM25 + pgvector retrieval fused via RRF (spec §6.2)."""
    from sqlalchemy import text as sa_text

    from app.ai.retrieval.embeddings import embed_single

    try:
        query_vec = await embed_single(query)
        query_vec_json = json.dumps(query_vec)
    except Exception:
        return await _bm25_kb_search(session, query=query, kb_ids=kb_ids, limit=limit)

    sql = sa_text(
        """
        WITH bm25 AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       ORDER BY ts_rank(
                           to_tsvector('simple', content), plainto_tsquery('simple', :query)
                       ) DESC
                   ) AS bm25_rank
            FROM knowledge_base_chunks
            WHERE kb_id = ANY(:kb_ids)
              AND is_deleted = FALSE
              AND to_tsvector('simple', content) @@ plainto_tsquery('simple', :query)
            LIMIT 40
        ),
        dense AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       ORDER BY embedding_json::vector <=> :vec::vector
                   ) AS dense_rank
            FROM knowledge_base_chunks
            WHERE kb_id = ANY(:kb_ids)
              AND is_deleted = FALSE
              AND embedding_json IS NOT NULL
            LIMIT 40
        ),
        rrf AS (
            SELECT COALESCE(b.id, d.id) AS id,
                   (
                       COALESCE(1.0 / (60 + b.bm25_rank), 0)
                       + COALESCE(1.0 / (60 + d.dense_rank), 0)
                   ) AS score
            FROM bm25 b
            FULL OUTER JOIN dense d ON b.id = d.id
        )
        SELECT
            c.id, c.kb_id, c.document_id, c.content, c.section_heading, c.chunk_index,
            c.token_count
        FROM rrf r
        JOIN knowledge_base_chunks c ON c.id = r.id
        ORDER BY r.score DESC
        LIMIT :limit
        """
    )

    try:
        rows = (
            await session.execute(
                sql.params(
                    query=query[:200],
                    kb_ids=[str(kid) for kid in kb_ids],
                    vec=query_vec_json,
                    limit=limit,
                )
            )
        ).fetchall()
        return [_serialize_chunk_row(r) for r in rows]
    except Exception:
        return await _bm25_kb_search(session, query=query, kb_ids=kb_ids, limit=limit)


# ---------------------------------------------------------------------------
# Context assembly for LLM injection (spec §6.4)
# ---------------------------------------------------------------------------

MAX_RAG_CONTEXT_TOKENS = 3000


def assemble_rag_context(chunks: list[dict]) -> str:
    """Format retrieved chunks into the RAG context block for LLM injection.

    Format:
        [DOC: {document_title} | Phần: {section_heading}]
        {content}
        ---

    Budget: MAX_RAG_CONTEXT_TOKENS ≈ 12 000 characters. Chunks are ordered by
    relevance (caller provides pre-ranked list). Truncation is applied to the
    last chunk if needed to fit the budget.
    """
    if not chunks:
        return ""

    budget_chars = MAX_RAG_CONTEXT_TOKENS * 4  # ~4 chars per token
    parts: list[str] = []
    used = 0

    for chunk in chunks:
        heading = chunk.get("section_heading") or ""
        doc_title = chunk.get("document_title") or ""
        content = chunk.get("content") or ""
        header = f"[DOC: {doc_title} | Phần: {heading}]" if (doc_title or heading) else ""
        entry = f"{header}\n{content}\n---".strip()

        if used + len(entry) > budget_chars:
            remaining = budget_chars - used
            if remaining > 200:
                entry = entry[:remaining]
                parts.append(entry)
            break
        parts.append(entry)
        used += len(entry) + 1

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Serialisers
# ---------------------------------------------------------------------------


def _serialize_kb(kb: KnowledgeBase) -> dict:
    return {
        "id": str(kb.id),
        "name": kb.name,
        "description": kb.description,
        "scope": kb.scope,
        "org_id": str(kb.org_id) if kb.org_id else None,
        "job_id": str(kb.job_id) if kb.job_id else None,
        "audience": kb.audience,
        "department_id": str(kb.department_id) if kb.department_id else None,
        "is_active": kb.is_active,
        "created_at": kb.created_at.isoformat(),
    }


def _serialize_document(doc: KnowledgeBaseDocument) -> dict:
    return {
        "id": str(doc.id),
        "kb_id": str(doc.kb_id),
        "title": doc.title,
        "mime_type": doc.mime_type,
        "file_size_bytes": doc.file_size_bytes,
        "page_count": doc.page_count,
        "chunking_mode": doc.chunking_mode,
        "chunk_count": doc.chunk_count,
        "status": doc.status,
        "uploaded_at": doc.uploaded_at.isoformat(),
        "processed_at": doc.processed_at.isoformat() if doc.processed_at else None,
    }


def _serialize_chunk_row(row) -> dict:
    return {
        "id": str(row.id),
        "kb_id": str(row.kb_id),
        "document_id": str(row.document_id),
        "content": row.content,
        "section_heading": row.section_heading or "",
        "chunk_index": row.chunk_index,
        "token_count": row.token_count,
    }
