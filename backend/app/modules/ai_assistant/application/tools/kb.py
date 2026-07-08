"""Knowledge base RAG query tool handler."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.permissions import Principal


async def knowledge_base_query(session: AsyncSession, principal: Principal, args: dict) -> dict:
    if not principal.is_authenticated:
        return {"ok": False, "error": "auth_required", "chunks": []}
    query = (args.get("query") or "").strip()
    if not query:
        return {"ok": False, "error": "query_required", "chunks": []}

    from app.ai.safety.input_guard import sanitize_instruction
    safe_query, blocked = sanitize_instruction(query)
    if blocked or not safe_query:
        return {"ok": False, "error": "query_blocked", "chunks": []}

    try:
        from app.modules.knowledge_base.application.kb_service import (
            assemble_rag_context,
            get_kb_ids_for_query,
            search_chunks,
        )

        kb_ids = await get_kb_ids_for_query(session, principal=principal)
        if not kb_ids:
            return {
                "ok": True,
                "found": False,
                "context": "",
                "chunks": [],
                "message": "Không có cơ sở kiến thức nào được tìm thấy.",
            }

        chunks = await search_chunks(session, query=safe_query, kb_ids=kb_ids, limit=5)
        context = assemble_rag_context(chunks)
        return {
            "ok": True,
            "found": bool(chunks),
            "context": context,
            "chunks": chunks,
            "source_count": len(chunks),
        }
    except Exception:
        return {
            "ok": False,
            "error": "kb_unavailable",
            "chunks": [],
            "context": "",
        }
