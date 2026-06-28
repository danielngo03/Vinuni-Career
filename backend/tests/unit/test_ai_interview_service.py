from __future__ import annotations

import json

import pytest

from app.ai.extraction.schemas import CVExtraction, JDExtraction, ProjectItem, SkillEvidence
from app.ai.gateway.schemas import ChatResponse
from app.ai.interview.schemas import (
    CommunicationEvaluation,
    ConversationTurn,
    CoverageItem,
    CoverageState,
    EvaluationState,
    InterviewConfig,
    InterviewRuntimeContext,
    MatchingResult,
    TopicEvidenceState,
)
from app.ai.interview.service import (
    InterviewTurnGenerationError,
    _has_enough_evidence_to_finish,
    _skill_has_interview_evidence,
    _validate_candidate_question,
    generate_interview_report,
    generate_next_turn,
)


class FakeGateway:
    def __init__(self, responses: list[dict | str]) -> None:
        self.responses = responses
        self.requests = []

    def chat(self, request):
        self.requests.append(request)
        response = self.responses.pop(0)
        content = response if isinstance(response, str) else json.dumps(response)
        return ChatResponse(
            content=content,
            provider="fake",
            model="fake-model",
            input_tokens=10,
            output_tokens=10,
        )


def _runtime(**updates) -> InterviewRuntimeContext:
    runtime = InterviewRuntimeContext(
        cv=CVExtraction(
            summary="Backend student",
            skills=[SkillEvidence(name="Python", evidence="Built an API")],
        ),
        job_description=JDExtraction(
            title="Backend Intern",
            required_skills=[
                SkillEvidence(name="Python"),
                SkillEvidence(name="FastAPI"),
            ],
            seniority="intern",
        ),
        matching_result=MatchingResult(
            matched_skills=["python"],
            missing_skills=["fastapi"],
            score=50,
        ),
        interview_config=InterviewConfig(
            language="vi",
            candidate_level="student",
            target_role="Backend Intern",
            current_phase="career",
            min_questions=2,
            max_questions=4,
        ),
    )
    return runtime.model_copy(update=updates)


def _planner(**updates) -> dict:
    payload = {
        "action": "ask_initial_question",
        "current_phase": "career",
        "suggested_next_phase": None,
        "question_plan": {
            "question_type": "initial",
            "difficulty": "easy",
            "target_competency": "career motivation",
            "source_type": "jd_requirement",
            "source_reference": "Backend Intern",
            "evidence_gap": "Motivation has not been assessed.",
            "question_intent": "Understand role motivation.",
            "topic_key": "career_motivation",
            "linked_skill_ids": [],
        },
        "previous_answer_evaluation": None,
        "internal_reason": "First question.",
        "expected_signals": ["specific motivation"],
        "evaluated_skill_ids": [],
        "follow_up_count": 0,
        "phase_completion_signal": None,
        "should_end_interview": False,
    }
    payload.update(updates)
    return payload


def test_first_question_has_no_fake_zero_score():
    gateway = FakeGateway(
        [
            _planner(),
            {"question": "Điều gì khiến em muốn ứng tuyển vị trí Backend Intern?"},
        ]
    )

    result = generate_next_turn(_runtime(), gateway=gateway)

    assert result.planner_output.action == "ask_initial_question"
    assert result.planner_output.previous_answer_evaluation is None
    assert result.question.startswith("Điều gì")
    assert len(gateway.requests) == 2


def test_follow_up_updates_previous_skill_and_keeps_internal_data_out_of_question():
    planner = _planner(
        action="ask_initial_question",
        current_phase="cv_verification",
        question_plan={
            "question_type": "initial",
            "difficulty": "easy",
            "target_competency": "FastAPI",
            "source_type": "jd_requirement",
            "source_reference": "FastAPI",
            "evidence_gap": "FastAPI has not been assessed.",
            "question_intent": "request_evidence",
            "topic_key": "verify_fastapi",
            "linked_skill_ids": ["fastapi"],
        },
        previous_answer_evaluation={
            "score": 3,
            "status": "verified",
            "answer_quality": "sufficient",
            "strengths": ["Specific Python API example"],
            "missing_evidence": [],
            "contradictions": [],
            "detected_competency": "Python API development",
            "evidence_found": ["Built an API for a student project"],
            "remaining_gap": "",
            "ownership": "direct",
            "topic_decision": "continue",
            "reason_for_next_question": "Python has enough evidence; assess FastAPI next.",
            "anti_repetition_check": "FastAPI has not been asked yet.",
            "ownership_check": "The candidate directly built the Python API.",
            "communication": {
                "clarity": 3,
                "specificity": 3,
                "relevance": 4,
                "structure": 3,
                "summary": "Clear and relevant.",
            },
        },
        evaluated_skill_ids=["python"],
    )
    gateway = FakeGateway(
        [
            planner,
            {"question": "Em đã sử dụng FastAPI trong dự án nào và trực tiếp làm phần nào?"},
        ]
    )
    runtime = _runtime(
        interview_config=_runtime().interview_config.model_copy(
            update={"current_phase": "cv_verification"}
        ),
        history=[
            ConversationTurn(
                question="Em đã dùng Python ở đâu?",
                answer="Em xây API cho đồ án.",
                phase="cv_verification",
                topic_key="verify_python",
            )
        ],
        question_count=1,
        latest_answer="Em xây API cho đồ án.",
    )

    result = generate_next_turn(runtime, gateway=gateway)

    python = next(item for item in result.coverage_state.skills if item.skill_id == "python")
    assert python.status == "verified"
    assert python.ownership == "direct"
    assert python.evidence_summaries == ["Built an API for a student project"]
    assert (
        result.evaluation_state.topic_evidence["verify_python"].evidence_found
        == ["Built an API for a student project"]
    )
    assert "score" not in result.question.lower()
    assert "expected_signals" not in result.question.lower()


