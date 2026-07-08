"""Unit tests for the university operations deep-analysis workforce consumer
(§4.2 / WS3.4). Pure/offline: decomposition, synthesis, the deterministic-first
narrative gate, RBAC gate, and the tool-registry contract — no DB, no broker,
no real LLM.
"""

from __future__ import annotations

import uuid

import pytest
from app.ai.agents import operations_analysis as oa
from app.ai.agents.models import SubtaskStatus
from app.modules.ai_assistant.application.tools.dispatch import (
    SUPPORTED_TOOL_NAMES,
    authorize_tool,
)
from app.modules.ai_assistant.application.tools.specs import (
    UNIVERSITY_STAFF,
    TOOL_SPECS,
)
from app.shared.permissions import Principal

_NEW_TOOLS = ("start_operations_analysis", "get_operations_analysis")


# --------------------------------------------------------------------------- #
# Decomposition                                                               #
# --------------------------------------------------------------------------- #


def test_decompose_fans_out_one_subtask_per_fixed_pass() -> None:
    run_id, org_id = uuid.uuid4(), uuid.uuid4()
    subs = oa.decompose_operations_analysis(
        run_id=run_id,
        target_type=oa.TARGET_PARTNER_HIRING_QUALITY,
        target_org_id=org_id,
    )
    assert [s.key for s in subs] == list(oa.OPS_PASSES)
    assert {s.subtask_type for s in subs} == {oa.OPERATIONS_PASS_SUBTASK_TYPE}
    for s in subs:
        assert s.payload["pass"] == s.key
        assert s.payload["run_id"] == str(run_id)
        assert s.payload["target_org_id"] == str(org_id)


# --------------------------------------------------------------------------- #
# Synthesis (pure)                                                            #
# --------------------------------------------------------------------------- #


def _success(area: str, signals: dict, *, confidence: str = "high", narrative=None) -> dict:
    return {
        "status": SubtaskStatus.SUCCESS.value,
        "result": {
            "area": area,
            "signals": signals,
            "confidence": confidence,
            "narrative": narrative,
            "narrative_available": bool(narrative),
        },
        "error_code": None,
        "duration_ms": 3,
    }


def _all_passes_results() -> dict:
    return {
        "jobs_quality": _success(
            "jobs_quality",
            {"total_jobs": 12, "missing_deadline": 2, "by_status": {"active": 10}},
        ),
        "pipeline_health": _success(
            "pipeline_health",
            {"total_applications": 40, "hired": 0, "offers_accepted": 1},
        ),
        "outcomes": _success("outcomes", {"total_outcomes": 0, "by_trust_level": []}),
        "compliance_flags": _success(
            "compliance_flags",
            {"total_jobs": 12, "jobs_sent_back": 5, "moderation_flag_rate": 0.42},
        ),
    }


def test_synthesis_report_has_full_structured_shape() -> None:
    report = oa.synthesize_operations_report(_all_passes_results())
    assert set(report.keys()) == {
        "target",
        "summary",
        "findings",
        "recommendations",
        "caveats",
        "coverage",
    }
    assert report["target"] == {"type": oa.TARGET_PARTNER_HIRING_QUALITY}
    assert report["coverage"] == {
        "passes_total": 4,
        "passes_ok": 4,
        "passes_failed": 0,
        "narratives": 0,
    }
    assert len(report["findings"]) == 4
    for f in report["findings"]:
        assert set(f.keys()) == {"area", "signal", "evidence"}
        assert isinstance(f["signal"], str) and f["signal"]


def test_synthesis_derives_deterministic_recommendations() -> None:
    report = oa.synthesize_operations_report(_all_passes_results())
    joined = " ".join(report["recommendations"]).lower()
    # missing_deadline > 0, hired == 0 with applications, high send-back rate, 0 outcomes.
    assert "deadline" in joined
    assert "no hires" in joined
    assert "send-back rate" in joined
    assert "no graduate outcomes" in joined


