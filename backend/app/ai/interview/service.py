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
    TECH_LEAD_REPORT_SYSTEM_PROMPT,
    TECHNICAL_CHECK_REPORT_SYSTEM_PROMPT,
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

TECH_LEAD_LABEL_TERMS = (
    "clear and specific communication",
    "technical problem solving",
    "critical thinking",
    "project ownership",
    "communication skill",
)

TECHNICAL_CHECK_NON_TASK_TERMS = (
    "buổi phỏng vấn",
    "chúc bạn",
    "dừng lại tại đây",
    "kết thúc phần",
    "interview will stop",
    "end the interview",
    "vì sao em quan tâm",
    "why are you interested",
    "career goal",
    "mục tiêu nghề nghiệp",
    "clear and specific communication",
    "communication skill",
    "kể cho tôi về kinh nghiệm",
    "tell me about your experience",
    "tình huống cụ thể em đã sử dụng",
    "situation where you used",
    "quyết định quan trọng nhất",
    "most important decision",
    "kết quả cụ thể nào cho thấy",
    "what concrete result showed",
)

TECHNICAL_TASK_SIGNALS = (
    "code",
    "query",
    "sql",
    "mongodb",
    "endpoint",
    "api",
    "status code",
    "debug",
    "log",
    "docker",
    "container",
    "output",
    "edge case",
    "exception",
    "request",
    "response",
    "viet",
    "truy van",
    "loi",
    "kiem tra",
    "dau vao",
    "dau ra",
    "status",
    "uvicorn",
    "pydantic",
)

TECH_LEAD_DIRECT_TASK_TERMS = (
    "basic programming test",
    "coding test",
    "programming skill test",
    "write code",
    "write a code",
    "write a snippet",
    "write a short snippet",
    "write sql",
    "write a sql",
    "write query",
    "write a query",
    "write a dockerfile",
    "filter even numbers",
    "return a new list",
    "kiểm tra kỹ năng lập trình",
    "kiểm tra lập trình",
    "viết code",
    "viết một đoạn code",
    "viết đoạn code",
    "viết một đoạn mã",
    "viết đoạn mã",
    "viết mã",
    "viết sql",
    "viết một câu lệnh sql",
    "viết câu lệnh sql",
    "viết một truy vấn",
    "viết query",
    "viết truy vấn",
    "viết dockerfile",
    "viết nội dung dockerfile",
    "lọc ra các số chẵn",
    "trả về một danh sách",
)