def test_partial_answer_can_switch_topic_when_planner_does_not_clarify():
    planner = _planner(
        action="ask_question",
        current_phase="cv_verification",
        question_plan={
            "question_type": "transition",
            "difficulty": "easy",
            "target_competency": "Docker deployment",
            "source_type": "jd_requirement",
            "source_reference": "Docker",
            "evidence_gap": "Docker has not been assessed.",
            "question_intent": "probe deployment reasoning",
            "topic_key": "verify_docker",
            "linked_skill_ids": ["docker"],
        },
        previous_answer_evaluation={
            "score": 2,
            "status": "partially_verified",
            "answer_quality": "partial",
            "strengths": ["Relevant API example"],
            "missing_evidence": ["No deployment details."],
            "contradictions": [],
            "detected_competency": "FastAPI backend service",
            "evidence_found": ["Explained API routing and service separation"],
            "remaining_gap": "Deployment details are still unclear.",
            "ownership": "direct",
            "topic_decision": "continue",
            "reason_for_next_question": "Move on to an unassessed must-have skill.",
            "anti_repetition_check": "Docker has not been asked yet.",
            "ownership_check": "The next question does not assume Docker ownership.",
            "communication": {
                "clarity": 3,
                "specificity": 2,
                "relevance": 3,
                "structure": 2,
                "summary": "Relevant but incomplete.",
            },
        },
        evaluated_skill_ids=["fastapi"],
        follow_up_count=0,
    )
    gateway = FakeGateway(
        [
            planner,
            {
                "question": (
                    "Nếu container FastAPI chạy nhưng host không gọi được API, bạn sẽ "
                    "kiểm tra port mapping, bind address và log theo thứ tự nào?"
                )
            },
        ]
    )
    runtime = _runtime(
        interview_config=_runtime().interview_config.model_copy(
            update={"current_phase": "cv_verification"}
        ),
        history=[
            ConversationTurn(
                question="Bạn thiết kế API FastAPI như thế nào?",
                answer="Em tách router và service.",
                phase="cv_verification",
                topic_key="verify_fastapi",
            )
        ],
        question_count=1,
        current_topic="verify_fastapi",
        current_difficulty="easy",
        latest_answer="Em tách router và service.",
    )

    result = generate_next_turn(runtime, gateway=gateway)

    assert result.planner_output.question_plan.topic_key == "verify_docker"
    assert result.planner_output.follow_up_count == 0


def test_switching_topics_resets_model_follow_up_count():
    planner = _planner(
        action="ask_question",
        current_phase="cv_verification",
        question_plan={
            "question_type": "transition",
            "difficulty": "easy",
            "target_competency": "Docker deployment",
            "source_type": "jd_requirement",
            "source_reference": "Docker",
            "evidence_gap": "Docker has not been assessed.",
            "question_intent": "probe deployment reasoning",
            "topic_key": "verify_docker",
            "linked_skill_ids": ["docker"],
        },
        previous_answer_evaluation={
            "score": 3,
            "status": "verified",
            "answer_quality": "sufficient",
            "strengths": ["Specific FastAPI example"],
            "missing_evidence": [],
            "contradictions": [],
            "detected_competency": "FastAPI backend service",
            "evidence_found": ["Explained API routing and service separation"],
            "remaining_gap": "",
            "ownership": "direct",
            "topic_decision": "continue",
            "reason_for_next_question": "Move on to Docker.",
            "anti_repetition_check": "Docker has not been asked yet.",
            "ownership_check": "The next question does not assume Docker ownership.",
            "communication": {
                "clarity": 3,
                "specificity": 3,
                "relevance": 4,
                "structure": 3,
                "summary": "Clear technical answer.",
            },
        },
        evaluated_skill_ids=["fastapi"],
        follow_up_count=2,
    )
    gateway = FakeGateway(
        [
            planner,
            {
                "question": (
                    "Nếu container FastAPI chạy nhưng host không gọi được API, bạn sẽ "
                    "kiểm tra port mapping, bind address và log theo thứ tự nào?"
                )
            },
        ]
    )
    runtime = _runtime(
        interview_config=_runtime().interview_config.model_copy(
            update={"current_phase": "cv_verification"}
        ),
        history=[
            ConversationTurn(
                question="Bạn thiết kế API FastAPI như thế nào?",
                answer="Em tách router và service.",
                phase="cv_verification",
                topic_key="verify_fastapi",
            )
        ],
        question_count=1,
        current_topic="verify_fastapi",
        current_difficulty="easy",
        latest_answer="Em tách router và service.",
    )

    result = generate_next_turn(runtime, gateway=gateway)

    assert result.planner_output.follow_up_count == 0
    assert result.provider_metadata["planner"]["sanitized_fields"] == ["follow_up_count"]


def test_tech_lead_project_question_retries_until_exact_technology_is_named():
    planner = _planner(
        action="ask_initial_question",
        current_phase="cv_verification",
        question_plan={
            "question_type": "initial",
            "difficulty": "easy",
            "target_competency": "AI backend demo",
            "source_type": "cv_project",
            "source_reference": "AI backend demo",
            "evidence_gap": "Project stack ownership has not been assessed.",
            "question_intent": "verify project architecture",
            "topic_key": "cv_project_ai_backend_demo",
            "linked_skill_ids": [],
        },
    )
    gateway = FakeGateway(
        [
            planner,
            {
                "question": (
                    "Trong dự án AI backend, bạn thiết kế luồng xử lý từ request đến "
                    "model response như thế nào?"
                )
            },
            {
                "question": (
                    "Trong dự án AI backend dùng FastAPI, bạn thiết kế luồng xử lý từ "
                    "request đến model response như thế nào?"
                )
            },
        ]
    )
    runtime = _runtime(
        cv=_runtime().cv.model_copy(
            update={
                "projects": [
                    ProjectItem(
                        name="AI backend demo",
                        description="FastAPI service with an AI endpoint.",
                        technologies=["Python", "FastAPI", "Docker"],
                    )
                ]
            }
        ),
        interview_config=_runtime().interview_config.model_copy(
            update={"interview_mode": "tech_lead", "current_phase": "cv_verification"}
        ),
    )

    result = generate_next_turn(runtime, gateway=gateway)

    assert "FastAPI" in result.question
    assert result.provider_metadata["question_generator"]["attempts"] == 2


