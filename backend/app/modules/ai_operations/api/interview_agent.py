from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.extraction.schemas import CVExtraction, JDExtraction, SkillEvidence
from app.ai.interview.schemas import (
    AnswerFeedback,
    CandidateInterviewResponse,
    ConversationTurn,
    CoverageState,
    EvaluationState,
    InterviewAnswerRequest,
    InterviewConfig,
    InterviewRuntimeContext,
    InterviewTurnResult,
    MatchingResult,
    PreviousAnswerEvaluation,
)
from app.ai.interview.service import (
    InterviewTurnGenerationError,
    generate_answer_coaching,
    generate_interview_report,
    generate_next_turn,
)
from app.ai.matching.skills import normalize_skills
from app.modules.access.api.auth import get_current_user
from app.modules.ai_operations.infrastructure.interview_models import (
    AIInterviewSession,
    AIInterviewTurn,
)
from app.modules.opportunities.infrastructure.models import Job
from app.modules.recruitment.infrastructure.models import CV
from app.platform.database.models import User
from app.platform.database.models.base import uuid_str
from app.platform.database.session import get_db
from app.shared.errors import AppError, ErrorCode

router = APIRouter(prefix="/ai/interviews", tags=["ai-interviews"])


def _raise_interview_generation_error(exc: Exception) -> None:
    raise AppError(
        code=ErrorCode.UPSTREAM_UNAVAILABLE,
        message="AI interview generation failed",
        status_code=502,
        details={"error": str(exc)[:500]},
    ) from exc


class StartInterviewRequest(BaseModel):
    cv_id: str
    job_id: str
    interview_config: InterviewConfig = Field(default_factory=InterviewConfig)


class InterviewTurnView(BaseModel):
    sequence: int
    phase: str
    topic_key: str
    question: str
    answer: str | None = None
    feedback: AnswerFeedback | None = None
    attempts: list[dict[str, Any]] = Field(default_factory=list)


class AcceptInterviewAnswerRequest(BaseModel):
    attempt_id: str = Field(min_length=1, max_length=36)


class InterviewSessionSummary(BaseModel):
    session_id: str
    job_id: str
    cv_id: str
    interview_mode: str
    status: str
    current_phase: str
    question_count: int
    job_title: str
    created_at: datetime
    updated_at: datetime | None = None
    has_report: bool


class InterviewSessionDetail(InterviewSessionSummary):
    report: dict[str, Any] | None = None
    turns: list[InterviewTurnView] = Field(default_factory=list)


