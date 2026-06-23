from __future__ import annotations

import json
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any

from pydantic import BaseModel

from app.ai.gateway import ChatMessage, ChatRequest, LLMGateway, get_llm_gateway
from app.ai.interview.prompts import (
    INTERVIEW_PLANNER_SYSTEM_PROMPT,
    INTERVIEW_REPORT_SYSTEM_PROMPT,
    QUESTION_GENERATOR_SYSTEM_PROMPT,
)
from app.ai.interview.schemas import (
    CoverageItem,
    CoverageState,
    EvaluationState,
    InterviewAssessmentDimension,
    InterviewReport,
    InterviewReportDraft,
    InterviewRuntimeContext,
    InterviewTurnResult,
    PlannerOutput,
    PreviousAnswerEvaluation,
    QuestionDifficulty,
    QuestionGeneratorOutput,
    QuestionPlan,
    TopicEvidenceState,
)
from app.ai.matching.skills import normalize_skills

INTERNAL_TERMS = (
    "expected_signals",
    "internal_reason",
    "previous_answer_evaluation",
    "rubric",
    "score:",
)

REPORT_DIMENSIONS = {
    "technical_knowledge": ("Kiến thức chuyên môn", 30),
    "practical_experience": ("Kinh nghiệm thực tế", 20),
    "problem_solving": ("Giải quyết vấn đề", 20),
    "communication": ("Giao tiếp và làm rõ", 20),
    "critical_thinking": ("Tư duy phản biện", 10),
}


def build_coverage_state(context: InterviewRuntimeContext) -> CoverageState:
    if context.coverage_state.skills:
        return context.coverage_state

    cv_names = {name: name for name in normalize_skills([item.name for item in context.cv.skills])}
    required = normalize_skills(
        [item.name for item in context.job_description.required_skills]
        or context.matching_result.matched_skills
        + context.matching_result.missing_skills
    )
    nice = normalize_skills([item.name for item in context.job_description.nice_to_have_skills])
    items: list[CoverageItem] = []
    seen: set[str] = set()

    for source, priority, names in (
        ("jd_requirement", "must_have", required),
        ("jd_nice_to_have", "nice_to_have", nice),
        ("cv_only", "cv_only", sorted(set(cv_names) - set(required) - set(nice))),
    ):
        for name in names:
            if name in seen:
                continue
            seen.add(name)
            items.append(
                CoverageItem(
                    skill_id=name,
                    skill=name,
                    source=source,
                    priority=priority,
                    status="claimed" if name in cv_names else "not_assessed",
                )
            )
    return CoverageState(
        skills=items,
        unassessed_topics=[item.skill_id for item in items],
    )


