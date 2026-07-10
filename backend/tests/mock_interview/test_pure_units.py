"""Pure unit tests for the mock-interview module — no DB, no provider.

Covers the deterministic, offline-safe pieces:
- ``caps`` clamps (question count + duration bounds);
- ``report_service.normalize_report`` (no-score invariant, whitelisted shape,
  degrade-to-fallback on empty/garbage) and ``_parse_json`` (fenced JSON + raises);
- ``conversation_service.strip_end_marker`` + ``build_transcript_lines``;
- the ``prompts.mock_interview.v1`` grounding / safety / no-score / localization
  invariants.
"""

from __future__ import annotations

import pytest
from app.ai.prompts.mock_interview import v1 as prompts
from app.modules.mock_interview.application import (
    caps,
    conversation_service,
    report_service,
)
from app.modules.mock_interview.domain.models import (
    SPEAKER_CANDIDATE,
    SPEAKER_INTERVIEWER,
    MockInterviewTurn,
)
from app.shared.exceptions import AIUnavailableError

_SCORE_KEYS = ("score", "rating", "grade")


# --------------------------------------------------------------------------- #
# caps                                                                         #
# --------------------------------------------------------------------------- #
def test_cap_constants_match_spec() -> None:
    assert caps.DAILY_SESSION_CAP == 3
    assert caps.WEEKLY_SESSION_CAP == 10
    assert caps.MAX_CONCURRENT_PER_USER == 1
    assert caps.MAX_SESSION_SECONDS == 600


@pytest.mark.parametrize(
    ("value", "expected"),
    [(-5, 3), (0, 3), (1, 3), (3, 3), (6, 6), (12, 12), (13, 12), (999, 12)],
)
def test_clamp_questions_bounds(value: int, expected: int) -> None:
    assert caps.clamp_questions(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [(-10, 0), (0, 0), (120, 120), (600, 600), (601, 600), (10_000, 600)],
)
def test_clamp_duration_bounds(value: int, expected: int) -> None:
    assert caps.clamp_duration(value) == expected


# --------------------------------------------------------------------------- #
# report_service.normalize_report — NO-SCORE invariant                         #
# --------------------------------------------------------------------------- #
def test_normalize_report_drops_score_rating_grade() -> None:
    raw = {
        "per_question": [
            {
                "question": "Tell me about a project",
                "suggestion": "Use STAR",
                "observation": "Answer lacked metrics",
                "score": 7,  # must be dropped
            }
        ],
        "overall_observations": "Solid effort overall.",
        "gaps_to_work_on": ["System design depth"],
        "strengths": ["Clear communication"],
        # top-level score-like fields the model must never leak downstream:
        "score": 88,
        "rating": "A-",
        "grade": 90,
        "percentage": 88.0,
    }
    out = report_service.normalize_report(raw)

    # No score/rating/grade anywhere in the normalized output.
    for key in _SCORE_KEYS:
        assert key not in out
    assert "percentage" not in out
    assert "score" not in out["per_question"][0]

    # Whitelisted shape only.
    assert set(out.keys()) == {
        "per_question",
        "overall_observations",
        "gaps_to_work_on",
        "strengths",
        "prompt_version",
        "is_fallback",
    }
    assert out["per_question"][0] == {
        "question": "Tell me about a project",
        "suggestion": "Use STAR",
        "observation": "Answer lacked metrics",
    }
    assert out["overall_observations"] == "Solid effort overall."
    assert out["is_fallback"] is False
    assert out["prompt_version"] == prompts.PROMPT_VERSION


def test_normalize_report_empty_dict_raises() -> None:
    with pytest.raises(AIUnavailableError):
        report_service.normalize_report({})


def test_normalize_report_garbage_dict_raises() -> None:
    # Keys the model might hallucinate but none of the whitelisted content.
    with pytest.raises(AIUnavailableError):
        report_service.normalize_report({"foo": "bar", "score": 100})


# --------------------------------------------------------------------------- #
# report_service._parse_json                                                   #
# --------------------------------------------------------------------------- #
def test_parse_json_handles_fenced_json_block() -> None:
    text = '```json\n{"overall_observations": "ok", "gaps_to_work_on": []}\n```'
    assert report_service._parse_json(text) == {
        "overall_observations": "ok",
        "gaps_to_work_on": [],
    }


def test_parse_json_handles_bare_fence() -> None:
    assert report_service._parse_json('```\n{"a": 1}\n```') == {"a": 1}


def test_parse_json_handles_surrounding_prose() -> None:
    # find('{')..rfind('}') tolerates leading/trailing chatter around the object.
    assert report_service._parse_json('Here you go: {"a": 1} thanks') == {"a": 1}


@pytest.mark.parametrize("bad", ["", None, "no json here", "{not valid json}", "[1, 2, 3]"])
def test_parse_json_raises_on_non_object(bad: str | None) -> None:
    with pytest.raises(AIUnavailableError):
        report_service._parse_json(bad)


# --------------------------------------------------------------------------- #
# conversation_service pure helpers                                            #
# --------------------------------------------------------------------------- #
def test_strip_end_marker_detects_end() -> None:
    clean, ended = conversation_service.strip_end_marker(
        "Thanks, that's all for today. [END]"
    )
    assert ended is True
    assert "[END]" not in clean
    assert clean == "Thanks, that's all for today."


