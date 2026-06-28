from __future__ import annotations

import json
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any

from pydantic import BaseModel

from app.ai.gateway import ChatMessage, ChatRequest, LLMGateway, get_llm_gateway
from app.ai.interview.prompts import (
    INTERVIEW_COACHING_SYSTEM_PROMPT,
    INTERVIEW_PLANNER_SYSTEM_PROMPT,
    INTERVIEW_REPORT_SYSTEM_PROMPT,
    QUESTION_GENERATOR_SYSTEM_PROMPT,
    TECH_LEAD_REPORT_SYSTEM_PROMPT,
    TECHNICAL_CHECK_REPORT_SYSTEM_PROMPT,
)
from app.ai.interview.schemas import (
    AnswerFeedback,
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
    "thiet ke",
    "flow",
    "xu ly",
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
    "write a command",
    "which command",
    "predict the output",
    "what is the output",
    "what output",
    "exact output",
    "viet command",
    "dung command nao",
    "cau lenh nao",
    "doan output",
    "output la gi",
    "dau ra la gi",
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


class InterviewTurnGenerationError(RuntimeError):
    """Raised when an interview turn cannot be generated safely."""


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
            provider_metadata={"reason": "max_questions_reached"},
        )

    llm = gateway or get_llm_gateway()
    metadata: dict[str, Any] = {}
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
        raise InterviewTurnGenerationError(
            f"Unable to generate a valid interview plan: {str(exc)[:500]}"
        ) from exc

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
        raise InterviewTurnGenerationError(
            "Interview planner attempted to finish before backend evidence requirements were met"
        )

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
        raise InterviewTurnGenerationError(
            f"Unable to generate a valid interview question: {str(exc)[:500]}"
        ) from exc

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


def generate_answer_coaching(
    context: InterviewRuntimeContext,
    *,
    question: str,
    answer: str,
    phase: str,
    question_intent: str,
    topic_key: str,
    evaluation: PreviousAnswerEvaluation,
    gateway: LLMGateway | None = None,
) -> tuple[AnswerFeedback, dict[str, Any]]:
    llm = gateway or get_llm_gateway()
    payload = {
        "language": context.interview_config.language,
        "candidate_level": context.interview_config.candidate_level,
        "target_role": context.interview_config.target_role,
        "phase": phase,
        "topic_key": topic_key,
        "question_intent": question_intent,
        "question": question,
        "answer": answer,
        "cv": context.cv.model_dump(mode="json"),
        "job_description": context.job_description.model_dump(mode="json"),
        "internal_evaluation": evaluation.model_dump(mode="json"),
    }
    return _call_structured(
        llm,
        system_prompt=INTERVIEW_COACHING_SYSTEM_PROMPT,
        payload=payload,
        output_model=AnswerFeedback,
        feature="interview_answer_coach",
    )


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
        intent = _normalize_question(planner.question_plan.question_intent)
        if any(
            term in intent
            for term in {
                "code task",
                "coding task",
                "query task",
                "sql task",
                "command task",
                "output prediction",
                "write code",
                "write query",
                "write sql",
            }
        ):
            raise ValueError("Tech lead planner requested a direct implementation task")
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
        follow_up_limit = (
            1
            if _is_technical_check(context)
            or evaluation.answer_quality in {"vague", "irrelevant"}
            else 2
        )
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
        if _is_tech_lead_direct_task(question):
            raise ValueError("Tech lead question requests code, query, command, or output")


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


def _technical_skill_category(skill_or_text: str) -> str:
    normalized = _normalize_question(skill_or_text)
    if any(term in normalized for term in {"python", "javascript", "typescript", "java", "go", "csharp"}):
        return "language"
    if any(term in normalized for term in {"fastapi", "django", "flask", "api", "endpoint", "pydantic", "jwt"}):
        return "api"
    if any(
        term in normalized
        for term in {
            "sql",
            "postgresql",
            "postgres",
            "mysql",
            "mongodb",
            "mongo",
            "database",
            "db",
            "du lieu",
            "co so du lieu",
            "truy van",
        }
    ):
        return "database"
    if any(term in normalized for term in {"docker", "container", "compose", "uvicorn", "deploy"}):
        return "tooling"
    if any(term in normalized for term in {"ai", "model", "mo hinh", "rag", "vector", "embedding", "llm"}):
        return "ai"
    if any(term in normalized for term in {"debug", "kiem tra", "log", "loi", "exception", "error", "500", "traceback", "timeout"}):
        return "debugging"
    if any(term in normalized for term in {"edge", "case", "null", "empty", "rong", "thieu", "missing", "invalid", "422"}):
        return "edge_case"
    return "general"


def _technical_covered_categories(
    context: InterviewRuntimeContext,
    coverage: CoverageState,
) -> set[str]:
    skill_by_topic = {f"verify_{item.skill_id}": item.skill for item in coverage.skills}
    categories: set[str] = set()
    for turn in context.history:
        text = f"{turn.topic_key} {turn.question} {turn.answer}"
        topic_skill = skill_by_topic.get(turn.topic_key)
        if topic_skill:
            categories.add(_technical_skill_category(topic_skill))
        category = _technical_skill_category(text)
        if category != "general":
            categories.add(category)
        normalized_text = _normalize_question(text)
        if any(term in normalized_text for term in {"debug", "kiem tra", "log", "loi", "exception", "error", "500", "traceback", "timeout", "try except", "zerodivisionerror"}):
            categories.add("debugging")
        if any(term in normalized_text for term in {"edge", "case", "null", "empty", "rong", "thieu", "missing", "invalid", "422"}):
            categories.add("edge_case")
    return categories


def _technical_skill_has_evidence(
    item: CoverageItem,
    context: InterviewRuntimeContext,
    evaluation_state: EvaluationState,
) -> bool:
    if item.evidence_count > 0 and item.status not in {"not_assessed", "claimed"}:
        return True
    skill_name = _normalize_question(item.skill)
    skill_category = _technical_skill_category(item.skill)
    for turn in context.history:
        text = f"{turn.topic_key} {turn.question} {turn.answer}"
        normalized_text = _normalize_question(text)
        if skill_name not in normalized_text and _technical_skill_category(text) != skill_category:
            continue
        topic_state = evaluation_state.topic_evidence.get(turn.topic_key)
        if topic_state and topic_state.evidence_found and topic_state.ownership != "not_owned":
            return True
    return False


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
        if answered_questions < max(5, context.interview_config.min_questions):
            return False
        covered_categories = _technical_covered_categories(context, coverage)
        if len(covered_categories) < 4:
            return False
        if not covered_categories.intersection({"debugging", "edge_case"}):
            return False
        must_have = [item for item in coverage.skills if item.priority == "must_have"]
        if must_have:
            return all(
                _technical_skill_has_evidence(item, context, evaluation_state)
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