def generate_next_turn(
    context: InterviewRuntimeContext,
    *,
    gateway: LLMGateway | None = None,
) -> InterviewTurnResult:
    coverage = build_coverage_state(context)
    runtime = context.model_copy(update={"coverage_state": coverage})

    if (
        runtime.question_count >= runtime.interview_config.max_questions
        and runtime.latest_answer is None
    ):
        planner = _finished_plan(runtime)
        return InterviewTurnResult(
            question="",
            planner_output=planner,
            coverage_state=coverage,
            evaluation_state=runtime.evaluation_state,
            provider_metadata={"fallback": True, "reason": "max_questions_reached"},
        )

    llm = gateway or get_llm_gateway()
    metadata: dict[str, Any] = {}
    planner: PlannerOutput | None = None
    try:
        planner, planner_meta = _call_structured(
            llm,
            system_prompt=INTERVIEW_PLANNER_SYSTEM_PROMPT,
            payload=runtime.model_dump(mode="json"),
            output_model=PlannerOutput,
            feature="interview_planner",
        )
        _validate_planner(planner, runtime)
        metadata["planner"] = planner_meta
    except Exception as exc:  # noqa: BLE001
        planner = _fallback_plan(
            runtime,
            previous_evaluation=(
                planner.previous_answer_evaluation if planner is not None else None
            ),
        )
        metadata["planner"] = {"fallback": True, "error": str(exc)[:500]}

    coverage, evaluation = _apply_previous_evaluation(
        coverage,
        runtime.evaluation_state,
        planner,
        evaluated_topic_key=(
            runtime.current_topic
            or (runtime.history[-1].topic_key if runtime.history else None)
        ),
        evaluated_difficulty=runtime.current_difficulty,
    )
    if runtime.question_count >= runtime.interview_config.max_questions:
        planner = _finished_plan(runtime)
        return InterviewTurnResult(
            question="",
            planner_output=planner,
            coverage_state=coverage,
            evaluation_state=evaluation,
            provider_metadata=metadata,
        )
    if _has_enough_evidence_to_finish(runtime, coverage, evaluation):
        planner = _finished_plan(runtime, reason="enough_evidence")
        return InterviewTurnResult(
            question="",
            planner_output=planner,
            coverage_state=coverage,
            evaluation_state=evaluation,
            provider_metadata=metadata,
        )
    if planner.should_end_interview:
        return InterviewTurnResult(
            question="",
            planner_output=planner,
            coverage_state=coverage,
            evaluation_state=evaluation,
            provider_metadata=metadata,
        )

    writer_payload = {
        "language": runtime.interview_config.language,
        "candidate_level": runtime.interview_config.candidate_level,
        "phase": planner.current_phase,
        "action": planner.action,
        "question_plan": planner.question_plan.model_dump(mode="json"),
        "previous_answer_summary": (runtime.latest_answer or "")[:1500],
        "previous_question": runtime.history[-1].question if runtime.history else "",
        "previous_answer_evaluation": (
            planner.previous_answer_evaluation.model_dump(mode="json")
            if planner.previous_answer_evaluation
            else None
        ),
        "already_asked_topics": [turn.topic_key for turn in runtime.history],
        "already_asked_questions": [turn.question for turn in runtime.history],
        "current_topic_evidence": (
            evaluation.topic_evidence.get(runtime.current_topic).model_dump(mode="json")
            if runtime.current_topic
            and evaluation.topic_evidence.get(runtime.current_topic)
            else None
        ),
    }
    writer_attempts: list[dict[str, Any]] = []
    try:
        for attempt in range(2):
            generated, writer_meta = _call_structured(
                llm,
                system_prompt=QUESTION_GENERATOR_SYSTEM_PROMPT,
                payload=writer_payload,
                output_model=QuestionGeneratorOutput,
                feature="interview_question_generator",
            )
            _validate_candidate_question(generated.question)
            duplicate = _find_similar_question(
                generated.question,
                [turn.question for turn in runtime.history],
            )
            writer_attempts.append(writer_meta)
            if duplicate is None:
                question = generated.question.strip()
                break
            if attempt == 1:
                raise ValueError(f"Generated question repeats an earlier question: {duplicate}")
            writer_payload = {
                **writer_payload,
                "rejected_question": generated.question,
                "rejection_reason": (
                    "The question is too similar to an earlier question. Target one narrower "
                    "unresolved evidence gap without repeating the same intent."
                ),
            }
        metadata["question_generator"] = {
            **writer_attempts[-1],
            "attempts": len(writer_attempts),
        }
    except Exception as exc:  # noqa: BLE001
        question = _fallback_question(runtime, planner)
        metadata["question_generator"] = {
            "fallback": True,
            "error": str(exc)[:500],
            "attempts": len(writer_attempts),
        }

    return InterviewTurnResult(
        question=question,
        planner_output=planner,
        coverage_state=coverage,
        evaluation_state=evaluation,
        provider_metadata=metadata,
    )


