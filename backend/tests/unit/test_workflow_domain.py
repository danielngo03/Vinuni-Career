from __future__ import annotations

from app.modules.workflow.domain.graph import FlowContext


def test_flow_context_interpolates_trigger_and_variables() -> None:
    ctx = FlowContext(trigger={"user_id": "u1"}, variables={"fraud_score": 0.82})
    assert ctx.interpolate("{{fraud_score}} > 0.70") == "0.82 > 0.70"
    assert ctx.interpolate("user={{user_id}}") == "user=u1"


def test_flow_context_merge_accumulates_variables() -> None:
    ctx = FlowContext(trigger={}, variables={"a": 1})
    ctx.merge({"b": 2})
    assert ctx.variables == {"a": 1, "b": 2}


def test_flow_context_interpolate_missing_key_raises() -> None:
    ctx = FlowContext(trigger={}, variables={})
    import pytest

    with pytest.raises(KeyError):
        ctx.interpolate("{{missing}}")
