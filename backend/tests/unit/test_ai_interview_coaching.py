from __future__ import annotations

import json

from app.ai.extraction.schemas import CVExtraction, JDExtraction, SkillEvidence
from app.ai.gateway.schemas import ChatResponse
from app.ai.interview.schemas import (
    AnswerFeedback,
    CommunicationEvaluation,
    InterviewConfig,
    InterviewRuntimeContext,
    MatchingResult,
    PreviousAnswerEvaluation,
)
from app.ai.interview.service import generate_answer_coaching
from app.modules.ai_operations.api.interview_agent import _public_feedback


class FakeCoachingGateway:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.requests = []

    def chat(self, request):
        self.requests.append(request)
        return ChatResponse(
            content=json.dumps(self.payload, ensure_ascii=False),
            provider="fake",
            model="fake-model",
            input_tokens=10,
            output_tokens=10,
        )


def _runtime() -> InterviewRuntimeContext:
    return InterviewRuntimeContext(
        cv=CVExtraction(
            summary="Sinh viên Backend AI",
            skills=[SkillEvidence(name="Python", evidence="Đã xây dựng API")],
        ),
        job_description=JDExtraction(
            title="Backend AI Engineer Intern",
            required_skills=[SkillEvidence(name="Python")],
            seniority="intern",
        ),
        matching_result=MatchingResult(
            matched_skills=["python"],
            score=80,
        ),
        interview_config=InterviewConfig(
            language="vi",
            candidate_level="student",
            target_role="Backend AI Engineer Intern",
        ),
    )


def _evaluation(**updates) -> PreviousAnswerEvaluation:
    evaluation = PreviousAnswerEvaluation(
        score=3,
        status="partially_verified",
        answer_quality="partial",
        strengths=["The candidate connected AI experience to the backend role."],
        missing_evidence=[
            "Explain API packaging, concurrency, and latency handling."
        ],
        remaining_gap="Understanding of backend service concurrency",
        ownership="direct",
        topic_decision="continue",
        communication=CommunicationEvaluation(
            clarity=4,
            specificity=3,
            relevance=4,
            structure=3,
            summary="The candidate gave a clear and relevant answer.",
        ),
    )
    return evaluation.model_copy(update=updates)


def test_coaching_agent_is_a_separate_model_call_with_phase_context() -> None:
    gateway = FakeCoachingGateway(
        {
            "summary": "Câu trả lời nêu rõ định hướng phù hợp với vị trí.",
            "tags": ["Đúng trọng tâm"],
            "strengths": ["Kết nối được nền tảng hiện có với mục tiêu nghề nghiệp."],
            "improvements": [
                "Nêu cụ thể hơn điều bạn muốn học hỏi trong kỳ thực tập."
            ],
        }
    )

    feedback, metadata = generate_answer_coaching(
        _runtime(),
        question="Vì sao bạn quan tâm đến vị trí Backend AI Engineer Intern?",
        answer="Em muốn phát triển ở giao điểm giữa AI và backend.",
        phase="career",
        question_intent="Đánh giá động lực và định hướng nghề nghiệp.",
        topic_key="career_motivation",
        evaluation=_evaluation(),
        gateway=gateway,
    )

    assert feedback.summary.startswith("Câu trả lời")
    assert metadata["provider"] == "fake"
    assert len(gateway.requests) == 1
    request = gateway.requests[0]
    assert request.metadata["feature"] == "interview_answer_coach"
    payload = json.loads(request.messages[1].content)
    assert payload["phase"] == "career"
    assert payload["question_intent"].startswith("Đánh giá động lực")
    assert payload["question"].startswith("Vì sao")


def test_career_feedback_filters_technical_and_ownership_suggestions() -> None:
    coaching = AnswerFeedback(
        summary="Câu trả lời thể hiện định hướng phù hợp với vị trí.",
        tags=["Đúng trọng tâm", "Thể hiện rõ vai trò"],
        strengths=["Nêu được mục tiêu phát triển ở giao điểm giữa AI và backend."],
        improvements=[
            "Làm rõ cách đóng gói pipeline thành API/service và xử lý nhiều request.",
            "Li\u00ean h\u1ec7 r\u00f5 h\u01a1n m\u1ee5c ti\u00eau ngh\u1ec1 nghi\u1ec7p v\u1edbi v\u1ecb tr\u00ed \u0111ang \u1ee9ng tuy\u1ec3n."
        ],
    )

    feedback = _public_feedback(
        _evaluation(),
        phase="career",
        question="Vì sao bạn quan tâm đến vị trí này?",
        question_intent="Đánh giá động lực và mục tiêu nghề nghiệp.",
        coaching=coaching,
    )

    combined = " ".join(
        [feedback.summary, *feedback.tags, *feedback.strengths, *feedback.improvements]
    ).lower()
    assert "xử lý nhiều request" not in combined
    assert "thể hiện rõ vai trò" not in combined
    assert any(
        "nghề nghiệp" in item or "vị trí" in item for item in feedback.improvements
    )


def test_technical_feedback_keeps_relevant_metric_suggestion() -> None:
    coaching = AnswerFeedback(
        summary="Câu trả lời mô tả đúng hướng tối ưu pipeline inference.",
        tags=["Đúng trọng tâm"],
        strengths=["Đề cập đến FP16 và xử lý bất đồng bộ."],
        improvements=["Bổ sung metric trước và sau tối ưu như FPS hoặc latency."],
    )

    feedback = _public_feedback(
        _evaluation(),
        phase="problem_solving",
        question="Bạn tối ưu độ trễ của pipeline inference như thế nào?",
        question_intent="Đánh giá cách cân bằng latency và độ chính xác.",
        coaching=coaching,
    )

    assert any("FPS" in item or "latency" in item for item in feedback.improvements)


def test_no_generic_gap_tag_when_model_gap_is_english() -> None:
    feedback = _public_feedback(
        _evaluation(),
        phase="career",
        question="Mục tiêu nghề nghiệp của bạn là gì?",
        question_intent="Đánh giá định hướng nghề nghiệp.",
        coaching=AnswerFeedback(
            summary="Câu trả lời thể hiện định hướng phù hợp.",
            strengths=["Nêu được mục tiêu phát triển dài hạn."],
            improvements=["Liên hệ rõ hơn mục tiêu với vị trí đang ứng tuyển."],
        ),
    )

    assert all("Một số chi tiết" not in tag for tag in feedback.tags)
    assert all("Understanding of" not in tag for tag in feedback.tags)
