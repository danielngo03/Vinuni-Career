from __future__ import annotations

import json

from app.ai.extraction.schemas import CVExtraction, JDExtraction, SkillEvidence
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
    _has_enough_evidence_to_finish,
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


def test_invalid_model_output_uses_single_question_fallback():
    gateway = FakeGateway(["not json"])

    result = generate_next_turn(_runtime(), gateway=gateway)

    assert result.question == (
        "Với vai trò Backend Intern, phần backend hoặc AI nào em muốn học sâu nhất khi tham gia team?"
    )
    assert result.provider_metadata["planner"]["fallback"] is True
    assert result.question.count("?") == 1


def test_technical_check_fallback_asks_code_question_instead_of_career():
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

    result = generate_next_turn(runtime, gateway=gateway)

    assert result.planner_output.current_phase == "cv_verification"
    assert result.planner_output.question_plan.topic_key == "verify_python"
    assert "Python" in result.question
    assert "ứng tuyển" not in result.question
    assert "muốn tìm hiểu" not in result.question


def test_technical_check_rejects_behavioral_question_and_falls_back_to_task():
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


def test_technical_check_overrides_early_finish_until_debug_or_edge_coverage():
    gateway = FakeGateway(
        [
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
            ),
            {"question": "If a FastAPI endpoint returns 500, what logs and request details would you inspect first?"},
        ]
    )
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
        coverage_state=CoverageState(
            skills=[
                CoverageItem(
                    skill_id="python",
                    skill="Python",
                    source="jd_requirement",
                    priority="must_have",
                    status="verified",
                    evidence_count=1,
                ),
                CoverageItem(
                    skill_id="fastapi",
                    skill="FastAPI",
                    source="jd_requirement",
                    priority="must_have",
                    status="verified",
                    evidence_count=1,
                ),
                CoverageItem(
                    skill_id="docker",
                    skill="Docker",
                    source="jd_requirement",
                    priority="must_have",
                    status="verified",
                    evidence_count=1,
                ),
            ]
        ),
        history=[
            ConversationTurn(question="Write a Python function.", answer="def f(): pass", phase="cv_verification", topic_key="verify_python"),
            ConversationTurn(question="Write a FastAPI endpoint.", answer="@app.post('/items')", phase="cv_verification", topic_key="verify_fastapi"),
            ConversationTurn(question="Write a Dockerfile.", answer="FROM python:3.12-slim", phase="problem_solving", topic_key="verify_docker"),
            ConversationTurn(question="Write a small API request body.", answer="{'email': 'a@b.com'}", phase="problem_solving", topic_key="verify_fastapi"),
            ConversationTurn(question="What status code should create return?", answer="201", phase="problem_solving", topic_key="verify_fastapi"),
        ],
        question_count=5,
    )

    result = generate_next_turn(runtime, gateway=gateway)

    assert result.question
    assert "500" in result.question
    assert result.planner_output.action != "finish_interview"


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


def test_non_owned_unobserved_topic_is_stopped_instead_of_probed_as_owner():
    planner = _planner(
        action="probe_deeper",
        current_phase="cv_verification",
        question_plan={
            "question_type": "follow_up",
            "difficulty": "medium",
            "target_competency": "Docker",
            "source_type": "previous_answer",
            "source_reference": "Thành viên khác làm và em không quan sát.",
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
            "communication": {
                "clarity": 3,
                "specificity": 2,
                "relevance": 4,
                "structure": 3,
                "summary": "Clearly states no ownership.",
            },
        },
        evaluated_skill_ids=[],
        follow_up_count=1,
    )
    gateway = FakeGateway(
        [
            planner,
            {"question": "Em có thể nêu một tình huống cụ thể em đã sử dụng Python không?"},
        ]
    )
    runtime = _runtime(
        interview_config=_runtime().interview_config.model_copy(
            update={"current_phase": "cv_verification"}
        ),
        history=[
            ConversationTurn(
                question="Em đã dùng Docker như thế nào trong dự án?",
                answer="Thành viên khác làm và em không quan sát.",
                phase="cv_verification",
                topic_key="verify_docker",
            )
        ],
        question_count=1,
        current_topic="verify_docker",
        current_difficulty="easy",
        latest_answer="Thành viên khác làm và em không quan sát.",
    )

    result = generate_next_turn(runtime, gateway=gateway)

    assert result.planner_output.question_plan.topic_key != "verify_docker"
    docker_state = result.evaluation_state.topic_evidence["verify_docker"]
    assert docker_state.ownership == "not_owned"
    assert docker_state.stop_reason
    assert "Docker" not in result.question