def test_python_skill_evidence_can_be_inferred_from_evaluated_ecosystem_answer():
    coverage_item = CoverageItem(
        skill_id="python",
        skill="Python",
        source="jd_requirement",
        priority="must_have",
        status="claimed",
    )
    runtime = _runtime(
        history=[
            ConversationTurn(
                question="Bạn xử lý timeout cho model call trong API như thế nào?",
                answer="Em dùng asyncio.wait_for quanh service call và log latency.",
                phase="problem_solving",
                topic_key="ai_timeout_flow",
            )
        ],
        evaluation_state=EvaluationState(
            topic_evidence={
                "ai_timeout_flow": TopicEvidenceState(
                    ownership="direct",
                    evidence_found=["Used asyncio timeout around model service call"],
                )
            }
        ),
    )

    assert _skill_has_interview_evidence(
        coverage_item,
        runtime,
        runtime.evaluation_state,
    )


def test_invalid_model_output_raises_interview_generation_error():
    gateway = FakeGateway(["not json"])

    with pytest.raises(InterviewTurnGenerationError, match="valid interview plan"):
        generate_next_turn(_runtime(), gateway=gateway)


def test_technical_check_invalid_planner_output_raises_interview_generation_error():
    gateway = FakeGateway(["not json"])
    runtime = _runtime(
        interview_config=_runtime().interview_config.model_copy(
            update={
                "interview_mode": "technical_check",
                "current_phase": "cv_verification",
                "allowed_next_phases": ["cv_verification", "problem_solving", "completed"],
            }
        )
    )

    with pytest.raises(InterviewTurnGenerationError, match="valid interview plan"):
        generate_next_turn(runtime, gateway=gateway)


def test_tech_lead_rejects_technical_query_task_intent():
    planner = _planner(
        action="ask_question",
        current_phase="cv_verification",
        question_plan={
            "question_type": "transition",
            "difficulty": "easy",
            "target_competency": "SQL proficiency and data manipulation",
            "source_type": "cv_skill",
            "source_reference": "Languages: Python, SQL",
            "evidence_gap": "SQL has not been assessed.",
            "question_intent": "technical_query_task",
            "topic_key": "sql_data_manipulation",
            "linked_skill_ids": ["sql"],
        },
        previous_answer_evaluation={
            "score": None,
            "status": "not_assessed",
            "answer_quality": "unable_to_answer",
            "strengths": [],
            "missing_evidence": ["No useful evidence."],
            "contradictions": [],
            "detected_competency": "Data pipeline design",
            "evidence_found": [],
            "remaining_gap": "No useful evidence for the previous topic.",
            "ownership": "unknown",
            "topic_decision": "stop",
            "reason_for_next_question": "Switch topics after no useful answer.",
            "anti_repetition_check": "SQL has not been asked yet.",
            "ownership_check": "The next question does not assume ownership.",
            "communication": {
                "clarity": 1,
                "specificity": 0,
                "relevance": 0,
                "structure": 0,
                "summary": "The candidate could not answer.",
            },
        },
        follow_up_count=0,
    )
    runtime = _runtime(
        interview_config=_runtime().interview_config.model_copy(
            update={
                "interview_mode": "tech_lead",
                "current_phase": "cv_verification",
                "allowed_next_phases": ["cv_verification", "problem_solving", "completed"],
            }
        ),
        history=[
            ConversationTurn(
                question="Em sẽ thiết kế pipeline Kafka và ClickHouse như thế nào?",
                answer="Tôi không biết.",
                phase="cv_verification",
                topic_key="jd_scenario_data_pipeline",
            )
        ],
        question_count=3,
        current_topic="jd_scenario_data_pipeline",
        current_difficulty="medium",
        latest_answer="Tôi không biết.",
    )

    with pytest.raises(InterviewTurnGenerationError, match="valid interview plan"):
        generate_next_turn(runtime, gateway=FakeGateway([planner]))


def test_tech_lead_sanitizes_internal_competency_label_in_plan():
    planner = _planner(
        current_phase="cv_verification",
        question_plan={
            "question_type": "initial",
            "difficulty": "easy",
            "target_competency": "technical problem solving",
            "source_type": "jd_requirement",
            "source_reference": "FastAPI backend service",
            "evidence_gap": "Backend debugging evidence has not been assessed.",
            "question_intent": "probe debugging approach",
            "topic_key": "verify_fastapi_debugging",
            "linked_skill_ids": ["fastapi"],
        },
    )
    gateway = FakeGateway(
        [
            planner,
            {
                "question": (
                    "Khi một API FastAPI trả 500 trong môi trường test, bạn sẽ kiểm tra "
                    "log, request và dependency theo thứ tự nào?"
                )
            },
        ]
    )

    result = generate_next_turn(
        _runtime(
            interview_config=_runtime().interview_config.model_copy(
                update={
                    "interview_mode": "tech_lead",
                    "current_phase": "cv_verification",
                }
            )
        ),
        gateway=gateway,
    )

    assert result.planner_output.question_plan.target_competency == "FastAPI backend service"
    assert result.provider_metadata["planner"]["sanitized_fields"] == [
        "question_plan.target_competency"
    ]
    assert "technical problem solving" not in result.question.lower()


