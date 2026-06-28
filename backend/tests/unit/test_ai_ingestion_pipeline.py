from __future__ import annotations

from app.ai.agents import run_cv_pipeline
from app.ai.extraction import gemini_document_cv
from app.ai.ingestion import inspect_upload
from app.ai.retrieval import RankedCandidate, lexical_rerank, reciprocal_rank_fusion
from app.modules.recruitment.api.cvs import _extract_full_cv_text


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


def test_text_cv_upload_extracts_full_text_not_preview():
    content = (
        "Nguyen Van A\nSkills: Python FastAPI PostgreSQL Docker\n"
        + "Backend platform ownership\n" * 40
    ).encode()
    decision = inspect_upload(content, declared_content_type="text/plain", filename="cv.txt")

    assert decision.route == "text_extraction"
    assert len(decision.extracted_text_preview) == 500
    assert len(_extract_full_cv_text(content, decision.detected_kind)) > 500


def test_cv_pipeline_masks_pii_and_normalizes_skills():
    result = run_cv_pipeline(
        "Nguyen Van A\nEmail: a@example.com\nSkills: React.js, NodeJS, PostgreSQL, Docker"
    )

    assert "a@example.com" not in result.masked_data["text"]
    assert {"react", "node", "postgresql", "docker"}.issubset(set(result.normalized_skills))
    assert result.parsed_data["document_type"] == "cv"


def test_gemini_pdf_cv_extraction_parses_structured_json(monkeypatch):
    monkeypatch.setattr(gemini_document_cv, "get_gemini_api_keys", lambda: ["test-key"])
    monkeypatch.setattr(
        gemini_document_cv,
        "_post_generate_content",
        lambda _api_key, _model, _body: {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": (
                                    '{"document_type":"cv","summary":"Backend student",'
                                    '"raw_markdown":"## Summary\\nBackend student\\n\\n'
                                    '## Skills\\n- Python\\n\\n'
                                    '## Projects\\n- Career platform: Matching service",'
                                    '"skills":[{"name":"Python","evidence":"Built FastAPI APIs"}],'
                                    '"education":[],"experiences":[],"projects":['
                                    '{"name":"Career platform","description":"Matching service",'
                                    '"technologies":["FastAPI","PostgreSQL"]}],'
                                    '"languages":["English"],"certifications":[],'
                                    '"raw_text_quality":"vision_extracted","confidence":0.9}'
                                )
                            }
                        ]
                    }
                }
            ]
        },
    )

    extraction = gemini_document_cv.extract_cv_from_pdf(b"%PDF- fake")
    raw_text = gemini_document_cv.cv_extraction_to_text(extraction)

    assert extraction.summary == "Backend student"
    assert extraction.raw_text_quality == "vision_extracted"
    assert raw_text.startswith("## Summary")
    assert "Python" in raw_text
    assert "Career platform" in raw_text


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
