"""Task C: surface the STRUCTURED matching suggestions that used to be discarded,
consolidate the fit contract, and close the gap -> CV-Studio improvement loop.

All offline (no real-model calls): ``semantic_scorer.analyze`` is monkeypatched to
return a fully-populated ``SemanticFitResult`` (matched evidence + gaps with
per-requirement suggestions + overall suggestion), and both AI gates are forced on.

Asserts:
(a) the on-demand analysis sub-call returns STRUCTURED suggestions + evidence
    strength + overall suggestion (not just the free-text summary), persisted so a
    reload reuses them without re-invoking the model;
(b) the authoritative default load (student-intelligence) returns deterministic fit
    WITHOUT triggering the model, and carries the gap -> CV-Studio hand-off;
(c) the gap -> CV-Studio hand-off payload is well-formed + confirmation-gated;
(d) no provider/model/token/confidence/embedding leakage.
"""

from __future__ import annotations

import json
import uuid

from app.ai.cv import semantic_scorer, skill_translation
from app.modules.documents.application import cv_gap_handoff, job_fit_service
from app.modules.opportunities.application import student_intelligence_service

from tests.documents_utils import make_student
from tests.integration.test_cv_job_fit import _build_strong_cv, _create_job

_FORBIDDEN = [
    "openrouter", "openai", "anthropic", "claude", "gpt-4", "gemini", "deepseek",
    "chat_cheap", "reasoning_cheap", "model_alias", "prompt_tokens",
    "completion_tokens", "storage_path", "storage_key", "confidence", "embedding",
    "rank", "percentile", "temperature", "max_tokens", "api_key",
]


def _assert_no_leak(payload: object) -> None:
    blob = json.dumps(payload, ensure_ascii=False).lower()
    for term in _FORBIDDEN:
        assert term not in blob, f"leaked term: {term!r}"


class _StructuredSemantic:
    """Counting stand-in for ``semantic_scorer.analyze`` that returns the FULL
    structured result (matched evidence + gaps w/ suggestions + overall)."""

    def __init__(self) -> None:
        self.calls = 0

    async def analyze(
        self,
        *,
        job: dict,
        cv_text: str,
        cv_language: str,
        deterministic_score: int,
        matched_skills: list[str],
        gaps: list[str],
    ) -> semantic_scorer.SemanticFitResult:
        self.calls += 1
        return semantic_scorer.SemanticFitResult(
            score=deterministic_score,
            summary="Strong Python/FastAPI backend match for this internship.",
            matched_evidence=[
                semantic_scorer.MatchedEvidence(
                    requirement="Python",
                    cv_evidence="Built REST APIs with Python and FastAPI",
                    strength="strong",
                    reasoning="Hands-on backend delivery at a startup.",
                )
            ],
            gaps=[
                semantic_scorer.MatchGap(
                    requirement="Kubernetes",
                    cv_evidence=None,
                    severity="hard",
                    reasoning="No container-orchestration evidence in the CV.",
                    suggestion="Add a project deploying a service to Kubernetes, "
                    "if you have genuine experience with it.",
                )
            ],
            overall_suggestion="Highlight cloud/infra impact to close the platform gap.",
        )


def _enable_ai(monkeypatch, fake: _StructuredSemantic) -> None:
    monkeypatch.setattr(job_fit_service, "real_provider_active", lambda: True)

    class _Cfg:
        job_fit_ai_explanation_enabled = True

    monkeypatch.setattr(job_fit_service.runtime_config, "current", lambda: _Cfg())
    monkeypatch.setattr(semantic_scorer, "analyze", fake.analyze)
    # Keep the cross-lingual tier off so deterministic matched/gaps stay lexical.
    monkeypatch.setattr(skill_translation, "real_provider_active", lambda: False)


async def _gap_job(db) -> uuid.UUID:
    """A job whose required skills include one the strong CV lacks (Kubernetes)."""
    return await _create_job(
        db,
        required_skills=["Python", "FastAPI", "Kubernetes"],
        preferred_skills=["PostgreSQL"],
    )


# --------------------------------------------------------------------------- #
# (a) Structured suggestions + evidence strength + overall are surfaced        #
# --------------------------------------------------------------------------- #


async def test_analysis_returns_structured_suggestions_not_just_summary(
    db_session, monkeypatch
) -> None:
    _u, student = await make_student(db_session)
    cv_id = await _build_strong_cv(db_session, student)
    job_id = await _gap_job(db_session)

    fake = _StructuredSemantic()
    _enable_ai(monkeypatch, fake)

    out = await job_fit_service.fit_explanation_for_job(
        db_session, principal=student, job_id=job_id, cv_id=None, locale="en",
    )

    # Free-text summary still present (backward compat).
    assert out["explanation"]
    assert out["ai_explanation_available"] is True
    assert out["cv_id"] == cv_id
    assert fake.calls == 1

    # STRUCTURED analysis surfaced (previously discarded).
    analysis = out["analysis"]
    assert analysis is not None
    assert analysis["overall_suggestion"]
    assert analysis["matched_evidence"], "matched evidence must be surfaced"
    me = analysis["matched_evidence"][0]
    assert me["requirement"] == "Python"
    assert me["evidence_strength"] == "strong"  # evidence STRENGTH exposed
    assert analysis["gaps"], "structured gaps must be surfaced"
    g = analysis["gaps"][0]
    assert g["requirement"] == "Kubernetes"
    assert g["severity"] == "hard"
    assert g["suggestion"], "per-requirement suggestion must survive"

    _assert_no_leak(out)