def test_technical_check_rejects_behavioral_question_and_retries_task():
    planner = _planner(
        action="ask_initial_question",
        current_phase="cv_verification",
        question_plan={
            "question_type": "initial",
            "difficulty": "easy",
            "target_competency": "Docker",
            "source_type": "jd_requirement",
            "source_reference": "Docker",
            "evidence_gap": "Docker technical skill has not been checked.",
            "question_intent": "technical_debug_scenario",
            "topic_key": "verify_docker",
            "linked_skill_ids": ["docker"],
        },
    )
    gateway = FakeGateway(
        [
            planner,
            {
                "question": (
                    "Em có thể nêu một tình huống cụ thể em đã sử dụng Docker không?"
                )
            },
            {
                "question": (
                    "Với Docker, em viết Dockerfile tối thiểu cho app FastAPI chạy bằng Uvicorn ở port 8000 như thế nào?"
                )
            },
        ]
    )
    runtime = _runtime(
        interview_config=_runtime().interview_config.model_copy(
            update={
                "interview_mode": "technical_check",
                "current_phase": "cv_verification",
                "allowed_next_phases": ["cv_verification", "problem_solving", "completed"],
            }
        ),
        coverage_state=CoverageState(
            skills=[
                CoverageItem(
                    skill_id="docker",
                    skill="Docker",
                    source="jd_requirement",
                    priority="must_have",
                    status="not_assessed",
                )
            ]
        ),
    )

    result = generate_next_turn(runtime, gateway=gateway)

    assert "Dockerfile" in result.question
    assert "tình huống cụ thể" not in result.question
    assert result.provider_metadata["question_generator"]["attempts"] == 2


def test_technical_check_rejects_early_finish_without_required_evidence():
    gateway = FakeGateway([
        _planner(
            action="finish_interview",
            current_phase="completed",
            question_plan={
                "question_type": "closing",
                "difficulty": "easy",
                "target_competency": "interview completion",
                "source_type": "general",
                "source_reference": "",
                "evidence_gap": "",
                "question_intent": "finish_interview",
                "topic_key": "completed",
                "linked_skill_ids": [],
            },
            should_end_interview=True,
        )
    ])
    runtime = _runtime(
        interview_config=_runtime().interview_config.model_copy(
            update={
                "interview_mode": "technical_check",
                "current_phase": "problem_solving",
                "allowed_next_phases": ["cv_verification", "problem_solving", "completed"],
                "min_questions": 3,
                "max_questions": 10,
            }
        ),
        history=[
            ConversationTurn(question="Write a Python function.", answer="def f(): pass", phase="cv_verification", topic_key="verify_python"),
        ],
        question_count=1,
    )

    with pytest.raises(InterviewTurnGenerationError, match="valid interview plan"):
        generate_next_turn(runtime, gateway=gateway)


def test_early_finish_retries_planner_before_raising():
    previous_evaluation = {
        "score": 3,
        "status": "verified",
        "answer_quality": "sufficient",
        "strengths": ["Specific API evidence"],
        "missing_evidence": [],
        "contradictions": [],
        "detected_competency": "FastAPI backend service",
        "evidence_found": ["Explained API service separation and logging"],
        "remaining_gap": "",
        "ownership": "direct",
        "topic_decision": "continue",
        "reason_for_next_question": "Assess another must-have skill.",
        "anti_repetition_check": "Docker has not been asked yet.",
        "ownership_check": "The answer described direct API work.",
        "communication": {
            "clarity": 3,
            "specificity": 3,
            "relevance": 4,
            "structure": 3,
            "summary": "Clear technical answer.",
        },
    }
    early_finish = _planner(
        action="finish_interview",
        current_phase="completed",
        question_plan={
            "question_type": "closing",
            "difficulty": "easy",
            "target_competency": "interview completion",
            "source_type": "general",
            "source_reference": "",
            "evidence_gap": "",
            "question_intent": "finish_interview",
            "topic_key": "completed",
            "linked_skill_ids": [],
        },
        previous_answer_evaluation=previous_evaluation,
        evaluated_skill_ids=["python"],
        should_end_interview=True,
    )
    corrected_plan = _planner(
        action="ask_question",
        current_phase="cv_verification",
        question_plan={
            "question_type": "transition",
            "difficulty": "easy",
            "target_competency": "Docker deployment",
            "source_type": "jd_requirement",
            "source_reference": "Docker",
            "evidence_gap": "Docker has not been assessed.",
            "question_intent": "probe deployment reasoning",
            "topic_key": "verify_docker",
            "linked_skill_ids": ["docker"],
        },
        previous_answer_evaluation=previous_evaluation,
        evaluated_skill_ids=["python"],
        follow_up_count=0,
    )
    gateway = FakeGateway(
        [
            early_finish,
            corrected_plan,
            {
                "question": (
                    "Khi triển khai một service FastAPI bằng Docker, bạn sẽ kiểm tra "
                    "những điểm nào nếu container chạy nhưng API không truy cập được?"
                )
            },
        ]
    )
    runtime = _runtime(
        interview_config=_runtime().interview_config.model_copy(
            update={
                "interview_mode": "tech_lead",
                "current_phase": "cv_verification",
                "allowed_next_phases": ["cv_verification", "problem_solving", "completed"],
                "min_questions": 3,
                "max_questions": 6,
            }
        ),
        history=[
            ConversationTurn(
                question="Bạn thiết kế API service như thế nào?",
                answer="Em tách router và service, thêm log latency.",
                phase="cv_verification",
                topic_key="verify_python",
            )
        ],
        question_count=1,
        current_topic="verify_python",
        current_difficulty="easy",
        latest_answer="Em tách router và service, thêm log latency.",
    )

    result = generate_next_turn(runtime, gateway=gateway)

    assert result.planner_output.should_end_interview is False
    assert result.planner_output.question_plan.topic_key == "verify_docker"
    assert len(gateway.requests) == 3
    assert "finish before backend evidence" in gateway.requests[1].messages[1].content


