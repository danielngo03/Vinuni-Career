from __future__ import annotations

from app.schemas.matching import (
    CompanyCandidateMatchRequest,
    MatchBreakdown,
    MatchListResponse,
    MatchResult,
    MatchingConfig,
    MatchingJobInput,
    MatchingMatrixRequest,
    MatchingStudentInput,
    SkillMatchBreakdown,
    StudentJobMatchRequest,
)


def match_student_to_jobs(payload: StudentJobMatchRequest) -> MatchListResponse:
    results = [
        score_match(payload.student, job, payload.config)
        for job in payload.jobs
    ]
    return MatchListResponse(
        audience="student",
        config=payload.config,
        results=sorted(results, key=lambda item: item.match_score, reverse=True),
    )


def match_candidates_to_job(payload: CompanyCandidateMatchRequest) -> MatchListResponse:
    results = [
        score_match(student, payload.job, payload.config)
        for student in payload.students
    ]
    return MatchListResponse(
        audience="company",
        config=payload.config,
        results=sorted(results, key=lambda item: item.match_score, reverse=True),
    )


def match_matrix(payload: MatchingMatrixRequest) -> MatchListResponse:
    results = [
        score_match(student, job, payload.config)
        for job in payload.jobs
        for student in payload.students
    ]
    return MatchListResponse(
        audience="matrix",
        config=payload.config,
        results=sorted(results, key=lambda item: item.match_score, reverse=True),
    )


