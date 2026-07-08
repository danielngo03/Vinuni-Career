"""Unit tests for the local, free, offline BM25-lite reranker (§6.3 tier 2)."""

from __future__ import annotations

import uuid

from app.ai.retrieval.local_reranker import local_rerank
from app.ai.retrieval.rerank import rerank_kb_chunks


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


def test_empty_candidates_returns_empty_list():
    assert local_rerank("python engineer", {}) == []


def test_empty_query_preserves_original_order_with_neutral_scores():
    a, b = _uuid(), _uuid()
    result = local_rerank("", {a: "Backend Engineer", b: "Frontend Engineer"})
    assert [cid for cid, _ in result] == [a, b]
    assert all(score == 0.0 for _, score in result)


def test_whitespace_only_query_is_treated_as_empty():
    a, b = _uuid(), _uuid()
    result = local_rerank("   ", {a: "Backend Engineer", b: "Frontend Engineer"})
    assert [cid for cid, _ in result] == [a, b]


def test_exact_keyword_match_ranks_higher():
    match = _uuid()
    off_topic = _uuid()
    candidates = {
        off_topic: "Marketing Coordinator responsible for social media campaigns",
        match: "Backend Engineer with strong Python and PostgreSQL experience",
    }
    result = local_rerank("python backend engineer", candidates)
    ranked_ids = [cid for cid, _ in result]
    assert ranked_ids[0] == match


def test_more_keyword_overlap_scores_higher_than_partial_overlap():
    strong = _uuid()
    weak = _uuid()
    candidates = {
        weak: "Data Analyst using Excel",
        strong: "Data Analyst using Python, SQL, and Excel for data pipelines",
    }
    result = local_rerank("python sql data pipeline", candidates)
    scores = dict(result)
    assert scores[strong] > scores[weak]


def test_top_k_caps_result_count():
    candidates = {_uuid(): f"Engineer role {i}" for i in range(10)}
    result = local_rerank("engineer", candidates, top_k=3)
    assert len(result) == 3


def test_results_sorted_descending_by_score():
    candidates = {_uuid(): text for text in ["python job", "python python job job", "unrelated"]}
    result = local_rerank("python job", candidates)
    scores = [score for _, score in result]
    assert scores == sorted(scores, reverse=True)


def test_no_network_no_provider_dependency():
    """This reranker must never import the AI gateway/HTTP stack — pure stdlib only."""
    from app.ai.retrieval import local_reranker

    module_names = {
        name.split(".")[0] for name in getattr(local_reranker, "__dict__", {})
    }
    assert "AiTaskRunner" not in module_names
    assert not hasattr(local_reranker, "get_provider")
    assert not hasattr(local_reranker, "get_provider_for_alias")
    assert not hasattr(local_reranker, "AsyncSession")


def test_is_synchronous_not_async():
    """The whole point is zero-latency local scoring — must not be a coroutine."""
    import inspect

    assert not inspect.iscoroutinefunction(local_rerank)


def test_diacritics_and_case_are_normalized_for_matching():
    a = _uuid()
    b = _uuid()
    candidates = {
        a: "KỸ SƯ PHẦN MỀM với kinh nghiệm Python",
        b: "Chuyên viên Marketing",
    }
    result = local_rerank("kỹ sư phần mềm python", candidates)
    assert result[0][0] == a


def test_rerank_kb_chunks_is_a_thin_wrapper_over_local_rerank():
    chunk_a = _uuid()
    chunk_b = _uuid()
    docs = {
        chunk_a: "Sinh viên quốc tế cần giấy phép lao động trước khi thực tập",
        chunk_b: "Chính sách nghỉ phép của nhân viên toàn thời gian",
    }
    result = rerank_kb_chunks("giấy phép lao động sinh viên quốc tế", docs, top_k=2)
    assert result[0][0] == chunk_a
    assert len(result) == 2
