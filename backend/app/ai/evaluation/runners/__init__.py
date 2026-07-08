"""Per-task-family eval runner registry.

Each family module exports ``run_case(case) -> Probe`` (async) and
``check(key, exp, probe) -> str | None``. The harness (``app.ai.evaluation.harness``)
dispatches to these by family name (for running a case) and by ``Probe.kind``
(for checking an expectation) — this is the single place both dispatch
tables are assembled, so adding a new family means adding one line here.
"""

from __future__ import annotations

from app.ai.evaluation.runners import (
    answer_feedback,
    bias,
    chat,
    competition_signal,
    content_moderation,
    cover_letter,
    cv_edit_command,
    cv_suggestions,
    fraud_detection,
    interview_prep,
    interview_sim,
    jd_extraction,
    jd_generation,
    jd_translation,
    knowledge_base,
    market_intelligence,
    recommend,
    scorecard_suggest,
    screening_brief,
)

RUN_CASE_BY_FAMILY = {
    "cv_ai_suggestions": cv_suggestions.run_case,
    "cv_edit_command": cv_edit_command.run_case,
    # Student assistant loop-closing write tools (Task G / WS-10). Each wraps an
    # already-evaluated AI task, so the tool's model behaviour is gated by reusing
    # that task's runner over a tool-framed dataset:
    #   tailor_cv_to_job              -> cv_edit_command (pending CV diff)
    #   draft_and_attach_cover_letter -> cover_letter    (draft, never auto-sent)
    "tailor_cv_to_job": cv_edit_command.run_case,
    "draft_and_attach_cover_letter": cover_letter.run_case,
    "recommend_cv_for_job": recommend.run_case,
    "interview_sim": interview_sim.run_case,
    "ai_assistant_chat": chat.run_case,
    "jd_generation": jd_generation.run_case,
    "jd_extraction": jd_extraction.run_case,
    "knowledge_base_query": knowledge_base.run_case,
    "bias_detection": bias.run_case,
    "cover_letter": cover_letter.run_case,
    "jd_translation": jd_translation.run_case,
    "scorecard_suggest": scorecard_suggest.run_case,
    "screening_brief": screening_brief.run_case,
    "interview_prep": interview_prep.run_case,
    "answer_feedback": answer_feedback.run_case,
    "competition_signal_explanation": competition_signal.run_case,
    "content_moderation": content_moderation.run_case,
    "fraud_detection": fraud_detection.run_case,
    "market_intelligence": market_intelligence.run_case,
}

CHECK_BY_KIND = {
    "cv": cv_suggestions.check,
    "cv_edit": cv_edit_command.check,
    "rec": recommend.check,
    "sim": interview_sim.check,
    "chat": chat.check,
    "jd": jd_generation.check,
    "jd_extraction": jd_extraction.check,
    "kb": knowledge_base.check,
    "bias": bias.check,
    "cover_letter": cover_letter.check,
    "jd_translation": jd_translation.check,
    "scorecard_suggest": scorecard_suggest.check,
    "screening_brief": screening_brief.check,
    "interview_prep": interview_prep.check,
    "answer_feedback": answer_feedback.check,
    "competition_signal": competition_signal.check,
    "content_moderation": content_moderation.check,
    "fraud_detection": fraud_detection.check,
    "market_intelligence": market_intelligence.check,
}

__all__ = ["RUN_CASE_BY_FAMILY", "CHECK_BY_KIND"]