def test_synthesis_partial_run_marks_failed_pass_as_caveat_not_finding() -> None:
    results = _all_passes_results()
    results["outcomes"] = {
        "status": SubtaskStatus.FAILED.value,
        "result": None,
        "error_code": "execution_error",
        "duration_ms": 2,
    }
    report = oa.synthesize_operations_report(results)
    assert report["coverage"]["passes_ok"] == 3
    assert report["coverage"]["passes_failed"] == 1
    assert len(report["findings"]) == 3
    assert not any(f["area"] == "outcomes" for f in report["findings"])
    assert any("could not be" in c.lower() for c in report["caveats"])


def test_synthesis_uses_narrative_when_present_else_deterministic_signal() -> None:
    results = _all_passes_results()
    results["jobs_quality"] = _success(
        "jobs_quality",
        {"total_jobs": 1, "missing_deadline": 1},
        confidence="low",
        narrative="Only one posting is live, so this read is tentative.",
    )
    report = oa.synthesize_operations_report(results)
    jq = next(f for f in report["findings"] if f["area"] == "jobs_quality")
    assert jq["signal"].startswith("Only one posting")
    assert report["coverage"]["narratives"] == 1


def test_synthesis_low_confidence_without_narrative_adds_caveat() -> None:
    results = _all_passes_results()
    results["outcomes"] = _success(
        "outcomes", {"total_outcomes": 0}, confidence="low", narrative=None
    )
    report = oa.synthesize_operations_report(results)
    assert any("low-confidence" in c.lower() for c in report["caveats"])


def test_synthesis_is_privacy_safe_no_leakage_tokens() -> None:
    report = oa.synthesize_operations_report(_all_passes_results())
    dumped = str(report).lower()
    for forbidden in (
        "openai",
        "anthropic",
        "gpt",
        "claude",
        "deepseek",
        "gemini",
        "api_key",
        "model_alias",
        "prompt_tokens",
    ):
        assert forbidden not in dumped


# --------------------------------------------------------------------------- #
# Narrative gate (deterministic-first; low-confidence only; metered)          #
# --------------------------------------------------------------------------- #


async def test_high_confidence_pass_never_calls_the_model(monkeypatch) -> None:
    called = {"n": 0}

    async def _fake_note(**_kwargs):  # pragma: no cover - must not run
        called["n"] += 1
        return {"narrative": "x"}

    monkeypatch.setattr(oa, "generate_json_note", _fake_note)
    principal = Principal(user_id=uuid.uuid4(), persona="university_staff", org_id=uuid.uuid4())
    out = await oa._maybe_narrate(
        None,
        principal,
        payload={"pass": "jobs_quality", "run_id": str(uuid.uuid4())},
        pass_result={"area": "jobs_quality", "signals": {"total_jobs": 12}, "confidence": "high"},
    )
    assert called["n"] == 0
    assert out["narrative"] is None
    assert out["narrative_available"] is False


async def test_low_confidence_pass_narrates_on_success(monkeypatch) -> None:
    async def _noop_enforce(*_a, **_k):
        return None

    async def _fake_note(**_kwargs):
        return {"narrative": "Sparse data — interpret with care."}

    monkeypatch.setattr(oa.energy_service, "enforce_energy", _noop_enforce)
    monkeypatch.setattr(oa, "generate_json_note", _fake_note)
    principal = Principal(user_id=uuid.uuid4(), persona="university_staff", org_id=uuid.uuid4())
    out = await oa._maybe_narrate(
        object(),
        principal,
        payload={"pass": "outcomes", "run_id": str(uuid.uuid4())},
        pass_result={"area": "outcomes", "signals": {"total_outcomes": 0}, "confidence": "low"},
    )
    assert out["narrative"] == "Sparse data — interpret with care."
    assert out["narrative_available"] is True


async def test_low_confidence_pass_degrades_when_ai_unavailable(monkeypatch) -> None:
    from app.shared.exceptions import AIUnavailableError

    async def _noop_enforce(*_a, **_k):
        return None

    async def _boom(**_kwargs):
        raise AIUnavailableError()

    monkeypatch.setattr(oa.energy_service, "enforce_energy", _noop_enforce)
    monkeypatch.setattr(oa, "generate_json_note", _boom)
    principal = Principal(user_id=uuid.uuid4(), persona="university_staff", org_id=uuid.uuid4())
    out = await oa._maybe_narrate(
        object(),
        principal,
        payload={"pass": "outcomes", "run_id": str(uuid.uuid4())},
        pass_result={"area": "outcomes", "signals": {"total_outcomes": 0}, "confidence": "low"},
    )
    assert out["narrative"] is None
    assert out["narrative_available"] is False


