"""University KB assistant tool: scope preference + leakage-safe citations (WS3.3).

Pure/DB-free unit tests for the ``search_university_knowledge`` wiring:
- the query-scope preference constant is exactly ``{university, platform}``
  (never partner/job), and
- ``_leakage_safe_chunks`` strips every retrieval internal (chunk/kb/doc id,
  chunk index, token count, similarity score) before results leave the tool,
  keeping only the document title / section heading / content the assistant
  needs to answer and cite.
"""

from __future__ import annotations

from app.modules.ai_assistant.application.tools.university import _leakage_safe_chunks
from app.modules.knowledge_base.application.kb_service import UNIVERSITY_QUERY_SCOPES
from app.modules.knowledge_base.domain.models import (
    KB_SCOPE_PLATFORM,
    KB_SCOPE_UNIVERSITY,
)


def test_university_query_scopes_are_university_plus_platform() -> None:
    assert UNIVERSITY_QUERY_SCOPES == frozenset({KB_SCOPE_UNIVERSITY, KB_SCOPE_PLATFORM})
    # A staffer's institutional search must never pull in employer/job KBs.
    assert "partner" not in UNIVERSITY_QUERY_SCOPES
    assert "job" not in UNIVERSITY_QUERY_SCOPES


def test_leakage_safe_chunks_strip_all_retrieval_internals() -> None:
    raw = [
        {
            "id": "chunk-123",
            "kb_id": "kb-1",
            "document_id": "doc-9",
            "content": "Staff may approve a job once the partner is verified.",
            "section_heading": "Moderation",
            "chunk_index": 4,
            "token_count": 88,
            "document_title": "Moderation Playbook",
            "score": 0.97,
        }
    ]
    safe = _leakage_safe_chunks(raw)
    assert safe == [
        {
            "document_title": "Moderation Playbook",
            "section_heading": "Moderation",
            "content": "Staff may approve a job once the partner is verified.",
        }
    ]
    only = safe[0]
    for leaky in ("id", "kb_id", "document_id", "chunk_index", "token_count", "score"):
        assert leaky not in only


def test_leakage_safe_chunks_handles_empty_and_malformed() -> None:
    assert _leakage_safe_chunks([]) == []
    # Non-dict entries are dropped rather than crashing the tool.
    assert _leakage_safe_chunks([None, "x", 3]) == []  # type: ignore[list-item]
    # Missing fields degrade to safe defaults, never a leak.
    assert _leakage_safe_chunks([{"content": "hi"}]) == [
        {"document_title": None, "section_heading": "", "content": "hi"}
    ]