def test_technical_check_can_finish_with_non_verify_topic_evidence():
    coverage = CoverageState(
        skills=[
            CoverageItem(
                skill_id="python",
                skill="Python",
                source="jd_requirement",
                priority="must_have",
                status="claimed",
            ),
            CoverageItem(
                skill_id="fastapi",
                skill="FastAPI",
                source="jd_requirement",
                priority="must_have",
                status="claimed",
            ),
            CoverageItem(
                skill_id="docker",
                skill="Docker",
                source="jd_requirement",
                priority="must_have",
                status="claimed",
            ),
        ]
    )
    runtime = _runtime(
        interview_config=_runtime().interview_config.model_copy(
            update={
                "interview_mode": "technical_check",
                "current_phase": "problem_solving",
                "min_questions": 3,
                "max_questions": 10,
            }
        ),
        history=[
            ConversationTurn(question="Write a FastAPI endpoint.", answer="Used Pydantic and Depends.", phase="cv_verification", topic_key="fastapi_implementation"),
            ConversationTurn(question="Write a Dockerfile.", answer="FROM python:3.12-slim", phase="cv_verification", topic_key="docker_implementation"),
            ConversationTurn(question="Write SQL GROUP BY.", answer="SELECT user_id, SUM(total) FROM orders GROUP BY user_id", phase="problem_solving", topic_key="sql_query_task"),
            ConversationTurn(question="Write Python list comprehension.", answer="[x*x for x in xs if x % 2 == 0]", phase="problem_solving", topic_key="verify_python"),
            ConversationTurn(question="Handle ZeroDivisionError.", answer="Use try-except ZeroDivisionError.", phase="problem_solving", topic_key="technical_problem_solving"),
        ],
        question_count=5,
    )
    evaluation = EvaluationState(
        topic_evidence={
            "fastapi_implementation": TopicEvidenceState(evidence_found=["Implemented FastAPI endpoint"]),
            "docker_implementation": TopicEvidenceState(evidence_found=["Wrote Dockerfile"]),
            "sql_query_task": TopicEvidenceState(evidence_found=["Wrote SQL query"]),
            "verify_python": TopicEvidenceState(evidence_found=["Used Python list comprehension"]),
            "technical_problem_solving": TopicEvidenceState(evidence_found=["Handled ZeroDivisionError"]),
        }
    )

    assert _has_enough_evidence_to_finish(runtime, coverage, evaluation) is True


def test_tech_lead_rejects_internal_communication_label_question():
    planner = _planner(
        action="clarify_answer",
        current_phase="problem_solving",
        question_plan={
            "question_type": "follow_up",
            "difficulty": "easy",
            "target_competency": "technical explanation",
            "source_type": "previous_answer",
            "source_reference": "API bị lỗi 500.",
            "evidence_gap": "Need concrete technical communication context.",
            "question_intent": "clarify_answer",
            "topic_key": "debug_communication",
            "linked_skill_ids": [],
        },
        previous_answer_evaluation={
            "score": 2,
            "status": "partially_verified",
            "answer_quality": "partial",
            "strengths": [],
            "missing_evidence": ["Specific bug report details"],
            "remaining_gap": "Specific bug report details are missing.",
            "ownership": "direct",
            "topic_decision": "clarify",
            "communication": {
                "clarity": 2,
                "specificity": 1,
                "relevance": 3,
                "structure": 2,
                "summary": "Partially clear.",
            },
        },
        follow_up_count=1,
    )
    gateway = FakeGateway(
        [
            planner,
            {
                "question": (
                    "Em có thể nêu một ví dụ cụ thể chứng minh khả năng clear and specific communication không?"
                )
            },
            {
                "question": (
                    "Nếu API trả 500, em sẽ mô tả endpoint, input, expected và actual cho teammate như thế nào?"
                )
            },
        ]
    )
    runtime = _runtime(
        interview_config=_runtime().interview_config.model_copy(
            update={"current_phase": "problem_solving"}
        ),
        history=[
            ConversationTurn(
                question="Em debug API 500 như thế nào?",
                answer="Em xem log.",
                phase="problem_solving",
                topic_key="debug_communication",
            )
        ],
        question_count=1,
        current_topic="debug_communication",
        latest_answer="Em xem log.",
    )

    result = generate_next_turn(runtime, gateway=gateway)

    assert "clear and specific communication" not in result.question
    assert "endpoint" in result.question
    assert result.provider_metadata["question_generator"]["attempts"] == 2


def test_repeated_question_is_rejected_and_regenerated():
    planner = _planner(
        action="clarify_answer",
        current_phase="career",
        question_plan={
            "question_type": "follow_up",
            "difficulty": "easy",
            "target_competency": "career motivation",
            "source_type": "previous_answer",
            "source_reference": "Em khá thích.",
            "evidence_gap": "The specific area of interest is missing.",
            "question_intent": "clarify_answer",
            "topic_key": "career_motivation",
            "linked_skill_ids": [],
        },
        previous_answer_evaluation={
            "score": 1,
            "status": "not_assessed",
            "answer_quality": "vague",
            "strengths": [],
            "missing_evidence": ["One specific area of interest"],
            "remaining_gap": "The specific area of interest is missing.",
            "ownership": "unknown",
            "topic_decision": "clarify",
            "communication": {
                "clarity": 1,
                "specificity": 0,
                "relevance": 2,
                "structure": 1,
                "summary": "Too vague.",
            },
        },
        follow_up_count=1,
    )
    repeated = "Điều gì khiến em muốn ứng tuyển vào vị trí này?"
    gateway = FakeGateway(
        [
            planner,
            {"question": repeated},
            {
                "question": (
                    "Trong vị trí này, em muốn tìm hiểu sâu nhất về xây dựng ứng dụng, "
                    "tối ưu chi phí hay vận hành LLM?"
                )
            },
        ]
    )
    runtime = _runtime(
        history=[
            ConversationTurn(
                question=repeated,
                answer="Em khá thích.",
                phase="career",
                topic_key="career_motivation",
            )
        ],
        question_count=1,
        current_topic="career_motivation",
        current_difficulty="easy",
        latest_answer="Em khá thích.",
    )

    result = generate_next_turn(runtime, gateway=gateway)

    assert result.question != repeated
    assert result.provider_metadata["question_generator"]["attempts"] == 2
    assert len(gateway.requests) == 3


