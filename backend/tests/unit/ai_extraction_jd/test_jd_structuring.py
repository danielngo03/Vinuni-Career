import pytest
from app.ai.extraction.jd import structuring
from app.shared.exceptions import AIUnavailableError


@pytest.mark.asyncio
async def test_run_jd_text_structuring_returns_llm_json(monkeypatch):
    async def fake(**kwargs):
        assert kwargs["task_type"] == "jd_extraction"
        assert "JOB_DESCRIPTION_TEXT" in kwargs["user_content"]
        return {"title": "Backend Engineer", "employment_type": "full_time"}

    monkeypatch.setattr(structuring, "generate_json_note", fake)
    out = await structuring.run_jd_text_structuring("We are hiring a Backend Engineer, full-time.")
    assert out["title"] == "Backend Engineer"


@pytest.mark.asyncio
async def test_propagates_ai_unavailable(monkeypatch):
    async def boom(**kwargs):
        raise AIUnavailableError()

    monkeypatch.setattr(structuring, "generate_json_note", boom)
    with pytest.raises(AIUnavailableError):
        await structuring.run_jd_text_structuring("some jd text")
