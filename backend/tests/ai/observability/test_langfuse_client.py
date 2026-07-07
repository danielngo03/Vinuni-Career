# tests/ai/observability/test_langfuse_client.py
from app.ai.observability import langfuse_client as lf


def test_disabled_when_no_keys(monkeypatch):
    monkeypatch.setattr(lf, "_settings_keys", lambda: (None, None, None))
    assert lf.is_enabled() is False
    assert lf.trace_call(task_type="job_fit", alias="a", provider=None, model=None,
        prompt_tokens=0, completion_tokens=0, latency_ms=1, status="ok",
        org_id=None, user_id=None, request_id="r") is None  # no-op, no raise
