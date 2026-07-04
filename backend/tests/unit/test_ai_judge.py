"""Unit tests for the LLM-as-judge module (§10.3) — offline provider only.

Verifies verdict parsing, score clamping, rubric isolation (judge uses the
``eval_model_alias``, never the chat alias), and that parse failures raise
``JudgeParseError`` instead of fabricating a score.
"""

from __future__ import annotations

from unittest import mock

import pytest
from app.ai.evaluation import judge
from app.ai.gateway.base import AICompletion, AIMessage


class _FakeProvider:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls: list[dict] = []

    async def complete(self, messages: list[AIMessage], **kwargs) -> AICompletion:
        self.calls.append({"messages": messages, **kwargs})
        return AICompletion(
            text=self.text,
            model_alias=kwargs.get("alias", ""),
            usage={},
            finish_reason="stop",
        )


class TestParseVerdict:
    def test_plain_json(self) -> None:
        result = judge._parse_verdict(
            '{"score": 4, "reasoning": "Grounded and complete.", "flags": []}'
        )
        assert result.score == 4
        assert result.flags == []

    def test_fenced_json_and_clamping(self) -> None:
        result = judge._parse_verdict(
            '```json\n{"score": 99, "reasoning": "x", "flags": ["fabrication"]}\n```'
        )
        assert result.score == 5  # clamped to 1-5
        assert result.flags == ["fabrication"]

    def test_low_clamp(self) -> None:
        assert judge._parse_verdict('{"score": -3, "reasoning": ""}').score == 1

    def test_garbage_raises_parse_error(self) -> None:
        for garbage in ("no json here", '{"score": "excellent"}', "{broken"):
            with pytest.raises(judge.JudgeParseError):
                judge._parse_verdict(garbage)


class TestJudgeResponse:
    async def test_uses_eval_alias_not_chat_alias(self) -> None:
        fake = _FakeProvider('{"score": 3, "reasoning": "ok", "flags": []}')
        with mock.patch.object(judge, "get_provider", lambda: fake):
            result = await judge.judge_response(
                "bias_detection", {"text": "sample"}, "flagged 2 phrases"
            )
        assert result.score == 3
        from app.ai.gateway import runtime_config

        cfg = runtime_config.current()
        assert fake.calls[0]["alias"] == cfg.eval_model_alias
        assert fake.calls[0]["alias"] != cfg.chat_model_alias

    async def test_default_rubric_per_task_in_prompt(self) -> None:
        fake = _FakeProvider('{"score": 5, "reasoning": "", "flags": []}')
        with mock.patch.object(judge, "get_provider", lambda: fake):
            await judge.judge_response("knowledge_base_query", {}, "answer [1]")
        user_msg = fake.calls[0]["messages"][1].content
        assert judge.RUBRICS["knowledge_base_query"] in user_msg

    async def test_unparseable_judge_output_raises(self) -> None:
        fake = _FakeProvider("I think it deserves a good grade!")
        with mock.patch.object(judge, "get_provider", lambda: fake):
            with pytest.raises(judge.JudgeParseError):
                await judge.judge_response("search_jobs", {}, "results")

    async def test_offline_provider_end_to_end_no_key(self) -> None:
        """Under the real default offline provider the call itself works;
        the echo text is not a verdict, so parsing raises — never a score."""
        with pytest.raises(judge.JudgeParseError):
            await judge.judge_response("search_jobs", {}, "some results")
