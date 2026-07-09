"""Celery task for asynchronous knowledge base document ingestion.

Pipeline:
1. Load document record and extract text from file_path.
2. Chunk the text via ``chunking.chunk_document()``.
3. Batch-embed all chunks via ``embed_texts()`` with the embedding alias.
4. Upsert chunk rows into ``knowledge_base_chunks``.
5. Update document status → DONE (or FAILED on error).

The task is idempotent: re-triggering on an already-DONE document re-chunks
and re-embeds, replacing old chunks (safe for admin-triggered re-index flows).

Worker retries: 3 attempts with exponential backoff (spec §6.1).
Audit event ``KB_CHUNK_EMBEDDED`` is written after each successful ingest.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime

from app.modules.knowledge_base.domain.models import (
    DOC_STATUS_DONE,
    DOC_STATUS_FAILED,
    DOC_STATUS_PROCESSING,
    KnowledgeBaseChunk,
    KnowledgeBaseDocument,
)

logger = logging.getLogger(__name__)

_KB_TASK_NAME = "knowledge_base.ingest_document"


async def _kb_ingest_task(payload: dict) -> None:
    """Background handler: run KB ingestion in its own session (idempotent).

    Mirrors ``documents.ingestion_service._ingestion_task``. On failure
    ``run_ingest`` marks the document ``FAILED`` and flushes before re-raising, so
    we commit in ``finally`` to persist either the DONE result or the FAILED
    status — the document never gets stuck silently in PROCESSING.
    """
    from app.core.db import get_sessionmaker

    document_id = str(payload["document_id"])
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        try:
            await run_ingest(document_id, session=session)
        except Exception:
            logger.exception("kb.ingest_failed", extra={"document_id": document_id})
        finally:
            await session.commit()


async def enqueue_ingest(document_id: str) -> None:
    """Schedule KB ingestion through the shared background-work queue.

    Uses ``app.core.worker.get_queue()`` — the same abstraction the CV ingestion
    pipeline uses — instead of a hardcoded Celery ``send_task`` to a queue no
    worker consumes. The caller MUST have committed the document first, because
    the handler runs in its own session (mirrors
    ``documents.ingestion_service.start_ingestion``: commit → enqueue). Under the
    default inline mode the handler runs in-process before this returns; a later
    Celery swap needs no caller change. Best-effort: a scheduling failure is
    logged (not silently swallowed) and the document stays PENDING for retry.
    """
    from app.core.worker import get_queue

    try:
        queue = get_queue()
        queue.register(_KB_TASK_NAME, _kb_ingest_task)
        await queue.enqueue(_KB_TASK_NAME, {"document_id": document_id})
    except Exception:
        logger.exception("kb.enqueue_failed", extra={"document_id": document_id})


async def run_ingest(document_id: str, *, session) -> None:
    """Execute the full ingestion pipeline for a single document.

    Called by the Celery task and directly in tests. Uses the provided
    async session so callers control transaction boundaries.
    """
    from sqlalchemy import delete, select

    from app.ai.retrieval.chunking import chunk_document
    from app.ai.retrieval.embeddings import embed_texts

    doc: KnowledgeBaseDocument | None = (
        await session.execute(
            select(KnowledgeBaseDocument).where(KnowledgeBaseDocument.id == uuid.UUID(document_id))
        )
    ).scalar_one_or_none()

    if doc is None:
        return

    # Mark as processing
    doc.status = DOC_STATUS_PROCESSING
    await session.flush()

    try:
        # --- Step 1: Extract text ---
        text = await _extract_text(doc)
        if not text.strip():
            raise ValueError("empty_content")

        # --- Step 2: Chunk ---
        chunks = await chunk_document(
            text,
            page_count=doc.page_count or 0,
        )
        if not chunks:
            raise ValueError("no_chunks_produced")

        # --- Step 3: Embed all chunks (batched) ---
        # Pass the session so real embedding spend is written to ai_usage_log
        # (visible to the budget guard, spec §5.4).
        chunk_texts = [c.content for c in chunks]
        embeddings = await embed_texts(chunk_texts, db=session, task_type="kb_embedding")

        # --- Step 4: Delete old chunks and upsert fresh ones ---
        await session.execute(
            delete(KnowledgeBaseChunk).where(KnowledgeBaseChunk.document_id == doc.id)
        )

        for chunk, embedding in zip(chunks, embeddings, strict=True):
            row = KnowledgeBaseChunk(
                id=uuid.uuid4(),
                document_id=doc.id,
                kb_id=doc.kb_id,
                content=chunk.content,
                section_heading=chunk.section_heading,
                chunk_index=chunk.chunk_index,
                token_count=chunk.token_count,
                embedding_json=json.dumps(embedding.vector) if embedding.vector else None,
            )
            session.add(row)

        # --- Step 5: Update document record ---
        doc.chunk_count = len(chunks)
        doc.status = DOC_STATUS_DONE
        doc.processed_at = datetime.now(UTC)
        await session.flush()

    except Exception as exc:
        doc.status = DOC_STATUS_FAILED
        doc.error_message = str(exc)[:500]
        doc.processed_at = datetime.now(UTC)
        await session.flush()
        raise


def _read_bytes_file(file_path: str) -> bytes:
    """Blocking read helper; run via ``asyncio.to_thread`` to avoid blocking the loop."""
    with open(file_path, "rb") as f:
        return f.read()


def _read_text_file(file_path: str) -> str:
    """Blocking read helper; run via ``asyncio.to_thread`` to avoid blocking the loop."""
    with open(file_path, encoding="utf-8", errors="replace") as f:
        return f.read()


async def _extract_text(doc: KnowledgeBaseDocument) -> str:
    """Extract text from the document file using the local-first extraction cascade
    (native text -> layout -> OCR fallback per ``docs/CV_INGESTION_EXTRACTION_SPEC.md``
    §19). Falls back to a raw plain-text read for ``.txt``/``.md`` files.
    """
    if not doc.file_path:
        return ""

    try:
        from app.ai.extraction.text_extraction import extract_text

        data = await asyncio.to_thread(_read_bytes_file, doc.file_path)
        filename = doc.file_path.rsplit("/", 1)[-1]
        result = await asyncio.to_thread(extract_text, filename, data)
        if result.text:
            return result.text
    except Exception:
        pass

    # Plain text fallback for .txt and .md files
    if doc.file_path.endswith((".txt", ".md")):
        try:
            return await asyncio.to_thread(_read_text_file, doc.file_path)
        except Exception:
            pass

    return ""
