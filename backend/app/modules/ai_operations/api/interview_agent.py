from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.extraction.schemas import CVExtraction, JDExtraction, SkillEvidence
from app.ai.interview.schemas import (
    CandidateInterviewResponse,
    ConversationTurn,
    CoverageState,
    EvaluationState,
    InterviewAnswerRequest,
    InterviewConfig,
    InterviewRuntimeContext,
    MatchingResult,
)
from app.ai.interview.service import generate_interview_report, generate_next_turn
from app.ai.matching.skills import normalize_skills
from app.modules.access.api.auth import get_current_user
from app.modules.ai_operations.infrastructure.interview_models import (
    AIInterviewSession,
    AIInterviewTurn,
)
from app.modules.opportunities.infrastructure.models import Job
from app.modules.recruitment.infrastructure.models import CV
from app.platform.database.models import User
from app.platform.database.session import get_db
from app.shared.errors import AppError, ErrorCode

router = APIRouter(prefix="/ai/interviews", tags=["ai-interviews"])


class StartInterviewRequest(BaseModel):
    cv_id: str
    job_id: str
    interview_config: InterviewConfig = Field(default_factory=InterviewConfig)


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
    config = payload.interview_config.model_copy(
        update={
            "target_role": payload.interview_config.target_role or job.title,
            "current_phase": "career",
        }
    )
    runtime = InterviewRuntimeContext(
        cv=cv_data,
        job_description=jd_data,
        matching_result=matching,
        interview_config=config,
    )
    result = generate_next_turn(runtime)

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
    turns[-1].answer = payload.answer
    history = [
        ConversationTurn(
            question=turn.question,
            answer=turn.answer or "",
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
        follow_up_count=int(previous_internal.get("follow_up_count", 0)),
        latest_answer=payload.answer,
    )
    result = generate_next_turn(runtime)
    session.current_phase = result.planner_output.current_phase
    session.coverage_state = result.coverage_state.model_dump(mode="json")
    session.evaluation_state = result.evaluation_state.model_dump(mode="json")
    if result.planner_output.should_end_interview:
        session.status = "COMPLETED"
        report_context = runtime.model_copy(
            update={
                "history": history,
                "coverage_state": result.coverage_state,
                "evaluation_state": result.evaluation_state,
            }
        )
        evaluations = [
            evaluation
            for turn in turns
            if (evaluation := turn.internal_output.get("previous_answer_evaluation"))
        ]
        if result.planner_output.previous_answer_evaluation:
            evaluations.append(
                result.planner_output.previous_answer_evaluation.model_dump(mode="json")
            )
        report, report_metadata = generate_interview_report(
            report_context,
            answer_evaluations=evaluations,
        )
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


def _cv_extraction(cv: CV) -> CVExtraction:
    if cv.parsed_data:
        try:
            return CVExtraction.model_validate(cv.parsed_data)
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
        raw_text_quality="unknown",
        confidence=0.5,
    )


def _jd_extraction(job: Job) -> JDExtraction:
    if job.parsed_requirements:
        try:
            return JDExtraction.model_validate(job.parsed_requirements)
        except ValueError:
            pass
    requirements = job.requirements or job.description
    return JDExtraction(
        title=job.title,
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