def generate_interview_report(
    context: InterviewRuntimeContext,
    *,
    answer_evaluations: list[dict[str, Any]],
    gateway: LLMGateway | None = None,
) -> tuple[InterviewReport, dict[str, Any]]:
    llm = gateway or get_llm_gateway()
    payload = {
        "language": context.interview_config.language,
        "candidate_level": context.interview_config.candidate_level,
        "target_role_context": context.interview_config.target_role,
        "transcript": [turn.model_dump(mode="json") for turn in context.history],
        "answer_evaluations": answer_evaluations,
        "coverage_state": context.coverage_state.model_dump(mode="json"),
        "communication_samples": [
            sample.model_dump(mode="json")
            for sample in context.evaluation_state.communication_samples
        ],
        "contradictions": context.evaluation_state.contradictions,
    }
    try:
        draft, metadata = _call_structured(
            llm,
            system_prompt=INTERVIEW_REPORT_SYSTEM_PROMPT,
            payload=payload,
            output_model=InterviewReportDraft,
            feature="interview_final_report",
        )
        return _finalize_report(draft), metadata
    except Exception as exc:  # noqa: BLE001
        return _fallback_report(context), {"fallback": True, "error": str(exc)[:500]}


def _finalize_report(draft: InterviewReportDraft) -> InterviewReport:
    by_key = {dimension.key: dimension for dimension in draft.dimensions}
    if set(by_key) != set(REPORT_DIMENSIONS):
        raise ValueError("The report must contain each assessment dimension exactly once")
    dimensions = [
        InterviewAssessmentDimension(
            key=key,
            label=label,
            score=by_key[key].score,
            weight=weight,
            summary=by_key[key].summary,
            evidence=by_key[key].evidence,
        )
        for key, (label, weight) in REPORT_DIMENSIONS.items()
    ]
    overall_score = round(
        sum(dimension.score * dimension.weight for dimension in dimensions) / 100
    )
    return InterviewReport(
        overall_score=overall_score,
        overall_summary=draft.overall_summary,
        dimensions=dimensions,
        strengths=draft.strengths,
        improvements=draft.improvements,
        insufficient_evidence=draft.insufficient_evidence,
        action_plan=draft.action_plan,
        confidence=draft.confidence,
    )


def _fallback_report(context: InterviewRuntimeContext) -> InterviewReport:
    samples = context.evaluation_state.communication_samples
    communication_score = (
        round(
            sum(
                sample.clarity
                + sample.specificity
                + sample.relevance
                + sample.structure
                for sample in samples
            )
            / (len(samples) * 16)
            * 100
        )
        if samples
        else 0
    )
    assessed = [
        item
        for item in context.coverage_state.skills
        if item.status not in {"not_assessed", "claimed"}
    ]
    verified = [item for item in assessed if item.status == "verified"]
    technical_score = round(len(verified) / len(assessed) * 100) if assessed else 0
    phase_scores = {
        "practical_experience": 50 if "cv_verification" in {t.phase for t in context.history} else 0,
        "problem_solving": 50 if "problem_solving" in {t.phase for t in context.history} else 0,
        "critical_thinking": 50 if "behavioral" in {t.phase for t in context.history} else 0,
    }
    scores = {
        "technical_knowledge": technical_score,
        **phase_scores,
        "communication": communication_score,
    }
    draft = InterviewReportDraft(
        overall_summary=(
            "Báo cáo được tổng hợp từ các bằng chứng đã ghi nhận trong buổi phỏng vấn. "
            "Một số nhận xét chi tiết chưa thể tạo đầy đủ."
        ),
        dimensions=[
            {
                "key": key,
                "score": scores[key],
                "summary": (
                    "Điểm tạm tính từ các bằng chứng có cấu trúc đã thu thập trong buổi phỏng vấn."
                ),
                "evidence": [],
            }
            for key in REPORT_DIMENSIONS
        ],
        strengths=[],
        improvements=[],
        insufficient_evidence=[
            "Chưa đủ dữ liệu để tạo nhận xét chi tiết cho toàn bộ khía cạnh."
        ],
        action_plan=[
            "Luyện trả lời bằng một ví dụ cụ thể, nêu rõ hành động cá nhân và kết quả."
        ],
        confidence="low",
    )
    return _finalize_report(draft)