REPORT_DIMENSIONS = {
    "technical_knowledge": ("Kiến thức chuyên môn", 30),
    "practical_experience": ("Kinh nghiệm thực tế", 20),
    "problem_solving": ("Giải quyết vấn đề", 20),
    "communication": ("Giao tiếp và làm rõ", 20),
    "critical_thinking": ("Tư duy phản biện", 10),
}
TECHNICAL_CHECK_REPORT_DIMENSIONS = {
    "technical_knowledge": ("Kiến thức chuyên môn", 30),
    "practical_experience": ("Độ đúng code/query", 25),
    "problem_solving": ("Debug và giải quyết vấn đề", 25),
    "communication": ("Giải thích kỹ thuật", 10),
    "critical_thinking": ("Edge cases và hiệu năng", 10),
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
        fallback_runtime = runtime.model_copy(
            update={"coverage_state": coverage, "evaluation_state": evaluation}
        )
        planner = _fallback_plan(
            fallback_runtime,
            previous_evaluation=planner.previous_answer_evaluation,
        )
        metadata["planner"] = {
            **metadata.get("planner", {}),
            "backend_overrode_early_finish": True,
        }

    writer_payload = {
        "language": runtime.interview_config.language,
        "interview_mode": runtime.interview_config.interview_mode,
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
            writer_attempts.append(writer_meta)
            try:
                _validate_candidate_question(generated.question, runtime)
            except ValueError as validation_error:
                if attempt == 1:
                    raise
                writer_payload = {
                    **writer_payload,
                    "rejected_question": generated.question,
                    "rejection_reason": str(validation_error),
                }
                continue
            duplicate = _find_similar_question(
                generated.question,
                [turn.question for turn in runtime.history],
            )
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
        "interview_mode": context.interview_config.interview_mode,
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
            system_prompt=_report_prompt(context),
            payload=payload,
            output_model=InterviewReportDraft,
            feature="interview_final_report",
        )
        return _finalize_report(
            draft,
            dimensions=_report_dimensions(context),
        ), metadata
    except Exception as exc:  # noqa: BLE001
        return _fallback_report(context), {"fallback": True, "error": str(exc)[:500]}


def _report_dimensions(
    context: InterviewRuntimeContext,
) -> dict[str, tuple[str, int]]:
    if context.interview_config.interview_mode == "technical_check":
        return TECHNICAL_CHECK_REPORT_DIMENSIONS
    return REPORT_DIMENSIONS


def _report_prompt(context: InterviewRuntimeContext) -> str:
    if context.interview_config.interview_mode == "technical_check":
        return TECHNICAL_CHECK_REPORT_SYSTEM_PROMPT
    if context.interview_config.interview_mode == "tech_lead":
        return TECH_LEAD_REPORT_SYSTEM_PROMPT
    return INTERVIEW_REPORT_SYSTEM_PROMPT


def _finalize_report(
    draft: InterviewReportDraft,
    *,
    dimensions: dict[str, tuple[str, int]] = REPORT_DIMENSIONS,
) -> InterviewReport:
    by_key = {dimension.key: dimension for dimension in draft.dimensions}
    if set(by_key) != set(dimensions):
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
        for key, (label, weight) in dimensions.items()
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
    report_dimensions = _report_dimensions(context)
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
            for key in report_dimensions
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
    return _finalize_report(draft, dimensions=report_dimensions)


def _call_structured[ModelT: BaseModel](
    gateway: LLMGateway,
    *,
    system_prompt: str,
    payload: dict[str, Any],
    output_model: type[ModelT],
    feature: str,
) -> tuple[ModelT, dict[str, Any]]:
    schema = output_model.model_json_schema()
    last_error: Exception | None = None
    for attempt in range(2):
        # Gemini can occasionally return malformed or empty content when a large
        # JSON Schema is enforced. Keep the first call strict, then retry in
        # JSON mode only so the same prompt can still produce valid structured
        # data before we fall back deterministically.
        response_schema = schema if attempt == 0 else None
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
                response_schema=response_schema,
                metadata={"feature": feature},
            )
        )
        try:
            parsed = output_model.model_validate(_load_json_object(response.content))
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt == 0:
                continue
            raise
        return parsed, {
            "provider": response.provider,
            "model": response.model,
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
            "attempts": attempt + 1,
        }
    raise RuntimeError("Structured model call failed") from last_error


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
    if _is_technical_check(context):
        if planner.current_phase in {"career", "behavioral", "candidate_questions"}:
            raise ValueError("Technical check mode only permits technical phases")
        if planner.question_plan.topic_key == "career_motivation":
            raise ValueError("Technical check mode cannot ask career motivation questions")
    if context.interview_config.interview_mode == "tech_lead":
        competency = planner.question_plan.target_competency.casefold()
        if any(term in competency for term in TECH_LEAD_LABEL_TERMS):
            raise ValueError("Tech lead planner exposed an internal competency label")
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
                "ask_question",
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


def _validate_candidate_question(
    question: str,
    context: InterviewRuntimeContext | None = None,
) -> None:
    normalized = question.strip().lower()
    if not normalized:
        raise ValueError("Question is empty")
    if normalized.count("?") > 1:
        raise ValueError("Question contains multiple question marks")
    if any(term in normalized for term in INTERNAL_TERMS):
        raise ValueError("Question leaks internal evaluation data")
    if context and _is_technical_check(context):
        if any(term in normalized for term in TECHNICAL_CHECK_NON_TASK_TERMS):
            raise ValueError("Technical check question is behavioral or communication-focused")
        task_text = _normalize_question(question)
        if not any(signal in task_text for signal in TECHNICAL_TASK_SIGNALS):
            raise ValueError("Technical check question lacks a concrete technical task signal")
    if context and context.interview_config.interview_mode == "tech_lead":
        if any(term in normalized for term in TECH_LEAD_LABEL_TERMS):
            raise ValueError("Tech lead question exposes an internal competency label")
        if (
            context.history
            and _is_tech_lead_direct_task(context.history[-1].question)
            and _is_tech_lead_direct_task(question)
        ):
            raise ValueError("Tech lead question repeats a direct coding/query task")
        if _is_tech_lead_direct_task(question) and _tech_lead_direct_task_count(context) >= 2:
            raise ValueError("Tech lead has reached the direct coding/query task limit")