def test_second_weak_answer_forces_topic_switch():
    planner = _planner(
        action="clarify_answer",
        current_phase="cv_verification",
        question_plan={
            "question_type": "follow_up",
            "difficulty": "easy",
            "target_competency": "project contribution",
            "source_type": "previous_answer",
            "source_reference": "Em làm nhiều lắm.",
            "evidence_gap": "A concrete contribution is still missing.",
            "question_intent": "clarify_answer",
            "topic_key": "project_contribution",
            "linked_skill_ids": [],
        },
        previous_answer_evaluation={
            "score": 1,
            "status": "not_assessed",
            "answer_quality": "vague",
            "strengths": [],
            "missing_evidence": ["One concrete contribution"],
            "remaining_gap": "A concrete contribution is still missing.",
            "topic_decision": "clarify",
            "communication": {
                "clarity": 1,
                "specificity": 0,
                "relevance": 2,
                "structure": 1,
                "summary": "Still vague.",
            },
        },
        follow_up_count=2,
    )
    gateway = FakeGateway(
        [
            planner,
            {"question": "Em có thể nêu một tình huống cụ thể em đã sử dụng Python không?"},
        ]
    )
    runtime = _runtime(
        interview_config=_runtime().interview_config.model_copy(
            update={"current_phase": "cv_verification"}
        ),
        history=[
            ConversationTurn(
                question="Em đóng góp gì trong đề tài?",
                answer="Nhiều lắm.",
                phase="cv_verification",
                topic_key="project_contribution",
            ),
            ConversationTurn(
                question="Em hãy chọn một phần cụ thể em trực tiếp làm?",
                answer="Em làm nhiều lắm.",
                phase="cv_verification",
                topic_key="project_contribution",
            ),
        ],
        evaluation_state=EvaluationState(
            topic_evidence={
                "project_contribution": TopicEvidenceState(
                    consecutive_weak_answers=1
                )
            }
        ),
        question_count=2,
        current_topic="project_contribution",
        current_difficulty="easy",
        follow_up_count=1,
        latest_answer="Em làm nhiều lắm.",
    )

    result = generate_next_turn(runtime, gateway=gateway)

    assert result.planner_output.question_plan.topic_key != "project_contribution"
    assert (
        result.evaluation_state.topic_evidence[
            "project_contribution"
        ].consecutive_weak_answers
        == 2
    )


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


def test_tech_lead_does_not_finish_when_must_have_jd_skill_is_unassessed():
    communication = CommunicationEvaluation(
        clarity=3,
        specificity=3,
        relevance=3,
        structure=3,
        summary="Clear technical answer.",
    )
    planner = _planner(
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
        previous_answer_evaluation={
            "score": 4,
            "status": "verified",
            "answer_quality": "sufficient",
            "strengths": ["Explained FastAPI endpoint design."],
            "missing_evidence": [],
            "contradictions": [],
            "communication": communication.model_dump(),
        },
        evaluated_skill_ids=["fastapi"],
        should_end_interview=True,
    )
    gateway = FakeGateway(
        [
            planner,
            {
                "question": (
                    "JD có yêu cầu Docker nhưng CV chưa có bằng chứng rõ. "
                    "Em từng containerize app backend chưa, và nếu có thì em tự làm phần nào?"
                )
            },
        ]
    )
    runtime = _runtime(
        interview_config=_runtime().interview_config.model_copy(
            update={"current_phase": "problem_solving", "max_questions": 8}
        ),
        history=[
            ConversationTurn(
                question="Em dùng Python ở đâu?",
                answer="Em xây API.",
                phase="cv_verification",
                topic_key="verify_python",
            ),
            ConversationTurn(
                question="Em thiết kế FastAPI endpoint thế nào?",
                answer="Em dùng Pydantic và service layer.",
                phase="problem_solving",
                topic_key="verify_fastapi",
            ),
            ConversationTurn(
                question="Giả sử app FastAPI lỗi 500 thì em debug thế nào?",
                answer="Em xem log, request body và stack trace.",
                phase="problem_solving",
                topic_key="jd_scenario_debug_backend_apis",
            ),
        ],
        coverage_state=CoverageState(
            skills=[
                CoverageItem(
                    skill_id="python",
                    skill="python",
                    source="jd_requirement",
                    priority="must_have",
                    status="verified",
                    evidence_count=1,
                ),
                CoverageItem(
                    skill_id="fastapi",
                    skill="fastapi",
                    source="jd_requirement",
                    priority="must_have",
                    status="verified",
                    evidence_count=1,
                ),
                CoverageItem(
                    skill_id="docker",
                    skill="docker",
                    source="jd_requirement",
                    priority="must_have",
                    status="not_assessed",
                    evidence_count=0,
                ),
            ]
        ),
        evaluation_state=EvaluationState(
            communication_samples=[communication, communication]
        ),
        question_count=3,
        current_topic="verify_fastapi",
        current_difficulty="medium",
        latest_answer="Em dùng Pydantic và tách service để dễ test.",
    )

    result = generate_next_turn(runtime, gateway=gateway)

    assert result.question
    assert result.planner_output.should_end_interview is False
    assert result.planner_output.question_plan.topic_key == "verify_docker"
    assert "Docker" in result.question