def _call_structured[ModelT: BaseModel](
    gateway: LLMGateway,
    *,
    system_prompt: str,
    payload: dict[str, Any],
    output_model: type[ModelT],
    feature: str,
) -> tuple[ModelT, dict[str, Any]]:
    schema = output_model.model_json_schema()
    response = gateway.chat(
        ChatRequest(
            messages=[
                ChatMessage(role="system", content=system_prompt),
                ChatMessage(
                    role="user",
                    content=json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                ),
            ],
            temperature=0.1,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": output_model.__name__,
                    "schema": schema,
                    "strict": True,
                },
            },
            response_schema=schema,
            metadata={"feature": feature},
        )
    )
    parsed = output_model.model_validate(_load_json_object(response.content))
    return parsed, {
        "provider": response.provider,
        "model": response.model,
        "input_tokens": response.input_tokens,
        "output_tokens": response.output_tokens,
    }


def _validate_planner(planner: PlannerOutput, context: InterviewRuntimeContext) -> None:
    config = context.interview_config
    first_turn = not context.history and context.latest_answer is None
    if first_turn:
        if planner.action != "ask_initial_question":
            raise ValueError("The first turn must use ask_initial_question")
        if planner.previous_answer_evaluation is not None:
            raise ValueError("The first turn cannot evaluate a previous answer")
    elif planner.previous_answer_evaluation is None:
        raise ValueError("Later turns must evaluate the previous answer")
    if planner.suggested_next_phase and planner.suggested_next_phase not in {
        *config.allowed_next_phases,
        config.current_phase,
    }:
        raise ValueError("suggested_next_phase is not allowed")
    if planner.follow_up_count > config.max_follow_ups_per_topic:
        raise ValueError("Planner exceeded max_follow_ups_per_topic")
    if not first_turn and planner.previous_answer_evaluation:
        evaluation = planner.previous_answer_evaluation
        topic_state = (
            context.evaluation_state.topic_evidence.get(context.current_topic)
            if context.current_topic
            else None
        )
        weak_answer = evaluation.answer_quality in {
            "vague",
            "irrelevant",
            "unable_to_answer",
        }
        consecutive_weak = (topic_state.consecutive_weak_answers if topic_state else 0) + (
            1 if weak_answer else 0
        )
        must_stop = (
            evaluation.topic_decision == "stop"
            or evaluation.answer_quality == "unable_to_answer"
            or consecutive_weak >= 2
            or (
                evaluation.ownership == "not_owned"
                and evaluation.topic_decision != "learning_probe"
            )
        )
        follow_up_limit = 1 if evaluation.answer_quality in {"vague", "irrelevant"} else 2
        can_follow_up = (
            context.follow_up_count < min(config.max_follow_ups_per_topic, follow_up_limit)
            and not must_stop
        )
        needs_follow_up = (
            evaluation.topic_decision in {"clarify", "learning_probe"}
            or (
                evaluation.answer_quality in {"vague", "partial", "irrelevant"}
                and bool(evaluation.missing_evidence)
            )
        )
        same_topic = planner.question_plan.topic_key == context.current_topic
        if must_stop and same_topic:
            raise ValueError("This topic must stop after weak, unable, or non-owned evidence")
        if evaluation.ownership == "not_owned" and same_topic:
            if evaluation.topic_decision != "learning_probe":
                raise ValueError("A non-owned topic only permits one learning probe")
            if topic_state and topic_state.learning_probe_used:
                raise ValueError("The learning probe for this non-owned topic was already used")
            if planner.question_plan.difficulty != "easy":
                raise ValueError("A learning probe for non-owned work must be easy")
        if needs_follow_up and can_follow_up:
            if not same_topic:
                raise ValueError("An incomplete answer must be clarified on the same topic")
            if planner.question_plan.question_type != "follow_up":
                raise ValueError("An incomplete answer requires a follow-up question")
            if planner.action not in {
                "probe_deeper",
                "request_example",
                "request_evidence",
                "clarify_answer",
                "challenge_assumption",
                "resolve_contradiction",
            }:
                raise ValueError("An incomplete answer requires a follow-up action")
            if planner.follow_up_count != context.follow_up_count + 1:
                raise ValueError("follow_up_count must increment on the same topic")
        elif not same_topic and planner.follow_up_count != 0:
            raise ValueError("follow_up_count must reset when switching topics")
        elif same_topic and needs_follow_up and not can_follow_up:
            raise ValueError("The follow-up limit for this answer or topic has been reached")
        if context.current_difficulty:
            difficulty_rank = {"easy": 0, "medium": 1, "hard": 2}
            if (
                difficulty_rank[planner.question_plan.difficulty]
                > difficulty_rank[context.current_difficulty] + 1
            ):
                raise ValueError("Question difficulty cannot jump more than one level")
    if planner.current_phase == "completed" and not planner.should_end_interview:
        raise ValueError("completed phase must end the interview")
    if planner.should_end_interview and planner.action != "finish_interview":
        raise ValueError("Ending the interview requires finish_interview")
    if planner.should_end_interview and context.question_count < config.max_questions:
        raise ValueError("The backend controls early interview completion")