def _normalize_question(question: str) -> str:
    value = unicodedata.normalize("NFKD", question.casefold())
    value = "".join(character for character in value if not unicodedata.combining(character))
    return " ".join(re.findall(r"\w+", value, flags=re.UNICODE))


def _is_tech_lead_direct_task(question: str) -> bool:
    normalized = _normalize_question(question)
    return any(
        _normalize_question(term) in normalized
        for term in TECH_LEAD_DIRECT_TASK_TERMS
    )


def _tech_lead_direct_task_count(context: InterviewRuntimeContext) -> int:
    return sum(1 for turn in context.history if _is_tech_lead_direct_task(turn.question))


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


def _is_technical_check(context: InterviewRuntimeContext) -> bool:
    return context.interview_config.interview_mode == "technical_check"


def _has_jd_scenario_evidence(context: InterviewRuntimeContext) -> bool:
    return any(turn.topic_key.startswith("jd_scenario_") for turn in context.history)


def _jd_scenario_plan(context: InterviewRuntimeContext) -> QuestionPlan:
    responsibility = next(
        (
            item.strip()
            for item in context.job_description.responsibilities
            if item.strip()
        ),
        context.job_description.title or context.interview_config.target_role,
    )
    role = context.interview_config.target_role or context.job_description.title or "this role"
    source_reference = responsibility or role
    normalized = normalize_skills([source_reference or role])
    topic_suffix = (normalized[0] if normalized else "role_workflow")[:100]
    return QuestionPlan(
        question_type="transition",
        difficulty="medium",
        target_competency=f"{role} workflow scenario",
        source_type="jd_requirement",
        source_reference=source_reference[:500],
        evidence_gap=(
            "The interview has not yet checked how the candidate applies the JD "
            "requirements to a realistic engineering workflow."
        ),
        question_intent="jd_work_scenario",
        topic_key=f"jd_scenario_{topic_suffix}",
    )


def _next_fallback_skill(
    context: InterviewRuntimeContext,
    coverage: CoverageState,
) -> CoverageItem | None:
    candidates = [
        item
        for item in coverage.skills
        if item.status != "verified"
        and item.evidence_count == 0
        and item.ownership != "not_owned"
        and not item.stop_reason
        and f"verify_{item.skill_id}" != context.current_topic
    ]
    if _is_technical_check(context):
        matched = [item for item in candidates if item.status == "claimed"]
        if matched:
            return sorted(matched, key=lambda item: item.skill)[0]
    if context.interview_config.interview_mode == "tech_lead":
        matched_must_have = [
            item for item in candidates if item.priority == "must_have" and item.status == "claimed"
        ]
        if matched_must_have:
            return matched_must_have[0]
        jd_only_must_have = [
            item
            for item in candidates
            if item.priority == "must_have" and item.status == "not_assessed"
        ]
        if jd_only_must_have:
            return jd_only_must_have[0]
    return next((item for item in candidates if item.priority == "must_have"), None)


def _fallback_evaluated_skill_ids(context: InterviewRuntimeContext) -> list[str]:
    if context.current_topic and context.current_topic.startswith("verify_"):
        return [context.current_topic.removeprefix("verify_")]
    return []


