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
)
from app.ai.interview.service import generate_interview_report, generate_next_turn


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
        action="switch_topic",
        current_phase="cv_verification",
        question_plan={
            "question_type": "transition",
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
    assert "score" not in result.question.lower()
    assert "expected_signals" not in result.question.lower()


def test_invalid_model_output_uses_single_question_fallback():
    gateway = FakeGateway(["not json"])

    result = generate_next_turn(_runtime(), gateway=gateway)

    assert result.question == "Điều gì khiến em muốn ứng tuyển vào vị trí này?"
    assert result.provider_metadata["planner"]["fallback"] is True
    assert result.question.count("?") == 1


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
        ],
        coverage_state=CoverageState(
            skills=[
                CoverageItem(
                    skill_id="python",
                    skill="python",
                    source="jd_requirement",
                    priority="must_have",
                    status="partially_verified",
                ),
                CoverageItem(
                    skill_id="fastapi",
                    skill="fastapi",
                    source="jd_requirement",
                    priority="must_have",
                    status="partially_verified",
                ),
            ]
        ),
        evaluation_state=EvaluationState(
            communication_samples=[communication, communication, communication]
        ),
        question_count=3,
        current_topic="impact",
        latest_answer="Em giảm thời gian xử lý từ 10 phút xuống 2 phút.",
    )

    result = generate_next_turn(runtime, gateway=gateway)

    assert result.question == ""
    assert result.planner_output.should_end_interview is True
    assert result.planner_output.phase_completion_signal == "enough_evidence"
    assert len(gateway.requests) == 1


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
