"""Unit tests for the deterministic chat model router + tool-subset selection.

No LLM, no DB: ``route_turn`` is a pure rule-based classifier and
``select_specs`` filters the live tool registry fail-open.
"""

from __future__ import annotations

from app.modules.ai_assistant.application import model_router
from app.modules.ai_assistant.application.model_router import (
    CORE_GROUP,
    TIER_CHEAP,
    TIER_DEFAULT,
    TIER_REASONING,
    TOOL_GROUPS,
    RouteDecision,
    route_turn,
    select_specs,
)
from app.modules.ai_assistant.application.tool_registry import TOOL_SPECS

# conftest pins AI_DEFAULT_MODEL_ALIAS / AI_REASONING_MODEL_ALIAS.
_DEFAULT = "chat_default"
_REASONING = "reasoning_default"
_CHEAP = "chat_cheap"


# --------------------------------------------------------------------------- #
# Tier decisions                                                              #
# --------------------------------------------------------------------------- #


def test_smalltalk_routes_to_cheap_tier() -> None:
    for text in ("xin chào bạn", "hello!", "cảm ơn bạn nhiều", "thanks", "ok", "tạm biệt"):
        decision = route_turn(text)
        assert decision.tier == TIER_CHEAP, text
        assert decision.model_alias == _CHEAP
        # Smalltalk is confident core-only OR fail-open short text.
        assert decision.escalate_alias == _DEFAULT


def test_meta_capability_question_routes_cheap_with_core_tools() -> None:
    decision = route_turn("Bạn có thể làm gì?")
    assert decision.tier == TIER_CHEAP
    assert decision.tool_groups == (CORE_GROUP,)
    assert decision.confident is True


def test_standard_operational_ask_routes_default_tier() -> None:
    decision = route_turn("Cho tôi xem pipeline ứng viên của job Backend Engineer")
    assert decision.tier == TIER_DEFAULT
    assert decision.model_alias == _DEFAULT
    assert "pipeline" in decision.tool_groups
    assert decision.confident is True
    assert decision.escalate_alias == _REASONING


def test_explicit_deep_analysis_routes_reasoning_tier_vi_and_en() -> None:
    for text in (
        "Phân tích sâu hiệu quả tuyển dụng quý này giúp tôi",
        "Give me a comprehensive strategy comparison for our hiring funnel",
        "So sánh chất lượng ứng viên giữa hai job đang mở",
    ):
        decision = route_turn(text)
        assert decision.tier == TIER_REASONING, text
        assert decision.model_alias == _REASONING
        # Reasoning is the top tier — no further escalation.
        assert decision.escalate_alias is None


def test_long_analytical_ask_routes_reasoning() -> None:
    text = (
        "Tại sao tỉ lệ chuyển đổi từ vòng sàng lọc sang vòng phỏng vấn của chúng tôi "
        "lại thấp như vậy trong quý vừa rồi? Hãy phân tích các yếu tố ảnh hưởng chính "
        "bao gồm chất lượng nguồn ứng viên, thời gian phản hồi của đội tuyển dụng, "
        "mức độ hấp dẫn của mô tả công việc và cả yếu tố mùa vụ, sau đó đề xuất cho tôi "
        "những thay đổi cụ thể có thể cải thiện tỉ lệ này trong quý tới."
    )
    assert len(text) >= 350
    decision = route_turn(text)
    assert decision.tier == TIER_REASONING


def test_ambiguous_ask_is_default_and_not_confident() -> None:
    decision = route_turn(
        "điều gì đó rất mơ hồ không khớp bất kỳ nhóm nào nhưng lại dài hơn bốn mươi ký tự"
    )
    assert decision.tier == TIER_DEFAULT
    assert decision.confident is False
    assert decision.tool_groups == ()


def test_aliases_are_internal_and_never_provider_names() -> None:
    for text in ("hello", "xem pipeline ứng viên", "phân tích sâu chiến lược"):
        decision = route_turn(text)
        for banned in ("openai", "openrouter", "deepseek", "gpt", "claude", "gemini"):
            assert banned not in decision.model_alias.lower()


# --------------------------------------------------------------------------- #
# Tool-subset selection (fail-open)                                           #
# --------------------------------------------------------------------------- #


def _all_specs() -> list:
    return list(TOOL_SPECS.values())


def test_confident_pipeline_ask_passes_pipeline_plus_core_only() -> None:
    specs = _all_specs()
    decision = RouteDecision(
        tier=TIER_DEFAULT,
        model_alias=_DEFAULT,
        tool_groups=("pipeline",),
        confident=True,
        escalate_alias=_REASONING,
    )
    subset = select_specs(specs, decision)
    allowed = TOOL_GROUPS["pipeline"] | TOOL_GROUPS[CORE_GROUP]
    assert subset, "subset must never be empty when pipeline tools exist"
    assert {s.name for s in subset} <= allowed
    assert len(subset) < len(specs), "subset must actually save schema tokens"


def test_not_confident_falls_open_to_full_set() -> None:
    specs = _all_specs()
    decision = RouteDecision(
        tier=TIER_DEFAULT,
        model_alias=_DEFAULT,
        tool_groups=(),
        confident=False,
        escalate_alias=_REASONING,
    )
    assert select_specs(specs, decision) == specs


def test_groups_tolerate_tool_names_missing_from_registry() -> None:
    # Some group members may not exist yet (other lanes add tools in parallel);
    # selection must not raise and must not fabricate specs.
    registry_names = set(TOOL_SPECS.keys())
    for group in TOOL_GROUPS:
        decision = RouteDecision(
            tier=TIER_DEFAULT,
            model_alias=_DEFAULT,
            tool_groups=(group,),
            confident=True,
            escalate_alias=None,
        )
        subset = select_specs(_all_specs(), decision)
        assert all(s.name in registry_names for s in subset)


def test_all_matched_names_unavailable_falls_open_to_full_set() -> None:
    # A caller whose grant-filtered spec list contains none of the matched
    # group's tools must keep their full (already tiny) list.
    specs = [s for s in _all_specs() if s.name == "search_jobs"]
    decision = RouteDecision(
        tier=TIER_DEFAULT,
        model_alias=_DEFAULT,
        tool_groups=("media",),
        confident=True,
        escalate_alias=None,
    )
    assert select_specs(specs, decision) == specs


def test_route_module_has_no_llm_dependency() -> None:
    # Guard against accidental provider/model coupling in the router module.
    import inspect

    source = inspect.getsource(model_router)
    for banned in ("provider.complete", "OfflineProvider", "get_provider_for_alias"):
        assert banned not in source
