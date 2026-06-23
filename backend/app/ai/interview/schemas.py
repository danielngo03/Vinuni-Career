from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.ai.extraction.schemas import CVExtraction, JDExtraction

InterviewPhase = Literal[
    "career",
    "cv_verification",
    "problem_solving",
    "behavioral",
    "candidate_questions",
    "completed",
]
PlannerAction = Literal[
    "ask_question",
    "ask_initial_question",
    "probe_deeper",
    "request_example",
    "request_evidence",
    "clarify_answer",
    "challenge_assumption",
    "resolve_contradiction",
    "increase_difficulty",
    "decrease_difficulty",
    "switch_topic",
    "switch_phase",
    "finish_interview",
]
VerificationStatus = Literal[
    "claimed",
    "partially_verified",
    "verified",
    "contradicted",
    "not_assessed",
]
AnswerQuality = Literal["vague", "partial", "sufficient", "irrelevant", "unable_to_answer"]
AssessmentDimensionKey = Literal[
    "technical_knowledge",
    "practical_experience",
    "problem_solving",
    "communication",
    "critical_thinking",
]


class MatchingResult(BaseModel):
    matched_skills: list[str] = Field(default_factory=list, max_length=100)
    missing_skills: list[str] = Field(default_factory=list, max_length=100)
    score: float | None = Field(default=None, ge=0, le=100)


class InterviewConfig(BaseModel):
    language: str = Field(default="vi", min_length=2, max_length=20)
    candidate_level: Literal["student", "intern", "fresher", "junior"] = "student"
    target_role: str = Field(default="", max_length=200)
    current_phase: InterviewPhase = "career"
    allowed_next_phases: list[InterviewPhase] = Field(
        default_factory=lambda: [
            "cv_verification",
            "problem_solving",
            "behavioral",
            "candidate_questions",
            "completed",
        ],
        max_length=6,
    )
    min_questions: int = Field(default=8, ge=1, le=20)
    max_questions: int = Field(default=18, ge=1, le=40)
    max_follow_ups_per_topic: int = Field(default=3, ge=0, le=5)
    min_communication_samples: int = Field(default=4, ge=1, le=20)

    @model_validator(mode="after")
    def validate_question_limits(self) -> InterviewConfig:
        if self.min_questions > self.max_questions:
            raise ValueError("min_questions cannot exceed max_questions")
        return self


class CoverageItem(BaseModel):
    skill_id: str = Field(min_length=1, max_length=100)
    skill: str = Field(min_length=1, max_length=100)
    source: Literal["jd_requirement", "jd_nice_to_have", "cv_only"]
    priority: Literal["must_have", "nice_to_have", "cv_only"]
    status: VerificationStatus = "not_assessed"
    evidence_count: int = Field(default=0, ge=0)
    last_topic_key: str | None = Field(default=None, max_length=160)


class CoverageState(BaseModel):
    skills: list[CoverageItem] = Field(default_factory=list, max_length=200)
    verified_topics: list[str] = Field(default_factory=list, max_length=200)
    unassessed_topics: list[str] = Field(default_factory=list, max_length=200)


class CommunicationEvaluation(BaseModel):
    clarity: int = Field(ge=0, le=4)
    specificity: int = Field(ge=0, le=4)
    relevance: int = Field(ge=0, le=4)
    structure: int = Field(ge=0, le=4)
    summary: str = Field(default="", max_length=500)


class InterviewAssessmentDimension(BaseModel):
    key: AssessmentDimensionKey
    label: str = Field(min_length=1, max_length=100)
    score: int = Field(ge=0, le=100)
    weight: int = Field(ge=0, le=100)
    summary: str = Field(min_length=1, max_length=1000)
    evidence: list[str] = Field(default_factory=list, max_length=5)


class InterviewReport(BaseModel):
    overall_score: int = Field(ge=0, le=100)
    overall_summary: str = Field(min_length=1, max_length=1500)
    dimensions: list[InterviewAssessmentDimension] = Field(min_length=5, max_length=5)
    strengths: list[str] = Field(default_factory=list, max_length=5)
    improvements: list[str] = Field(default_factory=list, max_length=5)
    insufficient_evidence: list[str] = Field(default_factory=list, max_length=5)
    action_plan: list[str] = Field(default_factory=list, max_length=5)
    confidence: Literal["low", "medium", "high"]


class InterviewReportDraftDimension(BaseModel):
    key: AssessmentDimensionKey
    score: int = Field(ge=0, le=100)
    summary: str = Field(min_length=1, max_length=1000)
    evidence: list[str] = Field(default_factory=list, max_length=5)


