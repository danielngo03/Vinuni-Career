"""Leak-safe status phases + ungrounded-number telemetry flag for the partner
native tool loop.

Everything here is OFFLINE/deterministic: the model completion is scripted (the
native loop's ``llm_complete_native`` is monkeypatched to a fixed sequence of
``AICompletion`` objects) and read-only tool dispatch is faked, so no provider
key, network, or real model call is involved (``AI_REAL_CALLS_ENABLED=false`` is
pinned by conftest).

Two invariants are locked:

1. The loop emits ``{"type": "status", "code": <phase>}`` events using ONLY the
   frozen leak-safe phase vocabulary (``model_router.LEAK_SAFE_PHASES``):
   "understanding" opens every turn, each tool dispatch emits its mapped work
   phase, and "composing" precedes the final text. A ``status`` event NEVER
   carries a tool name (the separate ``tool_call`` event still does, for
   internal/eval use only).

2. A partner pure-text answer (no tool this turn) that asserts a specific
   count/percentage/salary/metric appends the ``ungrounded_numeric_suspected``
   guard flag (telemetry only — the user-facing text is never altered), while a
   tool-grounded answer or plain non-numeric advice does not.
"""

from __future__ import annotations

import uuid

import pytest
from app.ai.gateway.base import AICompletion, AIMessage
from app.modules.ai_assistant.application import (
    chat_service,
    guardrails,
    model_router,
    native_loop,
    session_history,
)
from app.modules.ai_assistant.application.native_loop import available_specs
from app.modules.ai_assistant.application.tools.specs import TOOL_SPECS

from tests.messaging_utils import make_partner

# --------------------------------------------------------------------------- #
# Scripted-model + faked-dispatch harness                                     #
# --------------------------------------------------------------------------- #


def _completion(text: str = "", tool_calls: list[dict] | None = None) -> AICompletion:
    return AICompletion(text=text, model_alias="chat_default", tool_calls=tool_calls or [])


def _tool_call(name: str, arguments: str = "{}") -> dict:
    return {
        "id": f"call_{name}",
        "type": "function",
        "function": {"name": name, "arguments": arguments},
    }


def _script_model(monkeypatch, completions: list[AICompletion]) -> None:
    """Monkeypatch the native loop to return a fixed sequence of completions."""
    seq = iter(completions)

    async def _fake_complete(history, *, system_prompt, tools, **_kw) -> AICompletion:
        return next(seq)

    monkeypatch.setattr(native_loop, "llm_complete_native", _fake_complete)


def _fake_dispatch_ok(monkeypatch) -> None:
    async def _dispatch(name, args, *, session=None, principal=None) -> dict:
        return {"ok": True}

    monkeypatch.setattr(native_loop, "dispatch_tool", _dispatch)


def _capture_guard_flags(monkeypatch) -> dict:
    """Capture the guard_flags/status handed to per-turn telemetry."""
    captured: dict = {}

    async def _record(db, *, principal, session_id, alias, status, latency_ms, **kw) -> None:
        captured["status"] = status
        captured["guard_flags"] = list(kw.get("guard_flags") or [])
        captured["tool_names"] = list(kw.get("tool_names") or [])

    monkeypatch.setattr(native_loop.turn_telemetry, "record_chat_turn", _record)
    return captured


async def _chat(session, principal):
    created = await chat_service.create_session(session, principal=principal)
    return await session_history.require_session(session, principal, uuid.UUID(created["id"]))


async def _drive(session, principal, chat, *, specs, script, text_guard=None) -> list[dict]:
    events: list[dict] = []
    async for ev in native_loop.run_native_turn(
        session,
        principal=principal,
        chat=chat,
        history=[AIMessage(role="user", content="hỏi gì đó")],
        system_prompt="SYS",
        specs=specs,
        locale="vi",
        text_guard=text_guard,
    ):
        events.append(ev)
    return events


def _statuses(events: list[dict]) -> list[str]:
    return [e["code"] for e in events if e["type"] == "status"]


