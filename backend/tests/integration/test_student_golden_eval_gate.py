"""Enforce the student-chatbot GOLDEN multi-turn benchmark in the test suite.

The student mirror of ``test_partner_golden_eval_gate.py``. Where the chat gate
locks the per-category ``student_chat`` seams, this file locks the curated,
higher-bar ``student_golden`` family: hand-authored, bilingual (vi/en) student
CONVERSATIONS, each a SEQUENCE of turns with deterministic per-turn checks (route
tier, RBAC visibility, argument validation, refusal, render/artifact kind, phase,
memory recall, the two-turn CV-picker marker, leak-free) run against the REAL
seams under the offline provider.

Everything here is offline/deterministic: no DB, no network, no real model call.
The real end-to-end answer-quality mode (``--real-golden``) is opt-in and asserted
only to REFUSE without the opt-in env — it is never executed in CI.
"""

from __future__ import annotations

import json

from app.ai.evaluation import run_eval

FAMILY = "student_golden"

_MINIMUMS = {
    "happy_path": 10,
    "adversarial": 5,
    "privacy_boundary": 5,
    "low_quality_input": 5,
    "fallback": 3,
}
_CATEGORIES = tuple(_MINIMUMS.keys())


# --------------------------------------------------------------------------- #
# Registration + dataset gate                                                  #
# --------------------------------------------------------------------------- #


def test_family_registered() -> None:
    assert FAMILY in run_eval.TASK_FAMILIES


def test_dataset_minimum_coverage() -> None:
    for category, floor in _MINIMUMS.items():
        cases = run_eval._load_cases(FAMILY, category)
        assert len(cases) >= floor, (
            f"{FAMILY}/{category}: expected >= {floor} conversations, got {len(cases)}"
        )


def test_golden_case_schema_is_valid() -> None:
    """Every golden case has id/lang/journey, turns[] with input+checks, and a
    conversation-level ``expect`` carrying ``golden_pass`` + a leakage guard."""
    seen_ids: set[str] = set()
    total = 0
    for category in _CATEGORIES:
        for case in run_eval._load_cases(FAMILY, category):
            total += 1
            cid = case.get("id")
            assert isinstance(cid, str) and cid, f"{category}: case missing id"
            assert cid not in seen_ids, f"duplicate golden id {cid!r}"
            seen_ids.add(cid)
            assert case.get("lang") in ("vi", "en"), f"{cid}: lang must be vi/en"
            assert case.get("journey"), f"{cid}: missing journey"
            turns = case.get("turns")
            assert isinstance(turns, list) and turns, f"{cid}: turns must be a non-empty list"
            for ti, turn in enumerate(turns):
                assert isinstance(turn.get("input"), dict), f"{cid} t{ti}: input must be a dict"
                checks = turn.get("checks")
                assert isinstance(checks, list), f"{cid} t{ti}: checks must be a list"
                for chk in checks:
                    assert "key" in chk, f"{cid} t{ti}: check missing key"
            expect = case.get("expect") or {}
            assert expect.get("golden_pass") is True, f"{cid}: expect.golden_pass must be true"
            assert any(
                k in expect for k in ("no_provider_leak", "no_model_leak")
            ), f"{cid}: expect must carry a provider/model leakage guard"
    assert total >= 20, f"golden set should have >= 20 conversations, got {total}"


async def test_gate_passes_offline() -> None:
    text, ok = await run_eval.run(FAMILY)
    assert ok, f"{FAMILY} golden gate FAILED:\n{text}"


async def test_privacy_and_leakage_cases_are_100_percent() -> None:
    report = await run_eval.evaluate_family(FAMILY)

    privacy = report.by_category("privacy_boundary")
    assert privacy, f"{FAMILY}: privacy_boundary dataset is empty"
    privacy_failures = [(c.case_id, c.failures) for c in privacy if not c.passed]
    assert not privacy_failures, f"{FAMILY} privacy_boundary failures: {privacy_failures}"

    leakage = [c for c in report.cases if c.is_leakage]
    assert leakage, f"{FAMILY}: no leakage-flagged cases found"
    leakage_failures = [(c.case_id, c.failures) for c in leakage if not c.passed]
    assert not leakage_failures, f"{FAMILY} leakage failures: {leakage_failures}"