def _validate_candidate_question(question: str) -> None:
    normalized = question.strip().lower()
    if not normalized:
        raise ValueError("Question is empty")
    if normalized.count("?") > 1:
        raise ValueError("Question contains multiple question marks")
    if any(term in normalized for term in INTERNAL_TERMS):
        raise ValueError("Question leaks internal evaluation data")
    if len(re.findall(r"(?<=[.!?])\s+", normalized)) > 1:
        raise ValueError("Question contains multiple sentences")


def _normalize_question(question: str) -> str:
    value = unicodedata.normalize("NFKD", question.casefold())
    value = "".join(character for character in value if not unicodedata.combining(character))
    return " ".join(re.findall(r"\w+", value, flags=re.UNICODE))


def _find_similar_question(question: str, previous_questions: list[str]) -> str | None:
    normalized = _normalize_question(question)
    if not normalized:
        return None
    tokens = set(normalized.split())
    for previous in previous_questions:
        prior = _normalize_question(previous)
        if not prior:
            continue
        prior_tokens = set(prior.split())
        union = tokens | prior_tokens
        token_similarity = len(tokens & prior_tokens) / len(union) if union else 0
        sequence_similarity = SequenceMatcher(None, normalized, prior).ratio()
        if normalized == prior or sequence_similarity >= 0.84 or token_similarity >= 0.78:
            return previous
    return None


