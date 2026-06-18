from __future__ import annotations

from app.ai.agents import run_cv_pipeline
from app.ai.ingestion import inspect_upload
from app.ai.retrieval import RankedCandidate, lexical_rerank, reciprocal_rank_fusion


def test_gatekeeper_rejects_spoofed_binary_as_pdf():
    decision = inspect_upload(
        b"\x7fELFnot a real pdf",
        declared_content_type="application/pdf",
        filename="cv.pdf",
    )

    assert decision.route == "reject"
    assert "Rejected because file signature does not match declaration." in decision.reasons


def test_gatekeeper_routes_plain_text_cv_to_text_extraction():
    content = b"Nguyen Van A\nSkills: Python FastAPI PostgreSQL Docker\nExperience backend APIs"
    decision = inspect_upload(content, declared_content_type="text/plain", filename="cv.txt")

    assert decision.route == "text_extraction"
    assert decision.detected_kind == "text"
    assert decision.metadata["text_chars"] > 40


def test_cv_pipeline_masks_pii_and_normalizes_skills():
    result = run_cv_pipeline(
        "Nguyen Van A\nEmail: a@example.com\nSkills: React.js, NodeJS, PostgreSQL, Docker"
    )

    assert "a@example.com" not in result.masked_data["text"]
    assert {"react", "node", "postgresql", "docker"}.issubset(set(result.normalized_skills))
    assert result.parsed_data["document_type"] == "cv"


def test_rerank_combines_dense_sparse_and_lexical_signals():
    dense = [
        RankedCandidate("1", "Python FastAPI backend APIs", 0.8),
        RankedCandidate("2", "React frontend UI", 0.7),
    ]
    sparse = [
        RankedCandidate("2", "React frontend UI", 0.95),
        RankedCandidate("1", "Python FastAPI backend APIs", 0.6),
    ]

    fused = reciprocal_rank_fusion([dense, sparse])
    reranked = lexical_rerank("Python backend API", fused)

    assert reranked[0].id == "1"