def test_clean_narrative_drops_leaky_or_nonstring_text() -> None:
    assert oa._clean_narrative(None) is None
    assert oa._clean_narrative(123) is None
    assert oa._clean_narrative("Answered by gpt-4o.") is None
    assert oa._clean_narrative("  A tentative read.  ") == "A tentative read."


# --------------------------------------------------------------------------- #
# RBAC — pure defense-in-depth gate                                           #
# --------------------------------------------------------------------------- #


def test_may_analyze_partner_requires_university_and_grant() -> None:
    superadmin = Principal(user_id=uuid.uuid4(), persona="superadmin", is_superadmin=True)
    assert oa._may_analyze_partner(superadmin) is True

    granted = Principal(
        user_id=uuid.uuid4(),
        persona="university_staff",
        org_id=uuid.uuid4(),
        permissions=frozenset({"partners:read"}),
    )
    assert oa._may_analyze_partner(granted) is True

    ungranted = Principal(
        user_id=uuid.uuid4(), persona="university_staff", org_id=uuid.uuid4()
    )
    assert oa._may_analyze_partner(ungranted) is False

    partner = Principal(
        user_id=uuid.uuid4(),
        persona="partner_member",
        org_id=uuid.uuid4(),
        permissions=frozenset({"partners:read"}),
    )
    assert oa._may_analyze_partner(partner) is False

    guest = Principal(user_id=None, persona="guest")
    assert oa._may_analyze_partner(guest) is False


# --------------------------------------------------------------------------- #
# Tool registry / dispatch RBAC for the two new chat tools                    #
# --------------------------------------------------------------------------- #


def _university(perms: set[str] | None = None) -> Principal:
    return Principal(
        user_id=uuid.uuid4(),
        persona="university_staff",
        org_id=uuid.uuid4(),
        permissions=frozenset(perms or set()),
    )


def test_new_tools_registered_and_dispatchable() -> None:
    for name in _NEW_TOOLS:
        assert name in TOOL_SPECS
        assert name in SUPPORTED_TOOL_NAMES


def test_new_tools_declare_full_contract() -> None:
    for name in _NEW_TOOLS:
        spec = TOOL_SPECS[name]
        assert spec.persona == [UNIVERSITY_STAFF]
        assert spec.permission_class == "read_only"
        assert "partners:read" in spec.required_permissions
        assert "role:university_staff" in spec.required_permissions
        assert spec.audit_event_type.startswith("TOOL_")
        assert spec.fallback.strip()


def test_new_tools_authorized_only_for_granted_university_or_superadmin() -> None:
    granted = _university({"partners:read"})
    ungranted = _university(set())
    student = Principal(user_id=uuid.uuid4(), persona="student")
    partner = Principal(
        user_id=uuid.uuid4(),
        persona="partner_member",
        org_id=uuid.uuid4(),
        permissions=frozenset({"partners:read"}),
    )
    superadmin = Principal(
        user_id=uuid.uuid4(),
        persona="superadmin",
        is_superadmin=True,
        permissions=frozenset({"*"}),
    )
    for name in _NEW_TOOLS:
        spec = TOOL_SPECS[name]
        assert authorize_tool(spec, granted) is True, name
        assert authorize_tool(spec, ungranted) is False, name
        assert authorize_tool(spec, student) is False, name
        assert authorize_tool(spec, partner) is False, name
        assert authorize_tool(spec, superadmin) is True, name


@pytest.mark.parametrize(
    "target_type,expected",
    [(oa.TARGET_PARTNER_HIRING_QUALITY, True), ("something_else", False)],
)
def test_supported_targets(target_type: str, expected: bool) -> None:
    assert (target_type in oa.SUPPORTED_TARGETS) is expected