def _fallback_plan(
    context: InterviewRuntimeContext,
    *,
    previous_evaluation: PreviousAnswerEvaluation | None = None,
) -> PlannerOutput:
    first_turn = not context.history and context.latest_answer is None
    phase = context.interview_config.current_phase
    coverage = build_coverage_state(context)
    topic_state = (
        context.evaluation_state.topic_evidence.get(context.current_topic)
        if context.current_topic
        else None
    )
    should_clarify = (
        not first_turn
        and bool(context.current_topic)
        and context.follow_up_count < min(
            context.interview_config.max_follow_ups_per_topic,
            1,
        )
        and (topic_state is None or topic_state.ownership != "not_owned")
        and (topic_state is None or topic_state.consecutive_weak_answers < 1)
        and (topic_state is None or not topic_state.stop_reason)
        and (
            previous_evaluation is None
            or (
                previous_evaluation.ownership != "not_owned"
                and previous_evaluation.answer_quality != "unable_to_answer"
                and previous_evaluation.topic_decision != "stop"
            )
        )
    )
    target = next(
        (
            item
            for item in coverage.skills
            if item.priority == "must_have" and item.status != "verified"
            and item.ownership != "not_owned"
            and f"verify_{item.skill_id}" != context.current_topic
        ),
        None,
    )
    if should_clarify:
        plan = QuestionPlan(
            question_type="follow_up",
            difficulty="easy",
            target_competency="clear and specific communication",
            source_type="previous_answer",
            source_reference=(context.latest_answer or "")[:500],
            evidence_gap="A concrete example, personal action, or result is missing.",
            question_intent="clarify_answer",
            topic_key=context.current_topic or "clarify_previous_answer",
        )
    elif phase == "career" and first_turn:
        plan = QuestionPlan(
            question_type="initial" if first_turn else "transition",
            difficulty="easy",
            target_competency="career motivation",
            source_type="jd_requirement" if context.job_description.title else "general",
            source_reference=context.job_description.title,
            evidence_gap="The candidate's motivation for this role has not been assessed.",
            question_intent="Understand why the candidate wants this role.",
            topic_key="career_motivation",
        )
    else:
        skill = target.skill if target else "problem solving approach"
        plan = QuestionPlan(
            question_type="initial" if first_turn else "transition",
            difficulty="easy",
            target_competency=skill,
            source_type="jd_requirement" if target else "general",
            source_reference=skill,
            evidence_gap="Direct evidence of the candidate's contribution is missing.",
            question_intent="request_evidence",
            topic_key=f"verify_{target.skill_id}" if target else "problem_solving_approach",
            linked_skill_ids=[target.skill_id] if target else [],
        )
    return PlannerOutput(
        action=(
            "ask_initial_question"
            if first_turn
            else "clarify_answer"
            if should_clarify
            else "switch_topic"
        ),
        current_phase=(
            "cv_verification" if phase == "career" and not first_turn else phase
        ),
        question_plan=plan,
        previous_answer_evaluation=None
        if first_turn
        else previous_evaluation
        or PreviousAnswerEvaluation(
            status="not_assessed",
            answer_quality="vague",
            missing_evidence=["A concrete example or direct contribution is missing."],
            remaining_gap="A concrete example or direct contribution is missing.",
            topic_decision="clarify" if should_clarify else "stop",
            reason_for_next_question=(
                "Ask for one concrete example."
                if should_clarify
                else "Move to another competency after an unproductive topic."
            ),
            anti_repetition_check="Use a narrower evidence request than the previous question.",
            ownership_check="Do not assume ownership until the candidate states it.",
            communication={
                "clarity": 1,
                "specificity": 0,
                "relevance": 1,
                "structure": 1,
                "summary": "The answer could not be evaluated reliably.",
            },
        ),
        internal_reason="Deterministic fallback selected the highest-priority available topic.",
        follow_up_count=context.follow_up_count + 1 if should_clarify else 0,
    )


def _finished_plan(
    context: InterviewRuntimeContext,
    *,
    reason: str = "max_questions_reached",
) -> PlannerOutput:
    return PlannerOutput(
        action="finish_interview",
        current_phase="completed",
        suggested_next_phase=None,
        question_plan=QuestionPlan(
            question_type="closing",
            difficulty="easy",
            target_competency="interview completion",
            source_type="general",
            question_intent="finish_interview",
            topic_key="completed",
        ),
        previous_answer_evaluation=None,
        internal_reason=(
            "Enough evidence has been collected across required skills and communication."
            if reason == "enough_evidence"
            else "The configured question limit has been reached."
        ),
        phase_completion_signal=(
            "enough_evidence" if reason == "enough_evidence" else "max_questions_reached"
        ),
        should_end_interview=True,
    )