def score_match(
    student: MatchingStudentInput,
    job: MatchingJobInput,
    config: MatchingConfig | None = None,
) -> MatchResult:
    config = config or MatchingConfig()
    skill_breakdown: list[SkillMatchBreakdown] = []
    required_scores: list[float] = []
    optional_scores: list[float] = []
    matched_required: list[str] = []
    weak_required: list[str] = []
    missing_required: list[str] = []
    matched_optional: list[str] = []
    missing_optional: list[str] = []
    strengths: list[str] = []
    gaps: list[str] = []
    risks: list[str] = []
    recommendations: list[str] = []
    explanations: list[str] = []
    penalties = 0.0
    evidence_bonus = 0.0
    rejected = False

    for raw_skill, requirement in job.skills.items():
        skill = _normalize_skill(raw_skill)
        student_skill = _find_student_skill(student, skill)
        reasons: list[str] = []
        status = "missing"
        student_score = None
        confidence = None
        evidence: list[str] = []

        if student_skill is None:
            skill_score = 0.0
            reasons.append(f"{skill} is missing from the student profile.")
            if requirement.required:
                missing_required.append(skill)
                gaps.append(skill)
                recommendations.append(f"Build or add evidence for required skill: {skill}.")
                if config.missing_required_policy == "reject":
                    rejected = True
                else:
                    penalties += config.missing_required_penalty
            else:
                missing_optional.append(skill)
        else:
            student_score = student_skill.score
            confidence = student_skill.confidence
            evidence = student_skill.evidence
            ratio = student_skill.score / max(requirement.required_level, 0.1)
            capped_ratio = min(ratio, config.cap_skill_ratio)
            skill_score = capped_ratio / config.cap_skill_ratio * 100
            skill_score *= requirement.importance
            skill_score *= _confidence_factor(student_skill.confidence, config.minimum_confidence)

            if student_skill.score >= requirement.required_level:
                status = "matched"
                strengths.append(skill)
                reasons.append(
                    f"{skill} score {student_skill.score:.1f} meets required level "
                    f"{requirement.required_level:.1f}."
                )
                if requirement.required:
                    matched_required.append(skill)
                else:
                    matched_optional.append(skill)
            else:
                status = "weak"
                gaps.append(skill)
                shortfall = requirement.required_level - student_skill.score
                reasons.append(f"{skill} is {shortfall:.1f} below the required level.")
                if requirement.required:
                    weak_required.append(skill)
                    penalties += config.under_level_penalty
                    recommendations.append(f"Improve {skill} before applying or shortlisting.")
                else:
                    missing_optional.append(skill)

            if student_skill.confidence < config.minimum_confidence:
                penalties += config.low_confidence_penalty
                risks.append(f"{skill} has low confidence evidence.")
                reasons.append(f"{skill} confidence is below {config.minimum_confidence:.2f}.")
            if student_skill.evidence:
                evidence_bonus += min(config.evidence_bonus, len(student_skill.evidence) * 1.5)

        weighted_score = _clamp(skill_score, 0, 100)
        if requirement.required:
            required_scores.append(weighted_score)
        else:
            optional_scores.append(weighted_score)

        skill_breakdown.append(
            SkillMatchBreakdown(
                skill=skill,
                required=requirement.required,
                required_level=requirement.required_level,
                student_score=student_score,
                confidence=confidence,
                importance=requirement.importance,
                score=round(weighted_score, 2),
                status=status,
                evidence=evidence,
                reasons=reasons,
            )
        )

    required_score = _weighted_average(required_scores)
    optional_score = _weighted_average(optional_scores)
    if not optional_scores:
        optional_score = 100.0

    raw_score = (
        required_score * config.required_skill_weight
        + optional_score * config.optional_skill_weight
        + min(evidence_bonus, 10.0)
        - penalties
    )
    final_score = 0.0 if rejected else _clamp(raw_score, 0, 100)

    if matched_required:
        explanations.append(f"Meets required skills: {', '.join(matched_required)}.")
    if weak_required:
        explanations.append(f"Weak required skills: {', '.join(weak_required)}.")
    if missing_required:
        explanations.append(f"Missing required skills: {', '.join(missing_required)}.")
    if matched_optional:
        explanations.append(f"Optional skills present: {', '.join(matched_optional)}.")
    if penalties:
        explanations.append(f"Penalties applied: {penalties:.1f} points.")

    return MatchResult(
        student_id=student.student_id,
        student_name=student.name,
        job_id=job.job_id,
        job_title=job.title,
        company_id=job.company_id,
        job_status=job.status,
        job_location=job.location,
        match_score=round(final_score, 2),
        label=_label(final_score, rejected),
        decision=_decision(final_score, rejected, config),
        breakdown=MatchBreakdown(
            required_skills=round(required_score * config.required_skill_weight, 2),
            optional_skills=round(optional_score * config.optional_skill_weight, 2),
            evidence_bonus=round(min(evidence_bonus, 10.0), 2),
            penalties=round(penalties, 2),
            raw_score=round(raw_score, 2),
        ),
        required_skills={
            "matched": matched_required,
            "weak": weak_required,
            "missing": missing_required,
        },
        optional_skills={
            "matched": matched_optional,
            "missing": missing_optional,
        },
        skill_breakdown=skill_breakdown,
        strengths=_unique(strengths),
        gaps=_unique(gaps),
        risks=_unique(risks),
        recommendations=_unique(recommendations),
        explanations=explanations,
    )


def _find_student_skill(student: MatchingStudentInput, skill: str):
    for raw_skill, detail in student.skills.items():
        if _normalize_skill(raw_skill) == skill:
            return detail
    return None


def _normalize_skill(value: str) -> str:
    return value.strip().lower().replace(" ", "_")


def _confidence_factor(confidence: float, minimum_confidence: float) -> float:
    if confidence >= minimum_confidence:
        return 1.0
    return max(0.5, confidence / max(minimum_confidence, 0.1))


def _weighted_average(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _clamp(value: float, floor: float, ceiling: float) -> float:
    return max(floor, min(ceiling, value))


def _label(score: float, rejected: bool) -> str:
    if rejected:
        return "Rejected"
    if score >= 85:
        return "Strong match"
    if score >= 70:
        return "Good match"
    if score >= 55:
        return "Partial match"
    return "Weak match"


def _decision(score: float, rejected: bool, config: MatchingConfig) -> str:
    if rejected:
        return "rejected"
    if score >= config.shortlist_threshold:
        return "shortlist"
    if score >= config.review_threshold:
        return "review"
    if score >= config.low_match_threshold:
        return "low_match"
    return "rejected"


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