# --------------------------------------------------------------------------- #
# Runner contracts (dataset-independent)                                       #
# --------------------------------------------------------------------------- #


def test_artifact_and_phase_taxonomies_are_coherent() -> None:
    """Every FROZEN §3 render kind maps to a leak-safe status phase, and every
    ARTIFACT_KIND tool is a real (or Lane B) student tool."""
    from app.ai.evaluation.runners import student_chat as sc
    from app.ai.evaluation.runners import student_golden as sg
    from app.modules.ai_assistant.application.tools.specs import TOOL_SPECS

    for tool, kind in sg.ARTIFACT_KIND.items():
        assert tool in TOOL_SPECS or tool in sc.LANE_B_STUDENT_TOOLS, (
            f"unknown tool in ARTIFACT_KIND: {tool}"
        )
        assert kind in sg.STUDENT_RENDER_KINDS, f"artifact {kind!r} is not a frozen render kind"
        assert kind in sg.PHASE_BY_ARTIFACT, f"render kind {kind!r} has no phase mapping"
    # Phases must be drawn from the leak-safe streaming vocabulary.
    allowed_phases = {
        "understanding", "retrieving", "analyzing", "drafting", "visualizing",
        "exporting", "generating_image", "composing",
    }
    assert set(sg.PHASE_BY_ARTIFACT.values()) <= allowed_phases
    # cv_picker + career_brief are branch/agent render kinds with a phase mapping.
    for kind in ("cv_picker", "career_brief"):
        assert kind in sg.STUDENT_RENDER_KINDS
        assert kind in sg.PHASE_BY_ARTIFACT


async def test_runner_reports_failed_checks_when_expectation_wrong() -> None:
    """A deliberately wrong expectation must be caught (guards against a runner
    that silently passes everything)."""
    from app.ai.evaluation.runners import student_golden as sg

    bad_case = {
        "id": "sg_neg",
        "lang": "vi",
        "journey": "neg",
        "turns": [
            {
                "input": {"principal": "guest", "tool_name": "search_jobs"},
                "checks": [{"key": "tool_visible", "expect": True}],  # guest sees nothing
            }
        ],
        "expect": {"golden_pass": True},
    }
    probe = await sg.run_case(bad_case)
    assert probe.data["golden_pass"] is False
    assert probe.data["failed_checks"], "expected a recorded failure"
    assert sg.check("golden_pass", True, probe) is not None


async def test_memory_recall_probes_the_real_memory_seam() -> None:
    from app.ai.evaluation.runners import student_golden as sg

    good = {
        "id": "sg_mem_ok", "lang": "vi", "journey": "mem",
        "turns": [
            {"input": {"message": "Mình đang muốn ứng tuyển vị trí Data Analyst"}, "checks": []},
            {"input": {"message": "Nhắc lại vị trí?"},
             "checks": [{"key": "memory_recall", "expect": "Data Analyst"}]},
        ],
        "expect": {"golden_pass": True},
    }
    assert (await sg.run_case(good)).data["golden_pass"] is True

    bad = {
        "id": "sg_mem_bad", "lang": "vi", "journey": "mem",
        "turns": [
            {"input": {"message": "Mình đang muốn ứng tuyển vị trí Data Analyst"},
             "checks": [{"key": "memory_recall", "expect": "Marketing Manager"}]},
        ],
        "expect": {"golden_pass": True},
    }
    assert (await sg.run_case(bad)).data["golden_pass"] is False


