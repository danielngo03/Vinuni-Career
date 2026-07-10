"""Enforce the offline AI evaluation gate in the test suite.

This makes the documented CI gate (``docs/AI_PRODUCT_SPEC.md`` §10.1) a real,
enforced check rather than a loose script: the gate is run under the deterministic
OFFLINE provider (no network, no keys) and must pass — privacy/leakage cases at
100% and happy-path at or above the documented threshold. If a future change
regresses a dataset expectation, this test fails.

It is fast: no DB, no fixtures, pure in-process evaluation of the datasets.
"""

from __future__ import annotations

import subprocess
import sys

import pytest
from app.ai.evaluation import run_eval


@pytest.mark.parametrize("family", list(run_eval.TASK_FAMILIES))
async def test_each_family_has_full_dataset_coverage(family: str) -> None:
    """Every family ships all 5 standard categories at the §10.1 minimum counts."""

    minimums = {
        "happy_path": 10,
        "adversarial": 5,
        "privacy_boundary": 5,
        "low_quality_input": 5,
        "fallback": 3,
    }
    for category, floor in minimums.items():
        cases = run_eval._load_cases(family, category)
        assert len(cases) >= floor, (
            f"{family}/{category}: expected >= {floor} cases, got {len(cases)}"
        )


async def test_gate_passes_offline_for_all_families() -> None:
    """The full gate (all families) is green under the offline provider."""

    text, ok = await run_eval.run("all")
    assert ok, f"AI eval gate FAILED:\n{text}"


@pytest.mark.parametrize("family", list(run_eval.TASK_FAMILIES))
async def test_privacy_and_leakage_cases_are_100_percent(family: str) -> None:
    """Privacy-boundary and any leakage-flagged case must be 100% pass."""

    report = await run_eval.evaluate_family(family)

    privacy = report.by_category("privacy_boundary")
    assert privacy, f"{family}: privacy_boundary dataset is empty"
    privacy_failures = [(c.case_id, c.failures) for c in privacy if not c.passed]
    assert not privacy_failures, f"{family} privacy_boundary failures: {privacy_failures}"

    leakage = [c for c in report.cases if c.is_leakage]
    assert leakage, f"{family}: no leakage-flagged cases found"
    leakage_failures = [(c.case_id, c.failures) for c in leakage if not c.passed]
    assert not leakage_failures, f"{family} leakage failures: {leakage_failures}"


@pytest.mark.parametrize("family", list(run_eval.TASK_FAMILIES))
async def test_happy_path_meets_threshold(family: str) -> None:
    """Happy-path pass rate is at or above the documented threshold (80%)."""

    report = await run_eval.evaluate_family(family)
    passed, total, ok = run_eval._category_verdict(report, "happy_path")
    assert total > 0, f"{family}: happy_path dataset is empty"
    rate = passed / total
    assert ok and rate >= run_eval.HAPPY_PATH_THRESHOLD, (
        f"{family} happy_path pass rate {rate:.0%} < {run_eval.HAPPY_PATH_THRESHOLD:.0%}"
    )


def test_cli_entrypoint_exits_zero_when_green() -> None:
    """``python -m app.ai.evaluation.run_eval`` returns exit 0 and leaks nothing."""
    import pathlib

    backend_dir = pathlib.Path(__file__).resolve().parents[2]

    proc = subprocess.run(
        [sys.executable, "-m", "app.ai.evaluation.run_eval", "--task-family", "all"],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(backend_dir),
    )
    assert proc.returncode == 0, f"gate exited {proc.returncode}:\n{proc.stdout}\n{proc.stderr}"
    assert "OVERALL: PASS" in proc.stdout
    # The CLI output must never expose provider/model/token internals.
    lowered = proc.stdout.lower()
    for term in ("openrouter", "openai", "deepseek", "model_alias", "prompt_tokens"):
        assert term not in lowered, f"gate output leaked {term!r}"


# --------------------------------------------------------------------------- #
# Mock-interview eval families (turn brain + grounding) — added coverage.       #
# These two families closed the biggest offline-eval gap (the conversational    #
# interviewer had ZERO offline eval). They EXCEED the §10.1 minimum counts and  #
# each pass the offline gate green on their own; assert both explicitly so a    #
# regression is caught even while the full-gate test is parametrized broadly.   #
# --------------------------------------------------------------------------- #

_INTERVIEW_FAMILY_TARGETS = {
    "mock_interview_turn": {
        "happy_path": 15,
        "adversarial": 10,
        "privacy_boundary": 8,
        "low_quality_input": 6,
        "fallback": 5,
    },
    "interview_grounding": {
        "happy_path": 12,
        "adversarial": 6,
        "privacy_boundary": 6,
        "low_quality_input": 6,
        "fallback": 3,
    },
}


def test_new_interview_families_are_registered() -> None:
    """The two new interview eval families are wired into the dispatch tables."""

    for family in _INTERVIEW_FAMILY_TARGETS:
        assert family in run_eval.TASK_FAMILIES, f"{family} not registered"


@pytest.mark.parametrize("family", list(_INTERVIEW_FAMILY_TARGETS))
def test_new_interview_families_exceed_target_counts(family: str) -> None:
    """The interview families ship the higher target counts, not just the floor."""

    for category, target in _INTERVIEW_FAMILY_TARGETS[family].items():
        cases = run_eval._load_cases(family, category)
        assert len(cases) >= target, (
            f"{family}/{category}: expected >= {target} cases, got {len(cases)}"
        )


@pytest.mark.parametrize("family", list(_INTERVIEW_FAMILY_TARGETS))
async def test_new_interview_families_pass_offline_gate(family: str) -> None:
    """Each interview family is green under the offline provider and leaks nothing."""

    text, ok = await run_eval.run(family)
    assert ok, f"{family} eval gate FAILED:\n{text}"
    lowered = text.lower()
    for term in ("openrouter", "openai", "deepseek", "gpt-4", "model_alias", "prompt_tokens"):
        assert term not in lowered, f"{family} gate output leaked {term!r}"