def test_non_owned_unobserved_topic_rejects_same_topic_probe():
    planner = _planner(
        action="probe_deeper",
        current_phase="cv_verification",
        question_plan={
            "question_type": "follow_up",
            "difficulty": "medium",
            "target_competency": "Docker",
            "source_type": "previous_answer",
            "source_reference": "Team member handled it.",
            "evidence_gap": "Docker implementation evidence is missing.",
            "question_intent": "request_evidence",
            "topic_key": "verify_docker",
            "linked_skill_ids": ["docker"],
        },
        previous_answer_evaluation={
            "score": 0,
            "status": "not_assessed",
            "answer_quality": "unable_to_answer",
            "strengths": [],
            "missing_evidence": ["No direct or observed Docker evidence"],
            "remaining_gap": "No direct or observed Docker evidence.",
            "ownership": "not_owned",
            "topic_decision": "stop",
            "reason_for_next_question": "Stop Docker and assess another competency.",
            "ownership_check": "The candidate did not implement or observe Docker work.",
            "communication": {"clarity": 3, "specificity": 2, "relevance": 4, "structure": 3, "summary": "Clearly states no ownership."},
        },
        evaluated_skill_ids=[],
        follow_up_count=1,
    )
    gateway = FakeGateway([planner])
    runtime = _runtime(
        interview_config=_runtime().interview_config.model_copy(update={"current_phase": "cv_verification"}),
        history=[ConversationTurn(question="How did you use Docker?", answer="Team member handled it.", phase="cv_verification", topic_key="verify_docker")],
        question_count=1,
        current_topic="verify_docker",
        current_difficulty="easy",
        latest_answer="Team member handled it.",
    )

    with pytest.raises(InterviewTurnGenerationError, match="valid interview plan"):
        generate_next_turn(runtime, gateway=gateway)


def test_second_weak_answer_rejects_same_topic_follow_up():
    planner = _planner(
        action="clarify_answer",
        current_phase="cv_verification",
        question_plan={
            "question_type": "follow_up",
            "difficulty": "easy",
            "target_competency": "Python",
            "source_type": "previous_answer",
            "source_reference": "I did many things.",
            "evidence_gap": "Concrete evidence is missing.",
            "question_intent": "clarify_answer",
            "topic_key": "verify_python",
            "linked_skill_ids": ["python"],
        },
        previous_answer_evaluation={
            "score": 1,
            "status": "not_assessed",
            "answer_quality": "vague",
            "strengths": [],
            "missing_evidence": ["Concrete action missing"],
            "remaining_gap": "Concrete action missing.",
            "ownership": "unknown",
            "topic_decision": "clarify",
            "reason_for_next_question": "Clarify once more.",
            "communication": {"clarity": 1, "specificity": 0, "relevance": 2, "structure": 1, "summary": "Too vague."},
        },
        follow_up_count=1,
    )
    gateway = FakeGateway([planner])
    runtime = _runtime(
        history=[ConversationTurn(question="What did you build with Python?", answer="I did many things.", phase="cv_verification", topic_key="verify_python")],
        evaluation_state=EvaluationState(topic_evidence={"verify_python": TopicEvidenceState(consecutive_weak_answers=1)}),
        question_count=1,
        current_topic="verify_python",
        current_difficulty="easy",
        latest_answer="I did many things.",
    )

    with pytest.raises(InterviewTurnGenerationError, match="valid interview plan"):
        generate_next_turn(runtime, gateway=gateway)


def test_question_limit_finishes_without_calling_model():
    gateway = FakeGateway([])

    result = generate_next_turn(
        _runtime(question_count=4),
        gateway=gateway,
    )

    assert result.question == ""
    assert result.planner_output.action == "finish_interview"
    assert result.planner_output.previous_answer_evaluation is None
    assert result.planner_output.should_end_interview is True
    assert gateway.requests == []


def test_vague_answer_requires_follow_up_on_same_topic():
    planner = _planner(
        action="clarify_answer",
        current_phase="cv_verification",
        question_plan={
            "question_type": "follow_up",
            "difficulty": "easy",
            "target_competency": "project contribution",
            "source_type": "previous_answer",
            "source_reference": "Nhiều lắm.",
            "evidence_gap": "A concrete personal contribution is missing.",
            "question_intent": "clarify_answer",
            "topic_key": "project_contribution",
            "linked_skill_ids": [],
        },
        previous_answer_evaluation={
            "score": 1,
            "status": "not_assessed",
            "answer_quality": "vague",
            "strengths": [],
            "missing_evidence": ["One concrete personal contribution"],
            "contradictions": [],
            "communication": {
                "clarity": 1,
                "specificity": 0,
                "relevance": 2,
                "structure": 1,
                "summary": "Relevant but too vague to evaluate.",
            },
        },
        follow_up_count=1,
    )
    gateway = FakeGateway(
        [
            planner,
            {
                "question": (
                    "Em hãy chọn một phần cụ thể mà em trực tiếp thực hiện "
                    "và mô tả kết quả của phần đó?"
                )
            },
        ]
    )
    runtime = _runtime(
        interview_config=_runtime().interview_config.model_copy(
            update={"current_phase": "cv_verification"}
        ),
        history=[
            ConversationTurn(
                question="Em đã đóng góp gì trong đề tài?",
                answer="Nhiều lắm.",
                phase="cv_verification",
                topic_key="project_contribution",
            )
        ],
        question_count=1,
        current_topic="project_contribution",
        follow_up_count=0,
        latest_answer="Nhiều lắm.",
    )

    result = generate_next_turn(runtime, gateway=gateway)

    assert result.planner_output.action == "clarify_answer"
    assert result.planner_output.question_plan.topic_key == "project_contribution"
    assert result.planner_output.follow_up_count == 1
    assert len(result.evaluation_state.communication_samples) == 1