@router.post("/sessions", response_model=CandidateInterviewResponse, status_code=201)
def start_interview(
    payload: StartInterviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CandidateInterviewResponse:
    cv = db.get(CV, payload.cv_id)
    if not cv or cv.deleted_at is not None or cv.student_id != current_user.id:
        raise AppError(code=ErrorCode.NOT_FOUND, message="CV not found", status_code=404)
    job = db.get(Job, payload.job_id)
    if not job or job.deleted_at is not None:
        raise AppError(code=ErrorCode.NOT_FOUND, message="Job not found", status_code=404)

    cv_data = _cv_extraction(cv)
    jd_data = _jd_extraction(job)
    matching = _matching_result(cv_data, jd_data)
    technical_check = payload.interview_config.interview_mode == "technical_check"
    config_updates = {
        "target_role": payload.interview_config.target_role or job.title,
        "current_phase": "cv_verification" if technical_check else "career",
        "allowed_next_phases": (
            ["cv_verification", "problem_solving", "completed"]
            if technical_check
            else payload.interview_config.allowed_next_phases
        ),
    }
    provided_config_fields = payload.interview_config.model_fields_set
    if "max_questions" not in provided_config_fields:
        config_updates["max_questions"] = 10 if technical_check else 12
    if "min_questions" not in provided_config_fields:
        config_updates["min_questions"] = 3
    if "max_follow_ups_per_topic" not in provided_config_fields:
        config_updates["max_follow_ups_per_topic"] = 2
    config = payload.interview_config.model_copy(
        update=config_updates
    )
    runtime = InterviewRuntimeContext(
        cv=cv_data,
        job_description=jd_data,
        matching_result=matching,
        interview_config=config,
    )
    try:
        result = generate_next_turn(runtime)
    except InterviewTurnGenerationError as exc:
        _raise_interview_generation_error(exc)

    session = AIInterviewSession(
        user_id=current_user.id,
        cv_id=cv.id,
        job_id=job.id,
        status="COMPLETED" if result.planner_output.should_end_interview else "ACTIVE",
        current_phase=result.planner_output.current_phase,
        question_count=0 if result.planner_output.should_end_interview else 1,
        config=config.model_dump(mode="json"),
        cv_snapshot=cv_data.model_dump(mode="json"),
        jd_snapshot=jd_data.model_dump(mode="json"),
        matching_result=matching.model_dump(mode="json"),
        coverage_state=result.coverage_state.model_dump(mode="json"),
        evaluation_state=result.evaluation_state.model_dump(mode="json"),
    )
    db.add(session)
    db.flush()
    if result.question:
        db.add(_new_turn(session.id, 1, result))
    db.commit()
    db.refresh(session)
    return _candidate_response(session, result.question)


@router.get("/sessions", response_model=list[InterviewSessionSummary])
def list_interview_sessions(
    job_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[InterviewSessionSummary]:
    query = (
        select(AIInterviewSession)
        .where(AIInterviewSession.user_id == current_user.id)
        .order_by(AIInterviewSession.created_at.desc())
        .limit(50)
    )
    if job_id:
        query = query.where(AIInterviewSession.job_id == job_id)
    sessions = list(db.scalars(query))
    return [_session_summary(session) for session in sessions]


@router.get("/sessions/{session_id}", response_model=InterviewSessionDetail)
def get_interview_session(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> InterviewSessionDetail:
    session = db.get(AIInterviewSession, session_id)
    if not session or session.user_id != current_user.id:
        raise AppError(
            code=ErrorCode.NOT_FOUND,
            message="Interview session not found",
            status_code=404,
        )
    turns = list(
        db.scalars(
            select(AIInterviewTurn)
            .where(AIInterviewTurn.session_id == session.id)
            .order_by(AIInterviewTurn.sequence)
        )
    )
    summary = _session_summary(session)
    return InterviewSessionDetail(
        **summary.model_dump(),
        report=(session.evaluation_state or {}).get("final_report"),
        turns=[
            InterviewTurnView(
                sequence=turn.sequence,
                phase=turn.phase,
                topic_key=turn.topic_key,
                question=turn.question,
                answer=turn.answer,
                feedback=_accepted_feedback(turn),
                attempts=[
                    {
                        "attempt_id": attempt.get("attempt_id"),
                        "answer": attempt.get("answer"),
                        "feedback": _attempt_feedback(attempt, turn),
                    }
                    for attempt in turn.internal_output.get("practice_attempts", [])
                ],
            )
            for turn in turns
        ],
    )


@router.delete("/sessions/{session_id}", status_code=204)
def delete_interview_session(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    session = db.get(AIInterviewSession, session_id)
    if not session or session.user_id != current_user.id:
        raise AppError(
            code=ErrorCode.NOT_FOUND,
            message="Interview session not found",
            status_code=404,
        )
    db.delete(session)
    db.commit()
    return Response(status_code=204)


@router.post(
    "/sessions/{session_id}/answers",
    response_model=CandidateInterviewResponse,
)
def answer_interview_question(
    session_id: str,
    payload: InterviewAnswerRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CandidateInterviewResponse:
    session = db.get(AIInterviewSession, session_id)
    if not session or session.user_id != current_user.id:
        raise AppError(
            code=ErrorCode.NOT_FOUND,
            message="Interview session not found",
            status_code=404,
        )
    if session.status != "ACTIVE":
        raise AppError(
            code=ErrorCode.BAD_REQUEST,
            message="Interview session is already completed",
            status_code=400,
        )
    turns = list(
        db.scalars(
            select(AIInterviewTurn)
            .where(AIInterviewTurn.session_id == session.id)
            .order_by(AIInterviewTurn.sequence)
        )
    )
    if not turns or turns[-1].answer is not None:
        raise AppError(
            code=ErrorCode.BAD_REQUEST,
            message="No pending interview question",
            status_code=400,
        )
    history = [
        ConversationTurn(
            question=turn.question,
            answer=(
                payload.answer
                if turn.id == turns[-1].id
                else turn.answer or ""
            ),
            phase=turn.phase,
            topic_key=turn.topic_key,
        )
        for turn in turns
    ]
    config = InterviewConfig.model_validate(session.config)
    config = config.model_copy(update={"current_phase": session.current_phase})
    previous_internal = turns[-1].internal_output
    runtime = InterviewRuntimeContext(
        cv=CVExtraction.model_validate(session.cv_snapshot),
        job_description=JDExtraction.model_validate(session.jd_snapshot),
        matching_result=MatchingResult.model_validate(session.matching_result),
        interview_config=config,
        history=history,
        evaluation_state=EvaluationState.model_validate(session.evaluation_state),
        coverage_state=CoverageState.model_validate(session.coverage_state),
        question_count=session.question_count,
        current_topic=previous_internal.get("question_plan", {}).get("topic_key"),
        current_difficulty=previous_internal.get("question_plan", {}).get("difficulty"),
        follow_up_count=int(previous_internal.get("follow_up_count", 0)),
        latest_answer=payload.answer,
    )
    try:
        result = generate_next_turn(runtime)
    except InterviewTurnGenerationError as exc:
        _raise_interview_generation_error(exc)
    evaluation = result.planner_output.previous_answer_evaluation
    if evaluation is None:
        _raise_interview_generation_error(RuntimeError("Unable to evaluate this answer"))
    question_intent = str(
        previous_internal.get("question_plan", {}).get("question_intent") or ""
    )
    try:
        coaching, coaching_metadata = generate_answer_coaching(
            runtime,
            question=turns[-1].question,
            answer=payload.answer,
            phase=turns[-1].phase,
            question_intent=question_intent,
            topic_key=turns[-1].topic_key,
            evaluation=evaluation,
        )
        feedback = _public_feedback(
            evaluation,
            phase=turns[-1].phase,
            question=turns[-1].question,
            question_intent=question_intent,
            coaching=coaching,
        )
    except Exception as exc:
        _raise_interview_generation_error(exc)
    attempt_id = uuid_str()
    attempts = list(turns[-1].internal_output.get("practice_attempts", []))
    attempts.append(
        {
            "attempt_id": attempt_id,
            "answer": payload.answer,
            "feedback": feedback.model_dump(mode="json"),
            "coaching_metadata": coaching_metadata,
            "result": result.model_dump(mode="json"),
        }
    )
    turns[-1].internal_output = {
        **turns[-1].internal_output,
        "practice_attempts": attempts[-5:],
    }
    db.commit()
    return CandidateInterviewResponse(
        session_id=session.id,
        question="",
        current_phase=session.current_phase,
        should_end_interview=False,
        attempt_id=attempt_id,
        feedback=feedback,
        awaiting_acceptance=True,
    )


@router.post(
    "/sessions/{session_id}/answers/accept",
    response_model=CandidateInterviewResponse,
)
def accept_interview_answer(
    session_id: str,
    payload: AcceptInterviewAnswerRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CandidateInterviewResponse:
    session = db.get(AIInterviewSession, session_id)
    if not session or session.user_id != current_user.id:
        raise AppError(
            code=ErrorCode.NOT_FOUND,
            message="Interview session not found",
            status_code=404,
        )
    if session.status != "ACTIVE":
        raise AppError(
            code=ErrorCode.BAD_REQUEST,
            message="Interview session is already completed",
            status_code=400,
        )
    turns = list(
        db.scalars(
            select(AIInterviewTurn)
            .where(AIInterviewTurn.session_id == session.id)
            .order_by(AIInterviewTurn.sequence)
        )
    )
    if not turns or turns[-1].answer is not None:
        raise AppError(
            code=ErrorCode.BAD_REQUEST,
            message="No pending interview question",
            status_code=400,
        )
    current_turn = turns[-1]
    attempt = next(
        (
            item
            for item in current_turn.internal_output.get("practice_attempts", [])
            if item.get("attempt_id") == payload.attempt_id
        ),
        None,
    )
    if not attempt:
        raise AppError(
            code=ErrorCode.NOT_FOUND,
            message="Answer attempt not found",
            status_code=404,
        )

    result_data = attempt.get("result") or {}
    result = InterviewTurnResult.model_validate(result_data)
    current_turn.answer = str(attempt.get("answer") or "")
    current_turn.internal_output = {
        **current_turn.internal_output,
        "accepted_attempt_id": payload.attempt_id,
        "accepted_feedback": attempt.get("feedback"),
        "accepted_evaluation": (
            result.planner_output.previous_answer_evaluation.model_dump(mode="json")
            if result.planner_output.previous_answer_evaluation
            else None
        ),
    }
    session.current_phase = result.planner_output.current_phase
    session.coverage_state = result.coverage_state.model_dump(mode="json")
    session.evaluation_state = result.evaluation_state.model_dump(mode="json")
    if result.planner_output.should_end_interview:
        session.status = "COMPLETED"
        report_context = _runtime_for_accepted_answer(
            session,
            turns,
            current_turn.answer,
        ).model_copy(
            update={
                "coverage_state": result.coverage_state,
                "evaluation_state": result.evaluation_state,
            },
        )
        evaluations = [
            evaluation
            for turn in turns
            if (evaluation := turn.internal_output.get("accepted_evaluation"))
        ]
        try:
            report, report_metadata = generate_interview_report(
                report_context,
                answer_evaluations=evaluations,
            )
        except Exception as exc:
            _raise_interview_generation_error(exc)
        session.evaluation_state = {
            **session.evaluation_state,
            "final_report": report.model_dump(mode="json"),
            "report_metadata": report_metadata,
        }
    elif result.question:
        session.question_count += 1
        db.add(_new_turn(session.id, session.question_count, result))
    db.commit()
    return _candidate_response(session, result.question)


def _new_turn(
    session_id: str,
    sequence: int,
    result: Any,
) -> AIInterviewTurn:
    planner = result.planner_output
    return AIInterviewTurn(
        session_id=session_id,
        sequence=sequence,
        phase=planner.current_phase,
        topic_key=planner.question_plan.topic_key,
        question=result.question,
        internal_output={
            **planner.model_dump(mode="json"),
            "provider_metadata": result.provider_metadata,
        },
    )


def _candidate_response(
    session: AIInterviewSession,
    question: str,
) -> CandidateInterviewResponse:
    return CandidateInterviewResponse(
        session_id=session.id,
        question=question,
        current_phase=session.current_phase,
        should_end_interview=session.status == "COMPLETED",
        report=(session.evaluation_state or {}).get("final_report"),
    )


def _runtime_for_accepted_answer(
    session: AIInterviewSession,
    turns: list[AIInterviewTurn],
    latest_answer: str,
) -> InterviewRuntimeContext:
    config = InterviewConfig.model_validate(session.config).model_copy(
        update={"current_phase": session.current_phase}
    )
    current_internal = turns[-1].internal_output
    return InterviewRuntimeContext(
        cv=CVExtraction.model_validate(session.cv_snapshot),
        job_description=JDExtraction.model_validate(session.jd_snapshot),
        matching_result=MatchingResult.model_validate(session.matching_result),
        interview_config=config,
        history=[
            ConversationTurn(
                question=turn.question,
                answer=turn.answer or "",
                phase=turn.phase,
                topic_key=turn.topic_key,
            )
            for turn in turns
        ],
        evaluation_state=EvaluationState.model_validate(session.evaluation_state),
        coverage_state=CoverageState.model_validate(session.coverage_state),
        question_count=session.question_count,
        current_topic=current_internal.get("question_plan", {}).get("topic_key"),
        current_difficulty=current_internal.get("question_plan", {}).get("difficulty"),
        follow_up_count=int(current_internal.get("follow_up_count", 0)),
        latest_answer=latest_answer,
    )


_EMPTY_FEEDBACK_VALUES = {
    "",
    "none",
    "n/a",
    "na",
    "not applicable",
    "none for this project",
    "no gap",
    "nothing",
}
_ENGLISH_FEEDBACK_MARKERS = {
    "the",
    "candidate",
    "provided",
    "demonstrated",
    "mentioned",
    "explained",
    "clear",
    "role",
    "definition",
    "comprehensive",
    "coverage",
    "focus",
    "performance",
    "trade-offs",
    "metrics",
    "techniques",
    "used",
    "optimization",
    "inference",
    "pipeline",
    "latency",
    "integration",
    "and",
    "deep",
    "tools",
    "like",
    "industry-standard",
    "answer",
    "missing",
    "specific",
    "concrete",
    "understanding",
    "regarding",
    "technical",
    "project",
    "implementation",
    "details",
}
_VIETNAMESE_CHARACTERS = set(
    "ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệ"
    "íìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ"
)
_VIETNAMESE_FEEDBACK_MARKERS = {
    "bạn",
    "câu",
    "trả",
    "lời",
    "đã",
    "có",
    "chưa",
    "cần",
    "bổ",
    "sung",
    "trình",
    "bày",
    "kỹ",
    "thuật",
    "dự",
    "án",
    "vai",
    "trò",
    "hiệu",
    "năng",
    "tối",
    "ưu",
    "làm",
    "rõ",
}


def _vietnamese_feedback_text(value: str) -> str:
    text = value.strip().rstrip(".")
    normalized = " ".join(text.lower().split())
    if normalized in _EMPTY_FEEDBACK_VALUES:
        return ""
    words = {
        token.strip(".,:;!?()[]{}\"'")
        for token in normalized.replace("/", " ").split()
    }
    has_vietnamese_signal = (
        any(character in _VIETNAMESE_CHARACTERS for character in normalized)
        or bool(words & _VIETNAMESE_FEEDBACK_MARKERS)
    )
    if not has_vietnamese_signal:
        return ""
    if len(words & _ENGLISH_FEEDBACK_MARKERS) >= 2 and not has_vietnamese_signal:
        return ""
    return text


def _feedback_context_text(
    *,
    phase: str,
    question: str = "",
    question_intent: str = "",
) -> str:
    return " ".join([phase, question, question_intent]).lower()


def _is_role_fit_phase(phase: str) -> bool:
    return phase == "career"


def _is_behavioral_phase(phase: str) -> bool:
    return phase == "behavioral"


def _is_candidate_question_phase(phase: str) -> bool:
    return phase == "candidate_questions"


def _is_technical_feedback_context(
    *,
    phase: str,
    question: str = "",
    question_intent: str = "",
) -> bool:
    if phase in {"cv_verification", "problem_solving"}:
        return True
    context = _feedback_context_text(
        phase=phase,
        question=question,
        question_intent=question_intent,
    )
    return any(
        term in context
        for term in {
            "technical",
            "kỹ thuật",
            "project",
            "dự án",
            "system",
            "hệ thống",
            "debug",
            "architecture",
            "thiết kế",
        }
    )


def _is_ownership_feedback_context(
    *,
    phase: str,
    question: str = "",
    question_intent: str = "",
) -> bool:
    if phase in {"career", "candidate_questions"}:
        return False
    context = _feedback_context_text(
        phase=phase,
        question=question,
        question_intent=question_intent,
    )
    return any(
        term in context
        for term in {
            "vai trò",
            "phụ trách",
            "trách nhiệm",
            "bạn đã làm",
            "hành động của bạn",
            "quyết định của bạn",
            "dự án",
            "kinh nghiệm",
            "ownership",
            "responsibility",
            "personally",
            "your role",
            "your action",
            "project",
            "experience",
        }
    )


def _is_technical_coaching_text(value: str) -> bool:
    normalized = value.lower()
    return any(
        term in normalized
        for term in {
            "api",
            "service",
            "request",
            "concurrency",
            "latency",
            "throughput",
            "fps",
            "inference",
            "pipeline",
            "deployment",
            "đóng gói",
            "triển khai mô hình",
            "monitoring",
        }
    )


def _public_feedback(
    evaluation: PreviousAnswerEvaluation,
    *,
    phase: str,
    question: str = "",
    question_intent: str = "",
    coaching: AnswerFeedback | None = None,
) -> AnswerFeedback:
    if coaching is None:
        raise ValueError("Interview coaching output is required")
    technical_context = _is_technical_feedback_context(
        phase=phase,
        question=question,
        question_intent=question_intent,
    )
    ownership_context = _is_ownership_feedback_context(
        phase=phase,
        question=question,
        question_intent=question_intent,
    )
    summary = _vietnamese_feedback_text(coaching.summary)
    if not summary:
        raise ValueError("Interview coaching summary is invalid")
    strengths = [
        text
        for item in coaching.strengths
        if (text := _vietnamese_feedback_text(item))
    ]
    if not strengths:
        raise ValueError("Interview coaching strengths are invalid")
    improvements = [
        text
        for item in coaching.improvements
        if (text := _vietnamese_feedback_text(item))
        and (technical_context or not _is_technical_coaching_text(text))
    ]
    if not improvements and evaluation.answer_quality != "sufficient":
        raise ValueError("Interview coaching improvements are invalid")

    tags = [
        text
        for item in coaching.tags
        if (text := _vietnamese_feedback_text(item))
        and (technical_context or not _is_technical_coaching_text(text))
        and (
            ownership_context
            or all(term not in text.lower() for term in {"vai trò", "phần việc"})
        )
    ]
    quality_tags = {
        "sufficient": "Khá tốt",
        "partial": "Đúng hướng, chưa đủ sâu",
        "vague": "Còn chung chung",
        "irrelevant": "Chưa đúng trọng tâm",
        "unable_to_answer": "Chưa có đủ thông tin",
    }
    if quality_tag := quality_tags.get(evaluation.answer_quality):
        tags.insert(0, quality_tag)

    communication = evaluation.communication
    if communication.clarity >= 3:
        tags.append("Trình bày rõ ràng")
    elif communication.clarity <= 1:
        tags.append("Cần diễn đạt rõ hơn")
    if communication.specificity >= 3:
        tags.append("Có chi tiết cụ thể")
    elif communication.specificity <= 1:
        tags.append("Thiếu ví dụ cụ thể")
    if communication.relevance >= 3:
        tags.append("Đúng trọng tâm")
    if ownership_context and evaluation.ownership == "unknown":
        tags.append("Chưa rõ vai trò cá nhân")
    elif ownership_context and evaluation.ownership == "direct":
        tags.append("Thể hiện rõ vai trò")

    gap = _vietnamese_feedback_text(evaluation.remaining_gap)
    if gap and evaluation.answer_quality != "sufficient":
        if technical_context or not _is_technical_coaching_text(gap):
            tags.append(f"Chưa sâu: {gap[:90]}")

    return AnswerFeedback(
        summary=summary[:500],
        tags=list(dict.fromkeys(tags))[:8],
        strengths=list(dict.fromkeys(strengths))[:3],
        improvements=list(dict.fromkeys(improvements))[:3],
    )


def _sanitize_stored_feedback(raw: Any) -> AnswerFeedback | None:
    if not raw:
        return None
    feedback = AnswerFeedback.model_validate(raw)
    summary = _vietnamese_feedback_text(feedback.summary)
    if not summary:
        return None
    tags = [
        text for item in feedback.tags if (text := _vietnamese_feedback_text(item))
    ]
    strengths = [
        text
        for item in feedback.strengths
        if (text := _vietnamese_feedback_text(item))
    ]
    improvements = [
        text
        for item in feedback.improvements
        if (text := _vietnamese_feedback_text(item))
    ]
    return AnswerFeedback(
        summary=summary,
        tags=tags,
        strengths=strengths,
        improvements=improvements,
    )


def _accepted_feedback(turn: AIInterviewTurn) -> AnswerFeedback | None:
    raw = turn.internal_output.get("accepted_feedback")
    if raw:
        return _sanitize_stored_feedback(raw)
    return None


def _attempt_feedback(
    attempt: dict[str, Any],
    turn: AIInterviewTurn,
) -> AnswerFeedback | None:
    raw = attempt.get("feedback")
    if raw:
        return _sanitize_stored_feedback(raw)
    return None


def _session_summary(session: AIInterviewSession) -> InterviewSessionSummary:
    config = session.config or {}
    jd_snapshot = session.jd_snapshot or {}
    return InterviewSessionSummary(
        session_id=session.id,
        job_id=session.job_id,
        cv_id=session.cv_id,
        interview_mode=str(config.get("interview_mode") or "tech_lead"),
        status=session.status,
        current_phase=session.current_phase,
        question_count=session.question_count,
        job_title=str(jd_snapshot.get("title") or config.get("target_role") or ""),
        created_at=session.created_at,
        updated_at=session.updated_at,
        has_report=bool((session.evaluation_state or {}).get("final_report")),
    )


def _cv_extraction(cv: CV) -> CVExtraction:
    if cv.parsed_data:
        try:
            parsed = dict(cv.parsed_data)
            nested = parsed.get("gemini_extraction")
            extraction_data = dict(nested) if isinstance(nested, dict) else {}
            extraction_data.update(parsed)
            raw_markdown = (
                parsed.get("raw_markdown")
                or parsed.get("raw_text")
                or extraction_data.get("raw_markdown")
                or ""
            )
            extraction_data["raw_markdown"] = raw_markdown
            return CVExtraction.model_validate(extraction_data)
        except ValueError:
            pass
    return CVExtraction(
        summary=cv.summary or "",
        skills=[SkillEvidence(name=name) for name in (cv.skills or [])],
        education=cv.education_history or [],
        experiences=cv.work_experience or [],
        projects=cv.projects or [],
        certifications=[
            str(item.get("name", item)) if isinstance(item, dict) else str(item)
            for item in (cv.certificates or [])
        ],
        raw_markdown=str(
            (cv.parsed_data or {}).get("raw_markdown")
            or (cv.parsed_data or {}).get("raw_text")
            or ""
        ),
        raw_text_quality="unknown",
        confidence=0.5,
    )


def _jd_extraction(job: Job) -> JDExtraction:
    raw_text = "\n\n".join(
        part
        for part in (
            f"# {job.title}",
            job.description,
            job.requirements or "",
            job.responsibilities or "",
        )
        if part.strip()
    )[:80_000]
    if job.parsed_requirements:
        try:
            return JDExtraction.model_validate(job.parsed_requirements).model_copy(
                update={"raw_text": raw_text}
            )
        except ValueError:
            pass
    requirements = job.requirements or job.description
    return JDExtraction(
        title=job.title,
        description=job.description,
        raw_text=raw_text,
        required_skills=[
            SkillEvidence(name=name, evidence=requirements[:500])
            for name in (job.skills or [])
        ],
        responsibilities=[
            item.strip()
            for item in (job.responsibilities or "").splitlines()
            if item.strip()
        ][:60],
        seniority=_candidate_seniority(job),
        employment_type=job.job_type.value if job.job_type else "",
        confidence=0.5,
    )


def _matching_result(cv: CVExtraction, jd: JDExtraction) -> MatchingResult:
    cv_skills = set(normalize_skills([item.name for item in cv.skills]))
    jd_skills = set(normalize_skills([item.name for item in jd.required_skills]))
    matched = sorted(cv_skills & jd_skills)
    missing = sorted(jd_skills - cv_skills)
    score = round(len(matched) / max(1, len(jd_skills)) * 100, 2)
    return MatchingResult(matched_skills=matched, missing_skills=missing, score=score)


def _candidate_seniority(job: Job) -> str:
    value = job.experience_level.value.lower() if job.experience_level else ""
    if "intern" in value:
        return "intern"
    if "junior" in value or "entry" in value:
        return "junior"
    return "unknown"