def _fallback_question(
    context: InterviewRuntimeContext,
    planner: PlannerOutput,
) -> str:
    language = context.interview_config.language.lower()
    plan = planner.question_plan
    competency = plan.target_competency.strip() or "chủ đề này"
    if language.startswith("vi"):
        if (
            planner.previous_answer_evaluation
            and planner.previous_answer_evaluation.ownership == "not_owned"
            and planner.previous_answer_evaluation.topic_decision == "learning_probe"
            and plan.topic_key == context.current_topic
        ):
            candidate = (
                f"Nếu được giao phụ trách {competency}, bước đầu tiên em sẽ tìm hiểu "
                "và thực hiện là gì?"
            )
        elif plan.question_type == "follow_up":
            candidate = (
                f"Em có thể nêu một ví dụ cụ thể chứng minh khả năng {competency} không?"
            )
        elif planner.current_phase == "career":
            candidate = (
                f"Trong công việc {context.interview_config.target_role or 'này'}, "
                "khía cạnh nào khiến em muốn tìm hiểu sâu hơn?"
            )
        else:
            candidate = (
                f"Em có thể nêu một tình huống cụ thể em đã sử dụng {competency} không?"
            )
        alternatives = [
            candidate,
            f"Với {competency}, quyết định quan trọng nhất em từng trực tiếp đưa ra là gì?",
            f"Kết quả cụ thể nào cho thấy phần việc {competency} của em đã hoạt động tốt?",
        ]
    else:
        if (
            planner.previous_answer_evaluation
            and planner.previous_answer_evaluation.ownership == "not_owned"
            and planner.previous_answer_evaluation.topic_decision == "learning_probe"
            and plan.topic_key == context.current_topic
        ):
            candidate = (
                f"If you were assigned {competency}, what would be your first step "
                "to learn and implement it?"
            )
        elif plan.question_type == "follow_up":
            candidate = f"What concrete example best demonstrates your {competency}?"
        elif planner.current_phase == "career":
            candidate = (
                f"Which part of {context.interview_config.target_role or 'this role'} "
                "would you most like to explore further?"
            )
        else:
            candidate = f"What is one concrete situation where you used {competency}?"
        alternatives = [
            candidate,
            f"What was the most important decision you personally made about {competency}?",
            f"What concrete result showed that your work on {competency} was effective?",
        ]
    previous_questions = [turn.question for turn in context.history]
    return next(
        (
            alternative
            for alternative in alternatives
            if _find_similar_question(alternative, previous_questions) is None
        ),
        alternatives[-1],
    )