def test_strip_end_marker_no_marker() -> None:
    clean, ended = conversation_service.strip_end_marker("Tell me more.")
    assert ended is False
    assert clean == "Tell me more."


def test_build_transcript_lines_renders_roles() -> None:
    turns = [
        MockInterviewTurn(seq=1, speaker=SPEAKER_INTERVIEWER, text="Introduce yourself."),
        MockInterviewTurn(seq=2, speaker=SPEAKER_CANDIDATE, text="I am a CS student."),
        MockInterviewTurn(seq=3, speaker=SPEAKER_CANDIDATE, text="   "),  # blank -> skipped
    ]
    lines = conversation_service.build_transcript_lines(turns)
    assert lines == [
        "Interviewer: Introduce yourself.",
        "Candidate: I am a CS student.",
    ]


def test_build_transcript_lines_empty() -> None:
    assert conversation_service.build_transcript_lines([]) == []


# --------------------------------------------------------------------------- #
# prompts.mock_interview.v1                                                     #
# --------------------------------------------------------------------------- #
def _grounding(locale: str = "en") -> dict:
    return {
        "locale": locale,
        "job": {
            "title": "Backend Engineer",
            "company_name": "Acme Corp",
            "description": "Build and operate REST APIs.",
            "requirements": ["Strong Python and FastAPI experience"],
            "required_skills": ["Python", "FastAPI"],
            "seniority_level": "junior",
            "experience": "1-2 years",
        },
        "cv": {
            "title": "CS Intern CV",
            "language": "en",
            "highlights": ["[experience] Built async workers with Celery"],
            "skills": ["Python", "SQL"],
        },
        "matched_skills": ["Python"],
        "gaps": ["Kubernetes"],
    }


def test_conversation_prompt_contains_jd_and_cv_grounding() -> None:
    system = prompts.build_conversation_system_prompt(_grounding(), target_questions=6)
    # JD grounding present.
    assert "Backend Engineer" in system
    assert "Acme Corp" in system
    assert "Python" in system
    assert "Strong Python and FastAPI experience" in system
    # CV grounding present.
    assert "Built async workers with Celery" in system
    # Target injected.
    assert "6 questions" in system


def test_conversation_prompt_has_no_score_and_safety_rules() -> None:
    system = prompts.build_conversation_system_prompt(_grounding(), target_questions=6)
    # No-score / practice-not-evaluation rule.
    assert "do NOT score" in system
    assert "PRACTICE, not evaluation" in system
    # Protected-characteristics safety rule.
    assert "NEVER ask about age" in system
    assert "protected" in system
    # Do-not-reveal-model rule.
    assert "AI/model" in system


def test_conversation_prompt_language_switches_with_locale() -> None:
    vi = prompts.build_conversation_system_prompt(_grounding("vi"), target_questions=5)
    en = prompts.build_conversation_system_prompt(_grounding("en"), target_questions=5)
    # v2: the interview is CONDUCTED in the session language (switches per locale),
    # but the old hard "Speak ONLY in {language}" single-language rule was relaxed
    # into natural code-switching + candidate-mirroring.
    assert "Conduct the interview in Vietnamese" in vi
    assert "Conduct the interview in English" in en
    assert "Speak ONLY in" not in vi and "Speak ONLY in" not in en
    assert "original form" in vi and "Mirror the candidate" in vi


def test_report_prompt_forbids_scores() -> None:
    system = prompts.build_report_system_prompt("en")
    assert "NO numeric score" in system
    assert "grade" in system
    assert "ranking" in system
    # Anti-fabrication rule.
    assert "do not invent" in system


def test_static_fallback_report_has_no_score_fields() -> None:
    for locale in ("vi", "en"):
        report = prompts.static_fallback_report(_grounding(locale))
        for key in _SCORE_KEYS:
            assert key not in report
        assert set(report.keys()) == {
            "per_question",
            "overall_observations",
            "gaps_to_work_on",
            "strengths",
        }
        # The deterministic report reuses the JD gaps so it stays useful.
        assert report["gaps_to_work_on"]


def test_static_fallback_report_is_localized() -> None:
    vi = prompts.static_fallback_report(_grounding("vi"))
    en = prompts.static_fallback_report(_grounding("en"))
    assert vi["overall_observations"] != en["overall_observations"]
    assert "STAR" in vi["overall_observations"]  # method name kept in both
    assert "Situation" in en["overall_observations"]
    # Vietnamese diacritics only on the vi branch.
    assert "hoàn tất" in vi["overall_observations"]


def test_fallback_first_turn_is_localized() -> None:
    vi = prompts.fallback_first_turn(_grounding("vi"))
    en = prompts.fallback_first_turn(_grounding("en"))
    assert vi != en
    assert "Xin chào" in vi
    assert vi != ""
    assert en.startswith("Hi, thanks")
    # Grounds on the job title.
    assert "Backend Engineer" in en


def test_fallback_next_turn_is_localized() -> None:
    vi = prompts.fallback_next_turn(_grounding("vi"))
    en = prompts.fallback_next_turn(_grounding("en"))
    assert vi != en
    assert "Cảm ơn" in vi
    assert en.startswith("Thank you")