# --------------------------------------------------------------------------- #
# 1. Pure phase mapping table                                                 #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("name", "phase"),
    [
        # jobs / pipeline / events / knowledge reads → retrieving
        ("get_partner_jobs", "retrieving"),
        ("get_job_detail", "retrieving"),
        ("get_partner_pipeline_summary", "retrieving"),
        ("search_partner_candidates", "retrieving"),
        ("get_candidate_detail", "retrieving"),
        ("get_upcoming_partner_events", "retrieving"),
        ("search_events", "retrieving"),
        ("knowledge_base_query", "retrieving"),
        ("analyze_attachment", "retrieving"),
        # analytics → visualizing
        ("get_recruitment_analytics_chart", "visualizing"),
        ("get_hiring_funnel_diagram", "visualizing"),
        ("recruiting_analytics", "visualizing"),
        ("pipeline_summary", "visualizing"),
        # jd drafting → drafting
        ("draft_job_from_text", "drafting"),
        ("draft_job_description", "drafting"),
        ("rewrite_job_description", "drafting"),
        ("check_jd_bias", "drafting"),
        ("draft_job_from_attachment", "drafting"),
        ("validate_job_draft", "drafting"),
        # confirmation writes → analyzing
        ("create_job", "analyzing"),
        ("move_candidate_stage", "analyzing"),
        # exports → exporting
        ("export_jobs", "exporting"),
        ("export_applications", "exporting"),
        ("export_interviews", "exporting"),
        ("export_offers", "exporting"),
        ("export_events", "exporting"),
        # media → generating_image
        ("generate_image", "generating_image"),
        # unknown / empty fail open to the safe generic
        ("some_future_tool", "retrieving"),
        ("", "retrieving"),
    ],
)
def test_phase_for_tool_mapping(name: str, phase: str) -> None:
    assert model_router.phase_for_tool(name) == phase
    assert model_router.phase_for_tool(name) in model_router.LEAK_SAFE_PHASES


def test_phase_is_never_a_tool_name() -> None:
    """A phase code must never collide with any registered tool name (leak-safety)."""
    tool_names = set(TOOL_SPECS)
    for name in tool_names:
        phase = model_router.phase_for_tool(name)
        assert phase in model_router.LEAK_SAFE_PHASES
        assert phase not in tool_names, f"phase {phase!r} for {name!r} leaks a tool name"


# --------------------------------------------------------------------------- #
# 2. Phase-event emission through the live loop                               #
# --------------------------------------------------------------------------- #


async def test_read_only_turn_emits_understanding_phase_composing(db_session, monkeypatch) -> None:
    _u, _org, admin = await make_partner(db_session)
    chat = await _chat(db_session, admin)
    _fake_dispatch_ok(monkeypatch)
    _script_model(
        monkeypatch,
        [
            _completion(tool_calls=[_tool_call("get_recruitment_analytics_chart")]),
            _completion(text="Đây là phễu tuyển dụng của bạn."),
        ],
    )

    events = await _drive(
        db_session, admin, chat, specs=available_specs(admin), script=None
    )

    # Exact leak-safe phase timeline: understanding → visualizing → composing.
    assert _statuses(events) == ["understanding", "visualizing", "composing"]

    # No status event ever carries a tool name; every code is leak-safe.
    tool_names = set(TOOL_SPECS)
    for ev in events:
        if ev["type"] == "status":
            assert ev["code"] in model_router.LEAK_SAFE_PHASES
            assert ev["code"] not in tool_names

    # The tool_call event is KEPT for internal/eval consumers (not user-facing).
    assert [e["name"] for e in events if e["type"] == "tool_call"] == [
        "get_recruitment_analytics_chart"
    ]
    # Final text streamed + terminal done.
    assert any(e["type"] == "token" for e in events)
    assert sum(1 for e in events if e["type"] == "done") == 1


async def test_confirmation_turn_emits_analyzing(db_session, monkeypatch) -> None:
    _u, _org, admin = await make_partner(db_session)
    chat = await _chat(db_session, admin)
    _script_model(
        monkeypatch,
        [
            _completion(
                tool_calls=[
                    _tool_call(
                        "create_job",
                        '{"title": "Backend Engineer", "description": "Build APIs."}',
                    )
                ]
            ),
        ],
    )

    events = await _drive(
        db_session, admin, chat, specs=available_specs(admin), script=None
    )

    # Confirmation path: understanding → analyzing, then the confirmation card as
    # the terminal done event (no final text streamed, no "composing").
    assert _statuses(events) == ["understanding", "analyzing"]
    assert not any(e["type"] == "token" for e in events)
    done = [e for e in events if e["type"] == "done"]
    assert len(done) == 1
    # Leak-safety on the status stream holds here too.
    tool_names = set(TOOL_SPECS)
    for ev in events:
        if ev["type"] == "status":
            assert ev["code"] not in tool_names