def test_tech_lead_requires_jd_scenario_before_early_finish():
    communication = CommunicationEvaluation(
        clarity=3,
        specificity=3,
        relevance=3,
        structure=3,
        summary="Clear technical answer.",
    )
    planner = _planner(
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
        previous_answer_evaluation={
            "score": 4,
            "status": "verified",
            "answer_quality": "sufficient",
            "strengths": ["Explained Docker debugging."],
            "missing_evidence": [],
            "contradictions": [],
            "communication": communication.model_dump(),
        },
        evaluated_skill_ids=["docker"],
        should_end_interview=True,
    )
    gateway = FakeGateway(
        [
            planner,
            {
                "question": (
                    "Giả sử team cần xây API nhận text, gọi model AI và lưu kết quả. "
                    "Em sẽ thiết kế flow backend và xử lý lỗi chính như thế nào?"
                )
            },
        ]
    )
    runtime = _runtime(
        interview_config=_runtime().interview_config.model_copy(
            update={"current_phase": "problem_solving", "max_questions": 8}
        ),
        job_description=_runtime().job_description.model_copy(
            update={"responsibilities": ["Build backend APIs that integrate AI model calls."]}
        ),
        history=[
            ConversationTurn(
                question="Em dùng Python ở đâu?",
                answer="Em xây API.",
                phase="cv_verification",
                topic_key="verify_python",
            ),
            ConversationTurn(
                question="Em thiết kế FastAPI endpoint thế nào?",
                answer="Em dùng Pydantic và service layer.",
                phase="problem_solving",
                topic_key="verify_fastapi",
            ),
            ConversationTurn(
                question="Em dùng Docker như thế nào?",
                answer="Em viết Dockerfile và map port.",
                phase="problem_solving",
                topic_key="verify_docker",
            ),
        ],
        coverage_state=CoverageState(
            skills=[
                CoverageItem(
                    skill_id="python",
                    skill="python",
                    source="jd_requirement",
                    priority="must_have",
                    status="verified",
                    evidence_count=1,
                ),
                CoverageItem(
                    skill_id="fastapi",
                    skill="fastapi",
                    source="jd_requirement",
                    priority="must_have",
                    status="verified",
                    evidence_count=1,
                ),
                CoverageItem(
                    skill_id="docker",
                    skill="docker",
                    source="jd_requirement",
                    priority="must_have",
                    status="verified",
                    evidence_count=1,
                ),
            ]
        ),
        evaluation_state=EvaluationState(
            communication_samples=[communication, communication]
        ),
        question_count=3,
        current_topic="verify_docker",
        current_difficulty="medium",
        latest_answer="Em viết Dockerfile và debug bằng docker logs.",
    )

    result = generate_next_turn(runtime, gateway=gateway)

    assert result.question
    assert result.planner_output.should_end_interview is False
    assert result.planner_output.question_plan.topic_key.startswith("jd_scenario_")


def test_tech_lead_does_not_repeat_direct_coding_task():
    communication = CommunicationEvaluation(
        clarity=2,
        specificity=1,
        relevance=2,
        structure=2,
        summary="Avoided the direct SQL request.",
    )
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
            "communication": communication.model_dump(),
        },
        evaluated_skill_ids=["postgresql"],
    )
    gateway = FakeGateway(
        [
            planner,
            {"question": "Bạn hãy viết câu lệnh SQL lấy các order có amount lớn hơn 1000000."},
            {
                "question": (
                    "Trong một lỗi database timeout ở FastAPI, em sẽ kiểm tra connection pool, "
                    "query chậm và log PostgreSQL theo thứ tự nào?"
                )
            },
        ]
    )
    runtime = _runtime(
        interview_config=_runtime().interview_config.model_copy(
            update={"current_phase": "problem_solving", "max_questions": 8}
        ),
        history=[
            ConversationTurn(
                question="Bạn hãy viết câu lệnh SQL tính tổng amount theo user_id.",
                answer="Em sẽ xem log và sửa dần.",
                phase="problem_solving",
                topic_key="verify_postgresql",
            )
        ],
        coverage_state=CoverageState(
            skills=[
                CoverageItem(
                    skill_id="postgresql",
                    skill="PostgreSQL",
                    source="jd_requirement",
                    priority="must_have",
                    status="partially_verified",
                    evidence_count=1,
                )
            ]
        ),
        question_count=1,
        current_topic="verify_postgresql",
        current_difficulty="medium",
        latest_answer="Em sẽ xem log và sửa dần.",
    )

    result = generate_next_turn(runtime, gateway=gateway)

    assert "viết câu lệnh SQL" not in result.question
    assert "connection pool" in result.question
    assert result.provider_metadata["question_generator"]["attempts"] == 2


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