class InterviewReportDraft(BaseModel):
    overall_summary: str = Field(min_length=1, max_length=1500)
    dimensions: list[InterviewReportDraftDimension] = Field(min_length=5, max_length=5)
    strengths: list[str] = Field(default_factory=list, max_length=5)
    improvements: list[str] = Field(default_factory=list, max_length=5)
    insufficient_evidence: list[str] = Field(default_factory=list, max_length=5)
    action_plan: list[str] = Field(default_factory=list, max_length=5)
    confidence: Literal["low", "medium", "high"]


class EvaluationState(BaseModel):
    competency_status: dict[str, VerificationStatus] = Field(default_factory=dict)
    contradictions: list[str] = Field(default_factory=list, max_length=100)
    communication_samples: list[CommunicationEvaluation] = Field(
        default_factory=list,
        max_length=40,
    )
    final_report: InterviewReport | None = None


class ConversationTurn(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    answer: str = Field(default="", max_length=10_000)
    phase: InterviewPhase
    topic_key: str = Field(default="", max_length=160)


class PreviousAnswerEvaluation(BaseModel):
    score: int | None = Field(default=None, ge=0, le=4)
    status: VerificationStatus = "not_assessed"
    answer_quality: AnswerQuality
    strengths: list[str] = Field(default_factory=list, max_length=20)
    missing_evidence: list[str] = Field(default_factory=list, max_length=20)
    contradictions: list[str] = Field(default_factory=list, max_length=20)
    communication: CommunicationEvaluation


class QuestionPlan(BaseModel):
    question_type: Literal["initial", "follow_up", "transition", "closing"]
    difficulty: Literal["easy", "medium", "hard"]
    target_competency: str = Field(min_length=1, max_length=200)
    source_type: Literal[
        "cv_skill",
        "cv_project",
        "cv_experience",
        "cv_education",
        "jd_requirement",
        "previous_answer",
        "general",
    ]
    source_reference: str = Field(default="", max_length=500)
    evidence_gap: str = Field(default="", max_length=1000)
    question_intent: str = Field(min_length=1, max_length=300)
    topic_key: str = Field(min_length=1, max_length=160)
    linked_skill_ids: list[str] = Field(default_factory=list, max_length=30)


class PlannerOutput(BaseModel):
    action: PlannerAction
    current_phase: InterviewPhase
    suggested_next_phase: InterviewPhase | None = None
    question_plan: QuestionPlan
    previous_answer_evaluation: PreviousAnswerEvaluation | None = None
    internal_reason: str = Field(default="", max_length=1000)
    expected_signals: list[str] = Field(default_factory=list, max_length=20)
    evaluated_skill_ids: list[str] = Field(default_factory=list, max_length=30)
    follow_up_count: int = Field(default=0, ge=0, le=5)
    phase_completion_signal: Literal[
        "enough_evidence",
        "max_follow_up_reached",
        "max_questions_reached",
        "weak_signal_need_switch",
    ] | None = None
    should_end_interview: bool = False


class QuestionGeneratorOutput(BaseModel):
    question: str = Field(min_length=1, max_length=500)


class InterviewStartRequest(BaseModel):
    cv: CVExtraction
    job_description: JDExtraction
    matching_result: MatchingResult | None = None
    interview_config: InterviewConfig = Field(default_factory=InterviewConfig)


class InterviewAnswerRequest(BaseModel):
    answer: str = Field(min_length=1, max_length=10_000)


class CandidateInterviewResponse(BaseModel):
    session_id: str
    question: str
    current_phase: InterviewPhase
    should_end_interview: bool
    report: InterviewReport | None = None


class InterviewRuntimeContext(BaseModel):
    cv: CVExtraction
    job_description: JDExtraction
    matching_result: MatchingResult
    interview_config: InterviewConfig
    history: list[ConversationTurn] = Field(default_factory=list, max_length=80)
    evaluation_state: EvaluationState = Field(default_factory=EvaluationState)
    coverage_state: CoverageState = Field(default_factory=CoverageState)
    question_count: int = Field(default=0, ge=0)
    current_topic: str | None = Field(default=None, max_length=160)
    follow_up_count: int = Field(default=0, ge=0, le=5)
    latest_answer: str | None = Field(default=None, max_length=10_000)

    @model_validator(mode="after")
    def validate_runtime_limits(self) -> InterviewRuntimeContext:
        if self.question_count > self.interview_config.max_questions:
            raise ValueError("question_count cannot exceed max_questions")
        if self.follow_up_count > self.interview_config.max_follow_ups_per_topic:
            raise ValueError("follow_up_count cannot exceed max_follow_ups_per_topic")
        return self


class InterviewTurnResult(BaseModel):
    question: str
    planner_output: PlannerOutput
    coverage_state: CoverageState
    evaluation_state: EvaluationState
    provider_metadata: dict[str, Any] = Field(default_factory=dict)
