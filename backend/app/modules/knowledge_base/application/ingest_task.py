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
import uuid
from datetime import UTC, datetime

from app.modules.knowledge_base.domain.models import (
    DOC_STATUS_DONE,
    DOC_STATUS_FAILED,
    DOC_STATUS_PROCESSING,
    KnowledgeBaseChunk,
    KnowledgeBaseDocument,
)


def enqueue_ingest(document_id: str) -> None:
    """Enqueue the ingest task via Celery. Safe to call when Celery is unavailable."""
    try:
        from app.worker.celery_app import celery_app
        celery_app.send_task(
            "knowledge_base.ingest_document",
            args=[document_id],
            queue="ai",
        )
    except Exception:
        pass  # Celery offline — document stays PENDING; admin can re-trigger


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
            select(KnowledgeBaseDocument).where(
                KnowledgeBaseDocument.id == uuid.UUID(document_id)
            )
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
        chunk_texts = [c.content for c in chunks]
        embeddings = await embed_texts(chunk_texts)

        # --- Step 4: Delete old chunks and upsert fresh ones ---
        await session.execute(
            delete(KnowledgeBaseChunk).where(
                KnowledgeBaseChunk.document_id == doc.id
            )
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