def _fallback_previous_answer_evaluation(
    context: InterviewRuntimeContext,
    *,
    should_clarify: bool,
    previous_evaluation: PreviousAnswerEvaluation | None,
) -> PreviousAnswerEvaluation | None:
    if not context.latest_answer:
        return None
    if previous_evaluation is not None:
        return previous_evaluation

    normalized = _normalize_question(context.latest_answer)
    concrete_terms = {
        "api",
        "endpoint",
        "docker",
        "dockerfile",
        "fastapi",
        "jwt",
        "log",
        "curl",
        "status",
        "query",
        "sql",
        "pydantic",
        "uvicorn",
        "test",
        "input",
        "output",
        "expected",
        "actual",
        "500",
        "401",
        "422",
    }
    vague_terms = {"khong chac", "chua chac", "thu chay", "xem loi", "lam qua", "sua dan"}
    concrete_hits = sum(1 for term in concrete_terms if term in normalized)
    vague_hits = sum(1 for term in vague_terms if term in normalized)
    is_sufficient = concrete_hits >= 3 and vague_hits == 0
    answer_quality = "sufficient" if is_sufficient else "vague"
    status = "partially_verified" if is_sufficient else "not_assessed"
    topic_decision = "continue" if is_sufficient else ("clarify" if should_clarify else "stop")
    evidence = (
        ["Answer includes concrete technical details such as commands, status codes, logs, or implementation steps."]
        if is_sufficient
        else []
    )
    missing = [] if is_sufficient else ["A concrete command, code path, output, or result is missing."]
    return PreviousAnswerEvaluation(
        score=3 if is_sufficient else 1,
        status=status,
        answer_quality=answer_quality,
        strengths=evidence,
        missing_evidence=missing,
        evidence_found=evidence,
        remaining_gap="" if is_sufficient else "A concrete technical detail is still missing.",
        ownership="direct" if is_sufficient else "unknown",
        topic_decision=topic_decision,
        reason_for_next_question=(
            "Move to another required skill after concrete evidence."
            if is_sufficient
            else "Ask for one concrete technical detail."
        ),
        anti_repetition_check="Fallback evaluation asks a different technical angle next.",
        ownership_check="Fallback only marks direct ownership when the answer includes concrete implementation details.",
        communication={
            "clarity": 3 if is_sufficient else 1,
            "specificity": 3 if is_sufficient else 0,
            "relevance": 3 if is_sufficient else 1,
            "structure": 2 if is_sufficient else 1,
            "summary": (
                "Concrete technical answer with implementation/debug details."
                if is_sufficient
                else "Answer is too generic for reliable assessment."
            ),
        },
    )


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
        and (
            previous_evaluation is None
            or previous_evaluation.topic_decision in {"clarify", "learning_probe"}
            or previous_evaluation.answer_quality in {"vague", "partial", "irrelevant"}
            or bool(previous_evaluation.missing_evidence)
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
    target = _next_fallback_skill(context, coverage)
    if should_clarify:
        competency = (
            "technical debugging detail"
            if _is_technical_check(context)
            else "technical explanation"
        )
        plan = QuestionPlan(
            question_type="follow_up",
            difficulty="easy",
            target_competency=competency,
            source_type="previous_answer",
            source_reference=(context.latest_answer or "")[:500],
            evidence_gap=(
                "A concrete command, output, error, or edge case is missing."
                if _is_technical_check(context)
                else "A concrete technical action, decision, or result is missing."
            ),
            question_intent=(
                "technical_debug_scenario"
                if _is_technical_check(context)
                else "clarify_answer"
            ),
            topic_key=context.current_topic or "clarify_previous_answer",
        )
    elif phase == "career" and first_turn and not _is_technical_check(context):
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
    elif (
        context.interview_config.interview_mode == "tech_lead"
        and not target
        and not _has_jd_scenario_evidence(context)
    ):
        plan = _jd_scenario_plan(context)
    else:
        skill = target.skill if target else "technical problem solving"
        plan = QuestionPlan(
            question_type="initial" if first_turn else "transition",
            difficulty="easy",
            target_competency=skill,
            source_type="jd_requirement" if target else "general",
            source_reference=skill,
            evidence_gap=(
                "Technical correctness, syntax, and practical reasoning have not been checked."
                if _is_technical_check(context)
                else "Direct evidence of the candidate's contribution is missing."
            ),
            question_intent=(
                "technical_code_task"
                if _is_technical_check(context)
                else "request_evidence"
            ),
            topic_key=f"verify_{target.skill_id}" if target else "technical_problem_solving",
            linked_skill_ids=[target.skill_id] if target else [],
        )
    fallback_evaluation = _fallback_previous_answer_evaluation(
        context,
        should_clarify=should_clarify,
        previous_evaluation=previous_evaluation,
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
            "problem_solving"
            if _is_technical_check(context) and phase == "career"
            else "cv_verification"
            if phase == "career" and not first_turn
            else phase
        ),
        question_plan=plan,
        previous_answer_evaluation=None
        if first_turn
        else fallback_evaluation
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
        evaluated_skill_ids=[] if first_turn else _fallback_evaluated_skill_ids(context),
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
    if _normalize_question(competency) in {
        "technical explanation",
        "technical debugging detail",
        "technical problem solving",
        "clear and specific communication",
    }:
        competency = (
            "kỹ thuật em vừa mô tả"
            if language.startswith("vi")
            else "the technical part you just described"
        )
    if _is_technical_check(context):
        return _technical_fallback_question(context, competency)
    if plan.topic_key.startswith("jd_scenario_"):
        if language.startswith("vi"):
            return (
                f"Giả sử trong vai trò {context.interview_config.target_role or context.job_description.title or 'này'}, "
                f"team giao em một yêu cầu liên quan đến {plan.source_reference or competency}. "
                "Em sẽ thiết kế flow xử lý, tách các thành phần, và xử lý lỗi chính như thế nào?"
            )
        return (
            f"Suppose that in {context.interview_config.target_role or context.job_description.title or 'this role'}, "
            f"the team gives you a requirement related to {plan.source_reference or competency}. "
            "How would you design the processing flow, split components, and handle the main failure case?"
        )
    if language.startswith("vi"):
        if (
            planner.previous_answer_evaluation
            and planner.previous_answer_evaluation.ownership == "not_owned"
            and planner.previous_answer_evaluation.topic_decision == "learning_probe"
            and plan.topic_key == context.current_topic
        ):
            candidate = (
                f"Nếu được giao phụ trách {competency}, bước đầu tiên em sẽ kiểm tra tài liệu, "
                "thiết kế thử nghiệm, hay dựng prototype như thế nào?"
            )
        elif plan.question_type == "follow_up":
            candidate = (
                "Trong câu trả lời vừa rồi, em có thể chọn một bước kỹ thuật em trực tiếp làm "
                "và nói rõ input, hành động, kết quả không?"
            )
        elif planner.current_phase == "career":
            candidate = (
                f"Với vai trò {context.interview_config.target_role or 'này'}, phần backend hoặc AI nào "
                "em muốn học sâu nhất khi tham gia team?"
            )
        else:
            candidate = (
                f"Trong một dự án có liên quan tới {competency}, em trực tiếp implement phần nào "
                "và gặp lỗi kỹ thuật gì đáng nhớ?"
            )
        alternatives = [
            candidate,
            f"Khi làm phần {competency}, em đã dùng log, test, hoặc metric nào để biết hướng xử lý là đúng?",
            f"Nếu làm lại phần {competency}, em sẽ giữ thiết kế nào và đổi điểm kỹ thuật nào?",
            f"Em sẽ giải thích một lỗi trong phần {competency} cho teammate bằng endpoint, input, expected và actual như thế nào?",
            f"Ở phần {competency}, em đã gặp rủi ro về config, dữ liệu, hoặc dependency nào và xử lý ra sao?",
            f"Nếu phần {competency} bị chậm hoặc lỗi không ổn định, em sẽ kiểm tra log, timeout, hay retry ở đâu trước?",
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
                "to inspect docs, design a small test, or build a prototype?"
            )
        elif plan.question_type == "follow_up":
            candidate = (
                "From your last answer, pick one technical step you personally handled and "
                "state the input, action, and result."
            )
        elif planner.current_phase == "career":
            candidate = (
                f"For {context.interview_config.target_role or 'this role'}, which backend or AI area "
                "would you most want to learn deeply on the team?"
            )
        else:
            candidate = (
                f"In a project related to {competency}, what did you personally implement "
                "and what technical issue did you run into?"
            )
        alternatives = [
            candidate,
            f"When working on {competency}, what log, test, or metric told you your fix worked?",
            f"If you rebuilt the {competency} part, what technical design would you keep or change?",
            f"How would you explain a bug in {competency} to a teammate using endpoint, input, expected, and actual behavior?",
            f"For {competency}, what config, data, or dependency risk did you handle?",
            f"If {competency} became slow or flaky, where would you inspect logs, timeout, or retry behavior first?",
        ]
    previous_questions = [turn.question for turn in context.history]
    return next(
        (
            alternative
            for alternative in alternatives
            if _find_similar_question(alternative, previous_questions) is None
        ),
        (
            f"Ở lượt {len(context.history) + 1}, em chọn một lỗi khác trong {competency} và nêu cách debug cụ thể được không?"
            if language.startswith("vi")
            else f"For turn {len(context.history) + 1}, pick a different {competency} failure and explain the concrete debugging path."
        ),
    )


def _technical_fallback_question(
    context: InterviewRuntimeContext,
    competency: str,
) -> str:
    language = context.interview_config.language.lower()
    normalized = _normalize_question(competency)
    if language.startswith("vi"):
        if "mongodb" in normalized or "mongo" in normalized:
            candidates = [
                "Cho collection `orders` có các field `user_id`, `status`, `created_at`. Em viết MongoDB query lấy 10 đơn hàng mới nhất của một user đang ở trạng thái `paid` như thế nào?",
                "Với MongoDB, em sẽ tạo index nào cho query lọc theo `user_id`, `status` và sắp xếp theo `created_at` giảm dần?",
                "Nếu query MongoDB trả chậm khi lọc theo `status` và sort `created_at`, em dùng command nào để kiểm tra execution plan?",
                "Cho document thiếu field `status`, query lọc `status: \"paid\"` sẽ xử lý edge case này như thế nào?",
            ]
        elif "sql" in normalized or "postgres" in normalized or "mysql" in normalized:
            candidates = [
                "Cho bảng `orders(user_id, total, created_at)`. Em viết câu SQL tính tổng doanh thu theo từng user trong 30 ngày gần nhất như thế nào?",
                "Cho bảng `users` và `orders`, em viết SQL lấy 5 user có tổng giá trị đơn hàng cao nhất như thế nào?",
                "Với SQL query dùng `JOIN`, nếu kết quả bị nhân đôi số dòng, em kiểm tra khóa join và dữ liệu trùng như thế nào?",
                "Cho input không có order nào trong 30 ngày, query tổng doanh thu nên trả kết quả gì và em xử lý `NULL` ra sao?",
            ]
        elif "python" in normalized:
            candidates = [
                "Em viết một hàm Python nhận list số nguyên và trả về phần tử xuất hiện nhiều nhất như thế nào?",
                "Trong Python, đoạn code đọc file JSON có thể lỗi ở những điểm nào và em xử lý exception ra sao?",
                "Với input `[1, 2, 2, 3]`, hàm đếm tần suất của em trả output gì và xử lý list rỗng thế nào?",
                "Em viết một đoạn Python nhỏ validate payload có `email` và `password`, thiếu field thì trả lỗi gì?",
            ]
        elif "react" in normalized:
            candidates = [
                "Trong React, khi một component re-render quá nhiều vì state thay đổi, em sẽ kiểm tra và tối ưu theo hướng nào?",
                "Em viết một component React nhỏ gọi API khi mount và hiển thị trạng thái loading/error/data như thế nào?",
                "Nếu API trả lỗi 500, component React của em cập nhật state `error` và retry button như thế nào?",
                "Trong React, dependency array sai ở `useEffect` có thể gây bug gì và em debug bằng log nào?",
            ]
        elif "fastapi" in normalized:
            candidates = [
                "Trong FastAPI, em viết một endpoint POST nhận JSON, validate dữ liệu đầu vào và trả về status code phù hợp như thế nào?",
                "Nếu một endpoint FastAPI trả lỗi 500 không rõ nguyên nhân, em debug theo các bước kỹ thuật nào?",
                "Trong FastAPI, em dùng Pydantic schema thế nào để request thiếu `email` trả 422 thay vì crash 500?",
                "Nếu login sai mật khẩu, endpoint FastAPI nên trả status code nào và response body tối thiểu ra sao?",
            ]
        elif "docker" in normalized:
            candidates = [
                "Với Docker, em viết Dockerfile tối thiểu cho app FastAPI chạy bằng Uvicorn ở port 8000 như thế nào?",
                "Container chạy nhưng host không truy cập được port 8000, em kiểm tra `docker ps`, port mapping và bind host như thế nào?",
                "Trong Docker Compose, app không kết nối được database vì dùng `localhost`, em sửa `DB_HOST` và network ra sao?",
                "Nếu image build chậm do copy toàn bộ source trước khi install dependencies, em đổi thứ tự Dockerfile thế nào?",
            ]
        else:
            candidates = [
                f"Với {competency}, em hãy giải một task nhỏ: input là gì, output mong muốn là gì, và code hoặc query chính sẽ viết thế nào?",
                f"Khi dùng {competency}, nếu gặp lỗi runtime cụ thể, em kiểm tra log, config, command hoặc request nào trước?",
                f"Với {competency}, em nêu một edge case làm solution dễ fail và cách xử lý trong code hoặc config?",
            ]
    else:
        if "mongodb" in normalized or "mongo" in normalized:
            candidates = [
                "Given an `orders` collection with `user_id`, `status`, and `created_at`, what MongoDB query returns the 10 newest paid orders for one user?",
                "What MongoDB index would you create for filtering by `user_id` and `status` while sorting by `created_at` descending?",
                "If a MongoDB query filtering by `status` and sorting by `created_at` is slow, which command checks the execution plan?",
                "If a document is missing `status`, how should a query for `status: \"paid\"` handle that edge case?",
            ]
        elif "sql" in normalized or "postgres" in normalized or "mysql" in normalized:
            candidates = [
                "Given `orders(user_id, total, created_at)`, write a SQL query for revenue per user in the last 30 days.",
                "Given `users` and `orders`, write SQL to return the top 5 users by total order value.",
                "If a SQL JOIN duplicates rows unexpectedly, how would you inspect the join key and duplicate data?",
                "If there are no orders in the last 30 days, what should the revenue query return and how would you handle NULL?",
            ]
        elif "python" in normalized:
            candidates = [
                "Write a Python function that takes a list of integers and returns the most frequent element.",
                "When reading a JSON file in Python, what errors can happen and how would you handle them?",
                "For input `[1, 2, 2, 3]`, what output should your frequency function return and how should it handle an empty list?",
                "Write a small Python validation snippet for a payload with `email` and `password`, returning an error when a field is missing.",
            ]
        elif "react" in normalized:
            candidates = [
                "In React, if a component re-renders too often because of state changes, how would you inspect and optimize it?",
                "Write a small React component that calls an API on mount and handles loading, error, and data states.",
                "If an API returns 500, how should your React component update `error` state and expose a retry button?",
                "What bug can a wrong `useEffect` dependency array cause, and what log would you add to debug it?",
            ]
        elif "fastapi" in normalized:
            candidates = [
                "In FastAPI, how would you implement a POST endpoint that accepts JSON, validates input, and returns the right status code?",
                "If a FastAPI endpoint returns an unclear 500 error, what exact technical debugging steps would you take?",
                "In FastAPI, how would you use a Pydantic schema so a missing `email` returns 422 instead of crashing with 500?",
                "For a wrong login password, what status code and minimal response body should a FastAPI endpoint return?",
            ]
        elif "docker" in normalized:
            candidates = [
                "Write a minimal Dockerfile for a FastAPI app served by Uvicorn on port 8000.",
                "A container is running but the host cannot access port 8000; how do you inspect `docker ps`, port mapping, and bind host?",
                "In Docker Compose, the app cannot connect to the database because it uses `localhost`; how would you fix `DB_HOST` and networking?",
                "If an image build is slow because all source is copied before dependency install, how would you reorder the Dockerfile?",
            ]
        else:
            candidates = [
                f"For {competency}, solve a small technical task: what are the inputs, expected output, and code or query approach?",
                f"When using {competency}, if a concrete runtime error appears, which log, config, command, or request would you inspect first?",
                f"For {competency}, name one edge case that can break the solution and how you would handle it in code or config.",
            ]
    previous_questions = [turn.question for turn in context.history]
    return next(
        (
            candidate
            for candidate in candidates
            if _find_similar_question(candidate, previous_questions) is None
        ),
        (
            f"Ở lượt {len(context.history) + 1}, với {competency}, em nêu một lỗi runtime khác và command/log cụ thể để debug?"
            if language.startswith("vi")
            else f"For turn {len(context.history) + 1}, with {competency}, name a different runtime error and the exact command or log to debug it."
        ),
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
    answered_questions = context.question_count
    if _is_technical_check(context):
        if answered_questions < 3:
            return False
        must_have = [item for item in coverage.skills if item.priority == "must_have"]
        if must_have:
            return all(
                item.evidence_count > 0 and item.status not in {"not_assessed", "claimed"}
                for item in must_have
            )
        return len(evaluation_state.competency_status) >= 2

    if answered_questions < 4:
        return False
    if len(evaluation_state.communication_samples) < 2:
        return False

    must_have = [item for item in coverage.skills if item.priority == "must_have"]
    if must_have:
        assessed_must_have = [
            item
            for item in must_have
            if item.evidence_count > 0 and item.status not in {"not_assessed", "claimed"}
        ]
        required_count = len(must_have)
        if len(assessed_must_have) < required_count:
            return False
    if not _has_jd_scenario_evidence(context):
        return False

    phases = {turn.phase for turn in context.history}
    if "cv_verification" not in phases:
        return False
    if phases.intersection({"problem_solving", "behavioral"}):
        return True
    problem_signal = re.compile(
        r"\b(debug|log|bug|root|cause|trade|metric|test|timeout|retry)\b|lỗi|thiết kế",
        re.IGNORECASE,
    )
    return any(problem_signal.search(f"{turn.question} {turn.answer}") for turn in context.history)


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