async def test_analysis_reuses_persisted_structured_no_second_model_call(
    db_session, monkeypatch
) -> None:
    """A reload returns the SAME structured analysis from the row — no re-invoke."""
    _u, student = await make_student(db_session)
    await _build_strong_cv(db_session, student)
    job_id = await _gap_job(db_session)

    fake = _StructuredSemantic()
    _enable_ai(monkeypatch, fake)

    first = await job_fit_service.fit_explanation_for_job(
        db_session, principal=student, job_id=job_id, locale="en",
    )
    assert first["analysis"] is not None
    assert fake.calls == 1

    second = await job_fit_service.fit_explanation_for_job(
        db_session, principal=student, job_id=job_id, locale="en",
    )
    # Structured detail is persisted + reused; the model is NOT called again.
    assert fake.calls == 1
    assert second["analysis"] == first["analysis"]
    assert second["explanation"] == first["explanation"]


# --------------------------------------------------------------------------- #
# (b) Authoritative default load = deterministic, no model, carries hand-off    #
# --------------------------------------------------------------------------- #


async def test_default_intelligence_load_is_deterministic_and_carries_handoff(
    db_session, monkeypatch
) -> None:
    _u, student = await make_student(db_session)
    cv_id = await _build_strong_cv(db_session, student)
    job_id = await _gap_job(db_session)

    fake = _StructuredSemantic()
    _enable_ai(monkeypatch, fake)

    out = await student_intelligence_service.student_intelligence_for_job(
        db_session, principal=student, job_id=job_id, cv_id=None, locale="en",
    )

    # Deterministic fit returns; the model is NEVER invoked on the default load.
    assert out["fit"]["status"] == "scored"
    assert out["fit"]["score"] is not None
    assert out["fit"].get("explanation") is None
    assert fake.calls == 0

    # Each learning gap carries a confirmation-gated CV-Studio hand-off.
    assert out["learning_gaps"], "the Kubernetes gap should surface a learning gap"
    handoff = out["learning_gaps"][0]["cv_edit"]
    assert handoff is not None
    assert handoff["action"] == "cv_edit_command"
    assert handoff["cv_id"] == cv_id
    assert "ai-edit-command" in handoff["endpoint"]
    assert handoff["requires_confirmation"] is True
    assert handoff["request"]["instruction"]

    _assert_no_leak(out)


async def test_fit_explanation_improvements_present_even_when_ai_off(
    db_session,
) -> None:
    """The gap -> CV-Studio hand-off is deterministic: it works with the AI off."""
    _u, student = await make_student(db_session)
    cv_id = await _build_strong_cv(db_session, student)
    job_id = await _gap_job(db_session)

    # Default offline provider (no gate patching) -> AI narrative unavailable.
    out = await job_fit_service.fit_explanation_for_job(
        db_session, principal=student, job_id=job_id, locale="en",
    )
    assert out["explanation"] is None
    assert out["analysis"] is None
    assert out["ai_explanation_available"] is False
    # ...but the closed-loop improvement hand-offs are still built from the
    # deterministic gaps.
    assert out["improvements"], "improvements must not depend on the AI narrative"
    imp = out["improvements"][0]
    assert imp["action"] == "cv_edit_command"
    assert imp["cv_id"] == cv_id
    assert imp["requires_confirmation"] is True
    assert "ai-edit-command" in imp["endpoint"]


# --------------------------------------------------------------------------- #
# (b2) Learning resources from fit gaps (WS-15) — internal, deterministic, free  #
# --------------------------------------------------------------------------- #


async def test_fit_explanation_carries_internal_learning_resources(db_session) -> None:
    """Each deterministic fit gap surfaces an INTERNAL curated learning focus.

    Deterministic (no AI gate patched) -> the AI narrative is unavailable, but the
    learning-resource mapping is model-free and must still be present.
    """
    _u, student = await make_student(db_session)
    await _build_strong_cv(db_session, student)
    job_id = await _gap_job(db_session)  # requires Kubernetes; the CV lacks it

    out = await job_fit_service.fit_explanation_for_job(
        db_session, principal=student, job_id=job_id, locale="en",
    )

    # AI narrative is off, yet the deterministic learning resources are present.
    assert out["ai_explanation_available"] is False
    assert out["learning_resources"], "the Kubernetes gap must map to a resource"
    res = out["learning_resources"][0]
    assert set(res.keys()) == {"skill", "resource_type", "suggestion"}
    assert res["skill"].lower() == "kubernetes"
    # Kubernetes -> containers template -> hands-on lab (a real, specific resource
    # type, not the generic fallback).
    assert res["resource_type"] == "hands_on_lab"
    assert "Kubernetes" in res["suggestion"] or "kubernetes" in res["suggestion"].lower()

    # No external scraping / fabricated URLs, and no provider/model leakage.
    blob = json.dumps(out["learning_resources"], ensure_ascii=False)
    assert "http://" not in blob and "https://" not in blob and "www." not in blob
    _assert_no_leak(out)


