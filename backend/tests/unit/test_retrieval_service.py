from __future__ import annotations

from app.ai.retrieval import hybrid_retrieve, index_text


def test_indexing_chunks_embeds_and_reranks_passages():
    chunks = index_text(
        document_id="job-1",
        entity_type="job",
        title="Backend Engineer",
        text=(
            "REQUIREMENTS\nPython FastAPI PostgreSQL Docker are required.\n\n"
            "RESPONSIBILITIES\nBuild reliable backend APIs and operate services.\n\n"
            "BENEFITS\nLearning budget and flexible work."
        ),
        chunk_size=90,
        overlap=15,
    )

    results = hybrid_retrieve("Python backend API", entity_type="job")

    assert len(chunks) >= 2
    assert all(chunk.chunk_id.startswith("job-1:") for chunk in chunks)
    assert chunks[0].token_count > 0
    assert results
    assert results[0].metadata["document_id"] == "job-1"
