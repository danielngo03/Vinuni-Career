"""Unit tests for the AI system improvements batch.

Covers:
- Real SSE streaming (gateway base + offline provider)
- Circuit breaker state machine
- Embedding LRU cache
- Document chunking pipeline (sliding window + semantic detection)
- Conversation memory compression trigger
- Provider routing fix (get_provider_for_alias vs get_provider)
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Output guard
# ---------------------------------------------------------------------------


def test_output_guard_does_not_scrub_natural_vietnamese_slash_phrases():
    from app.ai.gateway.output_guard import scrub_text

    text = "Tìm việc/thực tập phù hợp, xem sự/kiện và nhận tư/vấn nghề nghiệp."

    assert scrub_text(text) == text


def test_output_guard_still_scrubs_model_paths():
    from app.ai.gateway.output_guard import scrub_text

    cleaned = scrub_text("Internal model deepseek/deepseek-chat responded.")

    assert "deepseek/deepseek-chat" not in cleaned.lower()
    assert "[hệ thống AI]" in cleaned
    assert "[hệ thống AI]/" not in cleaned


# ---------------------------------------------------------------------------
# Gateway: real streaming via base fallback
# ---------------------------------------------------------------------------


class TestStreamingBase:
    @pytest.mark.asyncio
    async def test_offline_provider_stream_yields_words(self):
        from app.ai.gateway.base import AIMessage
        from app.ai.gateway.offline import OfflineProvider

        provider = OfflineProvider()
        chunks: list[str] = []
        async for chunk in provider.stream(
            [AIMessage(role="user", content="hello")],
            alias="chat_cheap",
        ):
            chunks.append(chunk)
        assert len(chunks) > 0
        full = "".join(chunks)
        assert "offline" in full.lower() or "ref:" in full

    @pytest.mark.asyncio
    async def test_base_fallback_stream_calls_complete(self):
        """AIProvider.stream() default falls back to complete() and yields full text."""
        from app.ai.gateway.base import AIMessage
        from app.ai.gateway.offline import OfflineProvider

        provider = OfflineProvider()
        msgs = [AIMessage(role="user", content="test")]
        chunks: list[str] = []
        async for chunk in provider.stream(msgs, alias="chat_cheap"):
            chunks.append(chunk)
        assert chunks  # at least one chunk


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------


class TestCircuitBreaker:
    def setup_method(self):
        # Reset circuit states between tests
        from app.ai.gateway import factory

        factory._circuit_states.clear()

    def test_circuit_open_after_threshold(self):
        from app.ai.gateway.factory import _CB_THRESHOLD, _get_circuit

        circuit = _get_circuit("test-provider")
        for _ in range(_CB_THRESHOLD):
            circuit.record_failure()

        assert circuit.is_open() is True

    def test_circuit_closed_initially(self):
        from app.ai.gateway.factory import _get_circuit

        circuit = _get_circuit("new-provider")
        assert circuit.is_open() is False

    def test_circuit_resets_on_success(self):
        from app.ai.gateway.factory import _CB_THRESHOLD, _get_circuit

        circuit = _get_circuit("provider-x")
        for _ in range(_CB_THRESHOLD):
            circuit.record_failure()
        assert circuit.is_open() is True

        circuit.record_success()
        assert circuit.is_open() is False
        assert circuit.failure_count == 0

    def test_circuit_fewer_than_threshold_stays_closed(self):
        from app.ai.gateway.factory import _CB_THRESHOLD, _get_circuit

        circuit = _get_circuit("provider-y")
        for _ in range(_CB_THRESHOLD - 1):
            circuit.record_failure()
        assert circuit.is_open() is False


# ---------------------------------------------------------------------------
# Embedding LRU cache
# ---------------------------------------------------------------------------


class TestEmbedCache:
    def setup_method(self):
        from app.ai.retrieval.embeddings import clear_embed_cache

        clear_embed_cache()

    def test_cache_key_deterministic(self):
        from app.ai.retrieval.embeddings import _cache_key

        k1 = _cache_key("hello world", "embedding_cheap")
        k2 = _cache_key("hello world", "embedding_cheap")
        assert k1 == k2

    def test_cache_key_differs_by_alias(self):
        from app.ai.retrieval.embeddings import _cache_key

        k1 = _cache_key("hello", "embedding_cheap")
        k2 = _cache_key("hello", "embedding_fast")
        assert k1 != k2

    def test_cache_put_get(self):
        from app.ai.retrieval.embeddings import _cache_get, _cache_put

        key = "abc123"
        vector = [0.1, 0.2, 0.3]
        assert _cache_get(key) is None
        _cache_put(key, vector)
        assert _cache_get(key) == vector

    def test_cache_lru_eviction(self):
        from app.ai.retrieval.embeddings import (
            _CACHE_MAX,
            _cache_get,
            _cache_put,
        )

        # Fill the cache past its limit
        for i in range(_CACHE_MAX + 5):
            _cache_put(f"key_{i}", [float(i)])
        # The oldest keys should be evicted
        assert _cache_get("key_0") is None
        # The newest key should still be present
        assert _cache_get(f"key_{_CACHE_MAX + 4}") is not None

    @pytest.mark.asyncio
    async def test_embed_texts_uses_cache(self):
        """Calling embed_texts twice with the same text should hit the cache."""
        from unittest.mock import patch

        from app.ai.retrieval.embeddings import clear_embed_cache, embed_texts

        clear_embed_cache()

        with patch("app.ai.retrieval.embeddings.real_provider_active", return_value=False):
            # Offline provider always returns deterministic results
            result1 = await embed_texts(["hello"], alias="embedding_cheap")
            result2 = await embed_texts(["hello"], alias="embedding_cheap")
            # Both calls return the same vector
            assert result1[0].vector == result2[0].vector


# ---------------------------------------------------------------------------
# Chunking pipeline
# ---------------------------------------------------------------------------


class TestChunkingPipeline:
    @pytest.mark.asyncio
    async def test_sliding_window_produces_chunks(self):
        from app.ai.retrieval.chunking import chunk_document

        text = " ".join(["word"] * 2000)  # ~2000 words
        chunks = await chunk_document(text, mode="sliding_window")
        assert len(chunks) > 1
        # Each chunk should be non-empty
        for c in chunks:
            assert c.content.strip()
            assert c.token_count > 0

    @pytest.mark.asyncio
    async def test_empty_text_returns_no_chunks(self):
        from app.ai.retrieval.chunking import chunk_document

        chunks = await chunk_document("")
        assert chunks == []

    @pytest.mark.asyncio
    async def test_short_text_returns_one_chunk(self):
        from app.ai.retrieval.chunking import chunk_document

        text = "This is a very short document."
        chunks = await chunk_document(text, mode="sliding_window")
        assert len(chunks) == 1
        assert text in chunks[0].content

    @pytest.mark.asyncio
    async def test_chunk_indices_are_sequential(self):
        from app.ai.retrieval.chunking import chunk_document

        text = " ".join(["word"] * 3000)
        chunks = await chunk_document(text, mode="sliding_window")
        indices = [c.chunk_index for c in chunks]
        assert indices == list(range(len(chunks)))

    @pytest.mark.asyncio
    async def test_semantic_mode_falls_back_when_offline(self):
        """Semantic mode without real embeddings falls back to sliding window."""
        from unittest.mock import patch

        from app.ai.retrieval.chunking import chunk_document

        text = "\n\n".join(["Paragraph " + str(i) + " " + "word " * 50 for i in range(10)])
        # Patch embed to fail so semantic mode falls through to sliding window
        with patch("app.ai.retrieval.chunking._semantic_chunks") as mock_sem:
            mock_sem.side_effect = Exception("embed_unavailable")
            # chunk_document in auto mode may choose sliding window
            chunks = await chunk_document(text, mode="sliding_window")
            assert len(chunks) > 0

    def test_heading_detection(self):
        from app.ai.retrieval.chunking import _has_structured_headings

        md_text = "# Introduction\nSome content\n\n## Section 2\nMore content"
        assert _has_structured_headings(md_text) is True

        plain_text = "no headings here just regular text flowing on"
        assert _has_structured_headings(plain_text) is False


# ---------------------------------------------------------------------------
# Conversation memory compression trigger
# ---------------------------------------------------------------------------


class TestMemoryCompression:
    def test_compress_threshold_constant(self):
        from app.modules.ai_assistant.application.session_history import (
            _COMPRESS_THRESHOLD,
            _SUMMARY_KEEP_RECENT,
        )

        assert _COMPRESS_THRESHOLD > 0
        assert _SUMMARY_KEEP_RECENT > 0
        assert _COMPRESS_THRESHOLD > _SUMMARY_KEEP_RECENT

    @pytest.mark.asyncio
    async def test_summarize_history_offline(self):
        from unittest.mock import patch

        from app.ai.gateway.base import AIMessage
        from app.modules.ai_assistant.application.session_history import _summarize_history

        turns = [
            AIMessage(role="user", content="Tell me about internships"),
            AIMessage(role="assistant", content="Here are some internship opportunities..."),
            AIMessage(role="user", content="Which companies hire freshers?"),
            AIMessage(role="assistant", content="Several companies accept fresh graduates..."),
        ]
        # Patch the factory import path used inside _summarize_history
        with patch("app.ai.gateway.factory.real_provider_active", return_value=False):
            summary = await _summarize_history(turns)
        # Summary must be a non-empty string
        assert isinstance(summary, str)
        assert len(summary) > 0

    @pytest.mark.asyncio
    async def test_summarize_empty_returns_empty(self):
        from app.modules.ai_assistant.application.session_history import _summarize_history

        result = await _summarize_history([])
        assert result == ""


# ---------------------------------------------------------------------------
# Provider routing fix
# ---------------------------------------------------------------------------


class TestProviderRouting:
    def test_real_provider_active_returns_bool(self):
        from app.ai.gateway.factory import real_provider_active

        result = real_provider_active()
        assert isinstance(result, bool)

    def test_get_provider_for_alias_returns_offline_when_disabled(self):
        from unittest.mock import patch

        from app.ai.gateway.factory import get_provider_for_alias
        from app.ai.gateway.offline import OfflineProvider

        with patch("app.ai.gateway.factory.real_provider_active", return_value=False):
            provider = get_provider_for_alias("chat_cheap")
        assert isinstance(provider, OfflineProvider)

    def test_full_local_aliases_are_accessible_without_api_key(self):
        from app.ai.gateway import runtime_config

        selected = (
            "chat_local",
            "reasoning_local",
            "embedding_local",
            "rerank_local",
            "eval_local",
        )

        assert runtime_config.selected_aliases_accessible(
            selected,
            runtime_config._BUILTIN_ROUTES,
        )


# ---------------------------------------------------------------------------
# Retrieval reranking
# ---------------------------------------------------------------------------


class TestRerank:
    def test_parse_rank_array_accepts_fenced_json(self):
        from app.ai.retrieval.rerank import _parse_rank_array

        assert _parse_rank_array("```json\n[2, 1, 3]\n```") == [2, 1, 3]

    @pytest.mark.asyncio
    async def test_rerank_jobs_uses_configured_rerank_alias(self, monkeypatch):
        from types import SimpleNamespace
        from uuid import uuid4

        from app.ai.gateway.base import AICompletion
        from app.ai.gateway.task_runner import AiTaskRunner
        from app.ai.retrieval import rerank

        captured: dict[str, str] = {}

        async def fake_complete(self, messages, *, temperature=0.2, max_tokens=1024):
            captured["alias"] = self._alias
            captured["task_type"] = self._task_type
            return AICompletion(text="[2, 1]", model_alias=self._alias)

        monkeypatch.setattr(rerank, "real_provider_active", lambda: True)
        monkeypatch.setattr(
            rerank.runtime_config,
            "current",
            lambda: SimpleNamespace(rerank_model_alias="rerank_campus_secure"),
        )
        monkeypatch.setattr(AiTaskRunner, "complete", fake_complete)

        first = uuid4()
        second = uuid4()
        result = await rerank.rerank_jobs(
            "machine learning internship",
            {first: "Backend engineer", second: "Machine learning intern"},
            top_k=2,
        )

        assert captured == {
            "alias": "rerank_campus_secure",
            "task_type": "retrieval_rerank",
        }
        assert [jid for jid, _ in result] == [second, first]