def test_interview_finishes_early_when_evidence_is_sufficient():
    communication = CommunicationEvaluation(
        clarity=3,
        specificity=3,
        relevance=3,
        structure=3,
        summary="Clear answer.",
    )
    planner = _planner(
        action="switch_topic",
        current_phase="behavioral",
        question_plan={
            "question_type": "transition",
            "difficulty": "easy",
            "target_competency": "teamwork",
            "source_type": "general",
            "source_reference": "",
            "evidence_gap": "No further gap.",
            "question_intent": "switch_topic",
            "topic_key": "teamwork",
            "linked_skill_ids": [],
        },
        previous_answer_evaluation={
            "score": 4,
            "status": "verified",
            "answer_quality": "sufficient",
            "strengths": ["Concrete implementation and result"],
            "missing_evidence": [],
            "contradictions": [],
            "communication": communication.model_dump(),
        },
        evaluated_skill_ids=["python", "fastapi"],
    )
    gateway = FakeGateway([planner])
    runtime = _runtime(
        interview_config=_runtime().interview_config.model_copy(
            update={
                "current_phase": "behavioral",
                "min_questions": 3,
                "max_questions": 8,
                "min_communication_samples": 4,
            }
        ),
        history=[
            ConversationTurn(
                question="Em dùng Python ở đâu?",
                answer="Em xây API.",
                phase="cv_verification",
                topic_key="verify_python",
            ),
            ConversationTurn(
                question="Em xử lý lỗi như thế nào?",
                answer="Em tái hiện và kiểm tra log.",
                phase="problem_solving",
                topic_key="problem_solving",
            ),
            ConversationTurn(
                question="Kết quả ra sao?",
                answer="Em giảm thời gian xử lý.",
                phase="behavioral",
                topic_key="impact",
            ),
            ConversationTurn(
                question="Em giải thích bug đó cho teammate như thế nào?",
                answer="Em nêu endpoint, input, expected và actual.",
                phase="problem_solving",
                topic_key="communication_debug",
            ),
            ConversationTurn(
                question="Giả sử team cần xây API gọi model AI, em thiết kế flow thế nào?",
                answer="Em tách router, service gọi model, timeout và lưu DB.",
                phase="problem_solving",
                topic_key="jd_scenario_ai_api_flow",
            ),
        ],
        coverage_state=CoverageState(
            skills=[
                CoverageItem(
                    skill_id="python",
                    skill="python",
                    source="jd_requirement",
                    priority="must_have",
                    status="partially_verified",
                    evidence_count=1,
                ),
                CoverageItem(
                    skill_id="fastapi",
                    skill="fastapi",
                    source="jd_requirement",
                    priority="must_have",
                    status="partially_verified",
                    evidence_count=1,
                ),
            ]
        ),
        evaluation_state=EvaluationState(
            communication_samples=[communication, communication, communication]
        ),
        question_count=5,
        current_topic="impact",
        latest_answer="Em giảm thời gian xử lý từ 10 phút xuống 2 phút.",
    )

    result = generate_next_turn(runtime, gateway=gateway)

    assert result.question == ""
    assert result.planner_output.should_end_interview is True
    assert result.planner_output.phase_completion_signal == "enough_evidence"
    assert len(gateway.requests) == 1


def test_tech_lead_rejects_finish_when_must_have_jd_skill_is_unassessed():
    gateway = FakeGateway([
        _planner(
            action="finish_interview",
            current_phase="completed",
            question_plan={
                "question_type": "closing",
                "difficulty": "easy",
                "target_competency": "interview completion",
                "source_type": "general",
                "source_reference": "",
                "evidence_gap": "",
                "question_intent": "finish_interview",
                "topic_key": "completed",
                "linked_skill_ids": [],
            },
            should_end_interview=True,
        )
    ])
    runtime = _runtime(question_count=1, history=[ConversationTurn(question="Why this role?", answer="Backend AI.", phase="career", topic_key="career_motivation")])

    with pytest.raises(InterviewTurnGenerationError, match="valid interview plan"):
        generate_next_turn(runtime, gateway=gateway)


def test_tech_lead_rejects_early_finish_before_jd_scenario():
    gateway = FakeGateway([
        _planner(
            action="finish_interview",
            current_phase="completed",
            question_plan={
                "question_type": "closing",
                "difficulty": "easy",
                "target_competency": "interview completion",
                "source_type": "general",
                "source_reference": "",
                "evidence_gap": "",
                "question_intent": "finish_interview",
                "topic_key": "completed",
                "linked_skill_ids": [],
            },
            should_end_interview=True,
        )
    ])
    runtime = _runtime(
        history=[ConversationTurn(question="What did you build?", answer="An API.", phase="cv_verification", topic_key="verify_python")],
        question_count=1,
    )

    with pytest.raises(InterviewTurnGenerationError, match="valid interview plan"):
        generate_next_turn(runtime, gateway=gateway)


def test_tech_lead_rejects_switch_when_incomplete_answer_needs_follow_up():
    planner = _planner(
        action="switch_topic",
        current_phase="problem_solving",
        question_plan={
            "question_type": "transition",
            "difficulty": "medium",
            "target_competency": "PostgreSQL debugging",
            "source_type": "jd_requirement",
            "source_reference": "PostgreSQL",
            "evidence_gap": "Database reasoning still needs evidence.",
            "question_intent": "request_evidence",
            "topic_key": "verify_postgresql",
            "linked_skill_ids": ["postgresql"],
        },
        previous_answer_evaluation={
            "score": 2,
            "status": "partially_verified",
            "answer_quality": "partial",
            "strengths": ["Mentioned DB logs."],
            "missing_evidence": ["Did not answer the SQL task."],
            "contradictions": [],
            "topic_decision": "clarify",
            "communication": CommunicationEvaluation(clarity=2, specificity=1, relevance=2, structure=2, summary="Avoided the direct SQL request.").model_dump(),
        },
        evaluated_skill_ids=["postgresql"],
    )
    gateway = FakeGateway([planner])
    runtime = _runtime(
        interview_config=_runtime().interview_config.model_copy(update={"current_phase": "problem_solving", "max_questions": 8}),
        history=[ConversationTurn(question="Explain this SQL task.", answer="I would check logs.", phase="problem_solving", topic_key="verify_postgresql")],
        question_count=1,
        current_topic="verify_postgresql",
        current_difficulty="medium",
        latest_answer="I would check logs.",
    )

    with pytest.raises(InterviewTurnGenerationError, match="valid interview plan"):
        generate_next_turn(runtime, gateway=gateway)