# --------------------------------------------------------------------------- #
# 3. Ungrounded-number telemetry flag                                         #
# --------------------------------------------------------------------------- #


async def test_ungrounded_numeric_flag_fires_on_no_tool_answer(db_session, monkeypatch) -> None:
    _u, _org, admin = await make_partner(db_session)
    chat = await _chat(db_session, admin)
    captured = _capture_guard_flags(monkeypatch)
    text = "Hiện tại tổ chức của bạn có 12 ứng viên đang chờ xử lý và tỷ lệ chuyển đổi là 30%."
    _script_model(monkeypatch, [_completion(text=text)])

    events = await _drive(db_session, admin, chat, specs=available_specs(admin), script=None)

    assert "ungrounded_numeric_suspected" in captured["guard_flags"]
    # Telemetry flag ONLY — the user-facing text is never scrubbed.
    done = [e for e in events if e["type"] == "done"][0]
    assert done["message"]["content"] == text


async def test_ungrounded_numeric_flag_silent_on_tool_grounded_answer(
    db_session, monkeypatch
) -> None:
    _u, _org, admin = await make_partner(db_session)
    chat = await _chat(db_session, admin)
    captured = _capture_guard_flags(monkeypatch)
    _fake_dispatch_ok(monkeypatch)
    _script_model(
        monkeypatch,
        [
            _completion(tool_calls=[_tool_call("get_recruitment_analytics_chart")]),
            # Same numeric claim, but now backed by a tool call this turn.
            _completion(text="Bạn có 12 ứng viên và tỷ lệ chuyển đổi 30%."),
        ],
    )

    await _drive(db_session, admin, chat, specs=available_specs(admin), script=None)

    assert "ungrounded_numeric_suspected" not in captured["guard_flags"]


async def test_ungrounded_numeric_flag_silent_on_plain_advice(db_session, monkeypatch) -> None:
    _u, _org, admin = await make_partner(db_session)
    chat = await _chat(db_session, admin)
    captured = _capture_guard_flags(monkeypatch)
    _script_model(
        monkeypatch,
        [_completion(text="Bạn nên phỏng vấn kỹ và đánh giá ứng viên một cách công bằng.")],
    )

    await _drive(db_session, admin, chat, specs=available_specs(admin), script=None)

    assert "ungrounded_numeric_suspected" not in captured["guard_flags"]


# --------------------------------------------------------------------------- #
# 4. Pure ungrounded-number detector                                          #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "text",
    [
        "Hiện tại có 12 ứng viên đang chờ.",
        "There are 5 candidates in the pipeline.",
        "Tỷ lệ chuyển đổi là 30%.",
        "Conversion rate is 42.5%.",
        "Mức lương khoảng 15 triệu.",
        "Ngân sách 1500 USD cho vai trò này.",
        "Bạn có 3 offers đang mở.",
        "Đã nhận 8 hồ sơ trong tuần này.",
    ],
)
def test_ungrounded_numeric_detector_fires(text: str) -> None:
    assert guardrails.has_ungrounded_numeric_claim(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "",
        "Bạn nên phỏng vấn kỹ và đánh giá ứng viên công bằng.",
        "Hãy chuẩn bị 3 câu hỏi phỏng vấn cho ứng viên.",  # 3 câu → not a data noun
        "Công ty được thành lập năm 2018.",  # year, not a metric
        "Cuộc phỏng vấn diễn ra lúc 9:00 sáng.",  # time
        "Quy trình gồm hai bước:\n1. Đăng tin tuyển dụng\n2. Sàng lọc hồ sơ",  # list ordinals
        # "5 năm" is experience, not a record count → must not fire.
        "Ứng viên có 5 năm kinh nghiệm thường là một gợi ý chung.",
    ],
)
def test_ungrounded_numeric_detector_conservative(text: str) -> None:
    assert guardrails.has_ungrounded_numeric_claim(text) is False