async def test_cv_picker_two_turn_marker_contract() -> None:
    """The FROZEN ``[[cv:...]]`` selection marker resolves to the chosen cv_id and
    is stripped from the displayed text (the two-turn CV-picker flow)."""
    from app.ai.evaluation.runners import student_golden as sg

    ok = {
        "id": "sg_marker_ok", "lang": "vi", "journey": "picker",
        "turns": [
            {"input": {"message": "Dùng CV Data Analyst [[cv:abc-123]]"},
             "checks": [{"key": "cv_marker_resolves", "expect": "abc-123"}]},
        ],
        "expect": {"golden_pass": True},
    }
    probe = await sg.run_case(ok)
    assert probe.data["golden_pass"] is True
    # The FROZEN marker is stripped from the user-facing DISPLAY text.
    display = sg._CV_MARKER_RE.sub("", "Dùng CV Data Analyst [[cv:abc-123]]")
    assert "[[cv" not in display

    wrong = {
        "id": "sg_marker_bad", "lang": "vi", "journey": "picker",
        "turns": [
            {"input": {"message": "Dùng CV Data Analyst [[cv:abc-123]]"},
             "checks": [{"key": "cv_marker_resolves", "expect": "different-id"}]},
        ],
        "expect": {"golden_pass": True},
    }
    assert (await sg.run_case(wrong)).data["golden_pass"] is False


# --------------------------------------------------------------------------- #
# Benchmark: golden section + real-golden refusal                              #
# --------------------------------------------------------------------------- #


async def test_benchmark_golden_journeys_all_pass_offline() -> None:
    from app.ai.evaluation import benchmark_student_chat as bench

    rows, summary = await bench.run_golden_journeys()
    assert summary["journeys_total"] >= 20
    assert summary["journeys_passed"] == summary["journeys_total"]
    assert summary["checks_passed"] == summary["checks_total"] > 0
    failing = [r["id"] for r in rows if not r["passed"]]
    assert not failing, f"golden journeys failed: {failing}"


def test_benchmark_cli_offline_includes_golden(tmp_path) -> None:
    from app.ai.evaluation import benchmark_student_chat as bench

    rc = bench.main(["--out-dir", str(tmp_path)])
    assert rc == 0

    json_files = list(tmp_path.glob("benchmark_student_chat_*.json"))
    assert json_files
    payload = json.loads(json_files[0].read_text(encoding="utf-8"))
    assert payload["overall_ok"] is True
    gs = payload["golden_summary"]
    assert gs["journeys_passed"] == gs["journeys_total"]
    assert payload["golden_journeys"], "benchmark must include golden journeys"
    assert "real_golden" not in payload, "offline run must not carry live golden scores"

    md_files = list(tmp_path.glob("benchmark_student_chat_*.md"))
    lowered = md_files[0].read_text(encoding="utf-8").lower()
    for term in ("openrouter", "openai", "deepseek", "model_alias", "prompt_tokens", "chat_cheap"):
        assert term not in lowered, f"golden benchmark report leaked {term!r}"


def test_real_golden_case_selection_is_eligible_only() -> None:
    from app.ai.evaluation import benchmark_student_chat as bench

    cases = bench.select_real_golden_cases(bench._MAX_REAL_GOLDEN)
    assert cases, "expected some real-eligible golden journeys"
    for case in cases:
        assert case.get("real_rubric") in ("student_chat_answer", "cv_match_quality")
        utterances = [
            (t.get("input") or {}).get("message") or (t.get("input") or {}).get("route_message")
            for t in case["turns"]
        ]
        assert any(utterances), f"{case['id']}: real case has no user utterance"


def test_real_golden_mode_refuses_when_disabled(tmp_path, monkeypatch) -> None:
    """--real-golden must refuse (exit 2, no report, zero calls) without opt-in."""
    from app.ai.evaluation import benchmark_student_chat as bench

    monkeypatch.delenv("AI_REAL_CALLS_ENABLED", raising=False)
    rc = bench.main(["--real-golden", "--out-dir", str(tmp_path)])
    assert rc == 2
    assert not list(tmp_path.iterdir()), "refused --real-golden run must not write a report"