async def test_fit_explanation_learning_resources_empty_without_gaps(db_session) -> None:
    """A CV that fully covers the job's required skills has no gaps -> [] (honest)."""
    from tests.integration.test_cv_job_fit import _create_job

    _u, student = await make_student(db_session)
    await _build_strong_cv(db_session, student)
    # Default job requires only Python + FastAPI, both present in the strong CV.
    job_id = await _create_job(db_session)

    out = await job_fit_service.fit_explanation_for_job(
        db_session, principal=student, job_id=job_id, locale="en",
    )
    assert out["learning_resources"] == []


def test_learning_resources_mapping_is_pure_and_url_free() -> None:
    """The helper maps gap skills -> internal resources with de-dupe + no URLs."""
    out = job_fit_service._learning_resources_from_gaps(
        ["Docker", "docker", "AWS", "React", "  ", "SomeUnknownSkill"],
        locale="en",
    )
    skills = [r["skill"] for r in out]
    # Case-insensitive de-dupe of Docker/docker; blank dropped.
    assert skills == ["Docker", "AWS", "React", "SomeUnknownSkill"]
    types = {r["skill"]: r["resource_type"] for r in out}
    assert types["Docker"] == "hands_on_lab"
    assert types["AWS"] == "certification_path"
    assert types["React"] == "portfolio_piece"
    # Unknown skill -> truthful generic fallback, never fabricated.
    assert types["SomeUnknownSkill"] == "practice_project"
    blob = json.dumps(out, ensure_ascii=False)
    assert "http" not in blob and "www." not in blob


def test_learning_resources_mapping_honest_empty() -> None:
    assert job_fit_service._learning_resources_from_gaps([], locale="en") == []
    assert job_fit_service._learning_resources_from_gaps(["", "   "], locale="vi") == []


# --------------------------------------------------------------------------- #
# (c) Hand-off builder is pure, well-formed, advisory, confirmation-gated       #
# --------------------------------------------------------------------------- #


def test_handoff_builder_is_well_formed_and_advisory() -> None:
    out = cv_gap_handoff.build_improvement(cv_id="cv-123", skill="Docker", locale="en")
    assert out is not None
    assert out["action"] == "cv_edit_command"
    assert out["method"] == "POST"
    assert out["endpoint"] == "/api/v1/cvs/cv-123/ai-edit-command"
    assert out["cv_id"] == "cv-123"
    assert out["skill"] == "Docker"
    assert out["requires_confirmation"] is True
    instruction = out["request"]["instruction"]
    assert "Docker" in instruction
    # Advisory / never asserts the student HAS the skill.
    assert "only if" in instruction.lower()


def test_handoff_builder_returns_none_without_target_or_skill() -> None:
    assert cv_gap_handoff.build_improvement(cv_id=None, skill="Docker") is None
    assert cv_gap_handoff.build_improvement(cv_id="cv-1", skill="   ") is None


def test_handoff_builder_dedupes_and_limits() -> None:
    out = cv_gap_handoff.build_improvements(
        cv_id="cv-1",
        gaps=["Docker", "docker", "Kubernetes", "AWS", "GCP", "Azure", "Terraform"],
        locale="en",
        limit=5,
    )
    # Case-insensitive de-dupe of "Docker"/"docker" + capped at 5.
    assert len(out) == 5
    skills = [o["skill"] for o in out]
    assert skills == ["Docker", "Kubernetes", "AWS", "GCP", "Azure"]


def test_handoff_localizes_vi() -> None:
    out = cv_gap_handoff.build_improvement(cv_id="cv-1", skill="Docker", locale="vi")
    assert out is not None
    assert "chỉ khi" in out["request"]["instruction"].lower()


# --------------------------------------------------------------------------- #
# (d) analysis_payload leak-safety (excludes the model score)                   #
# --------------------------------------------------------------------------- #


def test_analysis_payload_excludes_score_and_is_leak_safe() -> None:
    result = semantic_scorer.SemanticFitResult(
        score=91,
        summary="x",
        matched_evidence=[
            semantic_scorer.MatchedEvidence(
                requirement="Python", cv_evidence="y", strength="moderate", reasoning="z"
            )
        ],
        gaps=[
            semantic_scorer.MatchGap(
                requirement="Go",
                cv_evidence=None,
                severity="soft",
                reasoning="r",
                suggestion="s",
            )
        ],
        overall_suggestion="o",
    )
    payload = semantic_scorer.analysis_payload(result)
    assert "score" not in payload
    assert payload["matched_evidence"][0]["evidence_strength"] == "moderate"
    assert payload["gaps"][0]["severity"] == "soft"
    _assert_no_leak(payload)