def _apply_previous_evaluation(
    coverage: CoverageState,
    evaluation_state: EvaluationState,
    planner: PlannerOutput,
    *,
    evaluated_topic_key: str | None,
    evaluated_difficulty: QuestionDifficulty | None,
) -> tuple[CoverageState, EvaluationState]:
    evaluation = planner.previous_answer_evaluation
    if not evaluation:
        return coverage, evaluation_state
    communication_samples = [
        *evaluation_state.communication_samples,
        evaluation.communication,
    ][-40:]
    topic_evidence = dict(evaluation_state.topic_evidence)
    if evaluated_topic_key:
        previous_topic = topic_evidence.get(evaluated_topic_key, TopicEvidenceState())
        weak_answer = evaluation.answer_quality in {
            "vague",
            "irrelevant",
            "unable_to_answer",
        }
        topic_evidence[evaluated_topic_key] = previous_topic.model_copy(
            update={
                "ownership": (
                    evaluation.ownership
                    if evaluation.ownership != "unknown"
                    else previous_topic.ownership
                ),
                "evidence_found": list(
                    dict.fromkeys(
                        [*previous_topic.evidence_found, *evaluation.evidence_found]
                    )
                )[-10:],
                "remaining_gap": evaluation.remaining_gap
                or (evaluation.missing_evidence[0] if evaluation.missing_evidence else ""),
                "highest_verified_difficulty": (
                    evaluated_difficulty
                    if evaluation.status == "verified" and evaluated_difficulty
                    else previous_topic.highest_verified_difficulty
                ),
                "stop_reason": (
                    evaluation.reason_for_next_question
                    if evaluation.topic_decision == "stop"
                    else previous_topic.stop_reason
                ),
                "consecutive_weak_answers": (
                    min(previous_topic.consecutive_weak_answers + 1, 10)
                    if weak_answer
                    else 0
                ),
                "learning_probe_used": (
                    previous_topic.learning_probe_used
                    or evaluation.topic_decision == "learning_probe"
                ),
                "red_flags": list(
                    dict.fromkeys([*previous_topic.red_flags, *evaluation.red_flags])
                )[-10:],
            }
        )
    red_flags = list(
        dict.fromkeys([*evaluation_state.red_flags, *evaluation.red_flags])
    )[-100:]
    linked = set(planner.evaluated_skill_ids)
    if not linked:
        return (
            coverage,
            evaluation_state.model_copy(
                update={
                    "communication_samples": communication_samples,
                    "topic_evidence": topic_evidence,
                    "red_flags": red_flags,
                }
            ),
        )

    updated_skills = []
    for item in coverage.skills:
        if item.skill_id not in linked:
            updated_skills.append(item)
            continue
        updated_skills.append(
            item.model_copy(
                update={
                    "status": evaluation.status,
                    "evidence_count": item.evidence_count + 1,
                    "evidence_summaries": list(
                        dict.fromkeys([*item.evidence_summaries, *evaluation.evidence_found])
                    )[-10:],
                    "ownership": (
                        evaluation.ownership
                        if evaluation.ownership != "unknown"
                        else item.ownership
                    ),
                    "highest_verified_difficulty": (
                        evaluated_difficulty
                        if evaluation.status == "verified" and evaluated_difficulty
                        else item.highest_verified_difficulty
                    ),
                    "stop_reason": (
                        evaluation.reason_for_next_question
                        if evaluation.topic_decision == "stop"
                        else item.stop_reason
                    ),
                    "last_topic_key": evaluated_topic_key,
                }
            )
        )
    statuses = dict(evaluation_state.competency_status)
    for skill_id in linked:
        statuses[skill_id] = evaluation.status
    contradictions = [
        *evaluation_state.contradictions,
        *evaluation.contradictions,
    ][-100:]
    verified_topics = list(coverage.verified_topics)
    if evaluation.status == "verified" and evaluated_topic_key:
        verified_topics.append(evaluated_topic_key)
    return (
        coverage.model_copy(
            update={
                "skills": updated_skills,
                "verified_topics": list(dict.fromkeys(verified_topics)),
                "unassessed_topics": [
                    item.skill_id for item in updated_skills if item.status == "not_assessed"
                ],
            }
        ),
        EvaluationState(
            competency_status=statuses,
            contradictions=contradictions,
            topic_evidence=topic_evidence,
            red_flags=red_flags,
            communication_samples=communication_samples,
            final_report=evaluation_state.final_report,
        ),
    )


def _has_enough_evidence_to_finish(
    context: InterviewRuntimeContext,
    coverage: CoverageState,
    evaluation_state: EvaluationState,
) -> bool:
    config = context.interview_config
    if context.question_count < config.min_questions:
        return False
    if len(evaluation_state.communication_samples) < config.min_communication_samples:
        return False

    must_have = [item for item in coverage.skills if item.priority == "must_have"]
    if must_have:
        if any(
            item.evidence_count == 0 or item.status in {"not_assessed", "claimed"}
            for item in must_have
        ):
            return False

    phases = {turn.phase for turn in context.history}
    if "cv_verification" not in phases:
        return False
    return bool(phases.intersection({"problem_solving", "behavioral"}))


def _load_json_object(content: str) -> dict[str, Any]:
    stripped = content.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, flags=re.DOTALL)
    if fenced:
        stripped = fenced.group(1)
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("No JSON object found in model output")
    payload = json.loads(stripped[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("Model output must be a JSON object")
    return payload
