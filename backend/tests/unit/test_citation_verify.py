"""Unit tests for §6.5 RAG citation verification (app.ai.retrieval.citation_verify)."""

from __future__ import annotations

from app.ai.retrieval.citation_verify import kb_source_titles, verify_citations


def test_no_citation_markers_passes_through_unchanged():
    answer = "Bạn có thể nộp đơn trực tiếp trên trang việc làm."
    result = verify_citations(answer, ["Internship Policy"])
    assert result.clean_answer == answer
    assert result.hallucination_risk is False
    assert result.cited_count == 0
    assert result.citation_grounded_rate is None


def test_grounded_citation_is_kept_verbatim():
    answer = "Theo Internship Policy — sinh viên cần hoàn thành ít nhất 3 tín chỉ."
    result = verify_citations(answer, ["Internship Policy"])
    assert "Internship Policy" in result.clean_answer
    assert result.hallucination_risk is False
    assert result.cited_count == 1
    assert result.grounded_count == 1
    assert result.citation_grounded_rate == 1.0


def test_ungrounded_citation_is_stripped_and_flagged():
    answer = "Theo Fake Internal Memo — bạn được miễn học phí hoàn toàn."
    result = verify_citations(answer, ["Internship Policy"])
    assert "Fake Internal Memo" not in result.clean_answer
    assert "tài liệu được cung cấp" in result.clean_answer
    assert result.hallucination_risk is True
    assert result.cited_count == 1
    assert result.grounded_count == 0
    assert result.ungrounded_count == 1
    assert result.citation_grounded_rate == 0.0


def test_english_citation_marker_supported():
    answer = "According to Internship Policy, students must register in advance."
    result = verify_citations(answer, ["Internship Policy"])
    assert result.hallucination_risk is False
    assert result.grounded_count == 1


def test_mixed_grounded_and_ungrounded_citations():
    answer = (
        "Theo Internship Policy: cần đăng ký trước 2 tuần. "
        "Theo Salary Guarantee Memo: bạn được đảm bảo lương 2000 USD/tháng."
    )
    result = verify_citations(answer, ["Internship Policy"])
    assert result.cited_count == 2
    assert result.grounded_count == 1
    assert result.ungrounded_count == 1
    assert result.hallucination_risk is True
    assert "Internship Policy" in result.clean_answer
    assert "Salary Guarantee Memo" not in result.clean_answer
    assert result.citation_grounded_rate == 0.5


def test_no_sources_retrieved_makes_any_citation_ungrounded():
    """If the KB retrieval found nothing, any citation the model invents is fabricated."""
    answer = "Theo Some Handbook — bạn có thể làm việc không giới hạn giờ."
    result = verify_citations(answer, [])
    assert result.hallucination_risk is True
    assert "Some Handbook" not in result.clean_answer


def test_empty_answer_is_a_no_op():
    result = verify_citations("", ["Internship Policy"])
    assert result.clean_answer == ""
    assert result.hallucination_risk is False
    assert result.cited_count == 0


def test_case_and_whitespace_insensitive_matching():
    answer = "Theo   internship   policy  , bạn cần đăng ký."
    result = verify_citations(answer, ["Internship Policy"])
    assert result.hallucination_risk is False
    assert result.grounded_count == 1


def test_partial_name_match_is_grounded():
    """A citation naming a shortened/partial document title still counts as grounded."""
    answer = "Theo Internship Policy 2026 — sinh viên cần đăng ký sớm."
    result = verify_citations(answer, ["Internship Policy"])
    assert result.hallucination_risk is False
    assert result.grounded_count == 1


def test_kb_source_titles_dedupes_and_ignores_missing_titles():
    chunks = [
        {"document_title": "Internship Policy", "content": "a"},
        {"document_title": "Internship Policy", "content": "b"},
        {"document_title": "Visa Guide", "content": "c"},
        {"content": "no title here"},
        {},
    ]
    titles = kb_source_titles(chunks)
    assert titles == ["Internship Policy", "Visa Guide"]


def test_kb_source_titles_empty_list():
    assert kb_source_titles([]) == []
    assert kb_source_titles(None) == []  # type: ignore[arg-type]