def test_final_report_uses_fixed_dimensions_and_backend_weighted_score():
    gateway = FakeGateway(
        [
            {
                "overall_summary": "Ứng viên thể hiện nền tảng tốt và cần đưa thêm số liệu.",
                "dimensions": [
                    {
                        "key": "technical_knowledge",
                        "score": 80,
                        "summary": "Giải thích đúng các khái niệm chính.",
                        "evidence": ["Mô tả được cách xây dựng API."],
                    },
                    {
                        "key": "practical_experience",
                        "score": 70,
                        "summary": "Có ví dụ thực tế nhưng kết quả chưa định lượng.",
                        "evidence": ["Nêu phần việc cá nhân trong đồ án."],
                    },
                    {
                        "key": "problem_solving",
                        "score": 60,
                        "summary": "Có quy trình xử lý cơ bản.",
                        "evidence": ["Tái hiện lỗi trước khi kiểm tra log."],
                    },
                    {
                        "key": "communication",
                        "score": 90,
                        "summary": "Trả lời rõ và đúng trọng tâm.",
                        "evidence": ["Bổ sung chi tiết tốt sau câu hỏi làm rõ."],
                    },
                    {
                        "key": "critical_thinking",
                        "score": 50,
                        "summary": "Chưa phân tích nhiều phương án đánh đổi.",
                        "evidence": [],
                    },
                ],
                "strengths": ["Trình bày rõ phần việc cá nhân."],
                "improvements": ["Nêu thêm số liệu kết quả."],
                "insufficient_evidence": ["Chưa đủ bằng chứng về phân tích đánh đổi."],
                "action_plan": ["Luyện trả lời theo tình huống, hành động và kết quả."],
                "confidence": "medium",
            }
        ]
    )
    context = _runtime(
        history=[
            ConversationTurn(
                question="Em đã làm phần nào trong đồ án?",
                answer="Em xây API và kiểm tra log khi có lỗi.",
                phase="cv_verification",
                topic_key="project_contribution",
            )
        ],
        question_count=1,
    )

    report, metadata = generate_interview_report(
        context,
        answer_evaluations=[],
        gateway=gateway,
    )

    assert report.overall_score == 73
    assert [dimension.weight for dimension in report.dimensions] == [30, 20, 20, 20, 10]
    assert all(dimension.key != "job_fit" for dimension in report.dimensions)
    assert metadata["provider"] == "fake"
    assert "engineering-lead interview" in gateway.requests[0].messages[0].content


def test_technical_check_report_uses_technical_labels_and_weights():
    gateway = FakeGateway(
        [
            {
                "overall_summary": "Ứng viên làm được bài kỹ thuật cơ bản và cần luyện edge cases.",
                "dimensions": [
                    {
                        "key": "technical_knowledge",
                        "score": 80,
                        "summary": "Nắm cú pháp và khái niệm chính.",
                        "evidence": ["Viết được hàm Python cơ bản."],
                    },
                    {
                        "key": "practical_experience",
                        "score": 70,
                        "summary": "Code/query phần chính đúng.",
                        "evidence": ["Trả về được kết quả mong muốn."],
                    },
                    {
                        "key": "problem_solving",
                        "score": 60,
                        "summary": "Có hướng debug nhưng chưa đầy đủ.",
                        "evidence": ["Kiểm tra input trước khi xử lý."],
                    },
                    {
                        "key": "communication",
                        "score": 90,
                        "summary": "Giải thích kỹ thuật ngắn gọn.",
                        "evidence": ["Nêu được lý do chọn cấu trúc dữ liệu."],
                    },
                    {
                        "key": "critical_thinking",
                        "score": 50,
                        "summary": "Chưa nêu đủ edge cases.",
                        "evidence": [],
                    },
                ],
                "strengths": ["Nắm bài kỹ thuật cơ bản."],
                "improvements": ["Bổ sung edge cases."],
                "insufficient_evidence": [],
                "action_plan": ["Luyện thêm bài query/code ngắn."],
                "confidence": "medium",
            }
        ]
    )
    context = _runtime(
        interview_config=_runtime().interview_config.model_copy(
            update={"interview_mode": "technical_check"}
        )
    )

    report, _ = generate_interview_report(
        context,
        answer_evaluations=[],
        gateway=gateway,
    )

    assert report.overall_score == 70
    assert [dimension.weight for dimension in report.dimensions] == [30, 25, 25, 10, 10]
    assert [dimension.label for dimension in report.dimensions] == [
        "Kiến thức chuyên môn",
        "Độ đúng code/query",
        "Debug và giải quyết vấn đề",
        "Giải thích kỹ thuật",
        "Edge cases và hiệu năng",
    ]
    assert "Assess technical performance only" in gateway.requests[0].messages[0].content


def test_tech_lead_rejects_direct_sql_task() -> None:
    context = _runtime()

    with pytest.raises(ValueError, match="requests code, query, command, or output"):
        _validate_candidate_question(
            (
                "Bạn hãy viết một câu lệnh SQL để lấy các customer_id có nhiều hơn "
                "5 đơn hàng."
            ),
            context,
        )


def test_tech_lead_allows_database_design_scenario() -> None:
    context = _runtime()

    _validate_candidate_question(
        (
            "Khi dữ liệu đơn hàng tăng lớn và báo cáo trở nên chậm, bạn sẽ kiểm tra "
            "và tối ưu thiết kế lưu trữ như thế nào?"
        ),
        context,
    )
