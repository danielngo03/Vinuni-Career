"""Offline tests for the CV-JD fit EXPLANATION grounding safety net.

The deterministic matcher is authoritative: if it says a skill is matched
(including via synonyms/abbreviations like "k8s" == "Kubernetes"), the LLM
explanation layer must NEVER resurface that skill as a gap or tell the candidate
to add it. These tests exercise the ``semantic_scorer`` post-filter and the v2
prompt ground-truth block WITHOUT any real model calls — ``generate_json_note``
is monkeypatched to return a crafted (deliberately disobedient) dict.
"""

from __future__ import annotations

from app.ai.cv import semantic_scorer
from app.ai.prompts.cv_fit_analysis import v2, v3

_JOB: dict = {
    "id": "job-1",
    "title": "Platform Engineer",
    "required_skills": ["Kubernetes", "Python"],
    "preferred_skills": [],
}


def _fake_note(gaps: list[dict]):
    """Return an async stand-in for ``generate_json_note`` yielding ``gaps``."""

    async def _note(**_kwargs) -> dict:
        return {
            "score": 80,
            "summary": "Strong platform background.",
            "matched_evidence": [
                {
                    "requirement": "Kubernetes",
                    "cv_evidence": "k8s in production",
                    "strength": "strong",
                    "reasoning": "Ran k8s clusters.",
                }
            ],
            "gaps": gaps,
            "overall_suggestion": "Highlight cloud impact.",
        }

    return _note


async def test_matched_skill_never_resurfaces_as_gap(monkeypatch) -> None:
    """LLM wrongly lists 'Kubernetes' as a gap while it is a matched skill."""
    monkeypatch.setattr(
        semantic_scorer,
        "generate_json_note",
        _fake_note(
            [
                {
                    "requirement": "Kubernetes",
                    "cv_evidence": None,
                    "severity": "hard",
                    "reasoning": "Not found.",
                    "suggestion": "Add Kubernetes experience.",
                }
            ]
        ),
    )

    result = await semantic_scorer.analyze(
        job=_JOB,
        cv_text="Experienced engineer running k8s clusters in production.",
        cv_language="en",
        deterministic_score=80,
        matched_skills=["Kubernetes"],
        gaps=[],
    )

    gap_reqs = [g.requirement.lower() for g in result.gaps]
    assert "kubernetes" not in gap_reqs


async def test_synonym_gap_is_filtered(monkeypatch) -> None:
    """matched=['Kubernetes'], LLM gap requirement 'k8s' -> filtered out."""
    monkeypatch.setattr(
        semantic_scorer,
        "generate_json_note",
        _fake_note(
            [
                {
                    "requirement": "k8s",
                    "cv_evidence": None,
                    "severity": "soft",
                    "reasoning": "Not detected.",
                    "suggestion": "Learn k8s.",
                }
            ]
        ),
    )

    result = await semantic_scorer.analyze(
        job=_JOB,
        cv_text="Deployed services with Kubernetes.",
        cv_language="en",
        deterministic_score=75,
        matched_skills=["Kubernetes"],
        gaps=[],
    )

    gap_reqs = [g.requirement.lower() for g in result.gaps]
    assert "k8s" not in gap_reqs
    assert result.gaps == []


async def test_genuine_gap_survives(monkeypatch) -> None:
    """A gap NOT covered by matched skills ('Python') must survive the filter."""
    monkeypatch.setattr(
        semantic_scorer,
        "generate_json_note",
        _fake_note(
            [
                {
                    "requirement": "Python",
                    "cv_evidence": None,
                    "severity": "hard",
                    "reasoning": "No Python evidence.",
                    "suggestion": "Add Python projects.",
                }
            ]
        ),
    )

    result = await semantic_scorer.analyze(
        job=_JOB,
        cv_text="Deployed services with Kubernetes.",
        cv_language="en",
        deterministic_score=60,
        matched_skills=["Kubernetes"],
        gaps=["Python"],
    )

    gap_reqs = [g.requirement.lower() for g in result.gaps]
    assert "python" in gap_reqs


def test_v2_user_message_renders_already_satisfied_block() -> None:
    """The v2 template must surface passed matched skills in the ground-truth block."""
    msg = v2.build_user_message(
        job=_JOB,
        cv_evidence="k8s, python",
        deterministic_score=80,
        matched_skills=["Kubernetes", "Docker"],
        deterministic_gaps=["Go"],
        output_language="en",
    )

    assert "ALREADY-SATISFIED REQUIREMENTS" in msg
    assert "Kubernetes" in msg
    assert "Docker" in msg
    assert "CONFIRMED GAPS" in msg
    assert "Go" in msg


def test_v2_prompt_version_is_two() -> None:
    assert v2.PROMPT_VERSION == 2


def test_semantic_scorer_uses_v3_prompt() -> None:
    # The scorer now binds to v3 (requirement-centric, reuse-safe summary), so the
    # per-version explanation cache regenerates cleanly on the version bump.
    assert v3.PROMPT_VERSION == 3
    assert semantic_scorer.PROMPT_VERSION == 3
