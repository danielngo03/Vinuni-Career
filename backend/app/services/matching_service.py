from __future__ import annotations

import re

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


SKILL_ALIASES = {
    "js": "javascript",
    "react.js": "react",
    "reactjs": "react",
    "ts": "typescript",
    "postgres": "postgresql",
    "postgre": "postgresql",
    "ms excel": "excel",
    "microsoft excel": "excel",
}

FIELD_ALIASES = {
    "computer science": {"computer science", "software engineering", "information technology"},
    "software engineering": {"computer science", "software engineering", "information technology"},
    "information technology": {"computer science", "software engineering", "information technology"},
    "business administration": {"business", "business administration", "management"},
    "business": {"business", "business administration", "management"},
    "marketing": {"marketing", "digital marketing"},
}


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

    skill_score = (
        required_score * config.required_skill_weight
        + optional_score * config.optional_skill_weight
    )
    experience_score, experience_active, experience_reasons = _score_experience(student, job)
    education_score, education_active, education_reasons = _score_education(student, job)
    component_weights = _component_weights(config, experience_active, education_active)

    raw_score = (
        skill_score * component_weights.get("skill", 0.0)
        + experience_score * component_weights.get("experience", 0.0)
        + education_score * component_weights.get("education", 0.0)
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
    explanations.extend(experience_reasons)
    explanations.extend(education_reasons)
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
            skill_score=round(skill_score, 2),
            experience_score=round(experience_score, 2),
            education_score=round(education_score, 2),
            component_weights=component_weights,
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
    normalized = re.sub(r"\s+", " ", value.strip().lower())
    canonical = SKILL_ALIASES.get(normalized, normalized)
    return canonical.replace(" ", "_")


def _score_experience(
    student: MatchingStudentInput,
    job: MatchingJobInput,
) -> tuple[float, bool, list[str]]:
    requirement = job.experience_requirements
    active = bool(
        requirement.required
        or requirement.min_months
        or requirement.preferred_titles
        or requirement.keywords
        or requirement.importance
    )
    if not active:
        return 0.0, False, []
    if not student.work_experience:
        return 0.0, True, ["No work experience evidence found for this requirement."]

    best_score = 0.0
    best_evidence = ""
    title_terms = [_normalize_text(value) for value in requirement.preferred_titles]
    keyword_terms = [_normalize_text(value) for value in requirement.keywords]

    for item in student.work_experience:
        item_text = _normalize_text(" ".join([item.title, item.company, item.duration, item.summary]))
        title_text = _normalize_text(item.title)
        components = [(item.score / 10 * 100, 0.15)]
        if title_terms:
            components.append((_term_match_score(title_text, title_terms), 0.35))
        if keyword_terms:
            components.append((_term_match_score(item_text, keyword_terms), 0.30))
        if requirement.min_months:
            components.append((_duration_score(item.duration, requirement.min_months), 0.20))
        item_score = _weighted_components(components)
        if item_score > best_score:
            best_score = item_score
            best_evidence = item.title or item.summary or item.company

    weighted = best_score * max(requirement.importance, 0.5)
    if best_score >= 70:
        return _clamp(weighted, 0, 100), True, [f"Experience requirement matched: {best_evidence}."]
    if requirement.required:
        return _clamp(weighted, 0, 100), True, ["Required experience is weak or missing."]
    return _clamp(weighted, 0, 100), True, ["Preferred experience is only partially covered."]


def _score_education(
    student: MatchingStudentInput,
    job: MatchingJobInput,
) -> tuple[float, bool, list[str]]:
    requirement = job.education_requirements
    active = bool(
        requirement.required
        or requirement.degrees
        or requirement.fields_of_study
        or requirement.certifications
        or requirement.keywords
        or requirement.importance
    )
    if not active:
        return 0.0, False, []
    if not student.education:
        return 0.0, True, ["No education evidence found for this requirement."]

    degree_terms = [_normalize_text(value) for value in requirement.degrees]
    field_terms = [_normalize_text(value) for value in requirement.fields_of_study]
    cert_terms = [_normalize_text(value) for value in requirement.certifications]
    keyword_terms = [_normalize_text(value) for value in requirement.keywords]
    best_score = 0.0
    best_evidence = ""

    for item in student.education:
        item_text = _normalize_text(" ".join([item.degree, item.institution, item.year, item.summary]))
        components = [(item.score / 10 * 100, 0.15)]
        if degree_terms:
            components.append((_term_match_score(item_text, degree_terms), 0.30))
        if field_terms:
            components.append((_field_match_score(item_text, field_terms), 0.35))
        if cert_terms:
            components.append((_term_match_score(item_text, cert_terms), 0.20))
        if keyword_terms:
            components.append((_term_match_score(item_text, keyword_terms), 0.20))
        item_score = _weighted_components(components)
        if item_score > best_score:
            best_score = item_score
            best_evidence = item.degree or item.summary or item.institution

    weighted = best_score * max(requirement.importance, 0.5)
    if best_score >= 70:
        return _clamp(weighted, 0, 100), True, [f"Education requirement matched: {best_evidence}."]
    if requirement.required:
        return _clamp(weighted, 0, 100), True, ["Required education is weak or missing."]
    return _clamp(weighted, 0, 100), True, ["Preferred education is only partially covered."]


def _component_weights(
    config: MatchingConfig,
    experience_active: bool,
    education_active: bool,
) -> dict[str, float]:
    weights = {
        "skill": config.skill_weight,
        "experience": config.experience_weight if experience_active else 0.0,
        "education": config.education_weight if education_active else 0.0,
    }
    total = sum(value for value in weights.values() if value > 0)
    if total <= 0:
        return {"skill": 1.0, "experience": 0.0, "education": 0.0}
    return {
        key: round(value / total, 4) if value > 0 else 0.0
        for key, value in weights.items()
    }


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _term_match_score(text: str, terms: list[str]) -> float:
    if not terms:
        return 0.0
    matched = sum(1 for term in terms if term and term in text)
    return matched / len(terms) * 100


def _field_match_score(text: str, fields: list[str]) -> float:
    if not fields:
        return 0.0
    matched = 0
    for field in fields:
        equivalents = FIELD_ALIASES.get(field, {field})
        if any(equivalent in text for equivalent in equivalents):
            matched += 1
    return matched / len(fields) * 100


def _duration_score(duration: str, min_months: int) -> float:
    if min_months <= 0:
        return 0.0
    months = _months_from_text(duration)
    if months <= 0:
        return 0.0
    return _clamp(months / min_months * 100, 0, 100)


def _months_from_text(text: str) -> int:
    match = re.search(r"(\d+)\s*\+?\s*(month|months|year|years|yr|yrs)\b", text, flags=re.IGNORECASE)
    if not match:
        return 0
    amount = int(match.group(1))
    unit = match.group(2).lower()
    return amount * 12 if unit.startswith(("year", "yr")) else amount


def _weighted_components(components: list[tuple[float, float]]) -> float:
    total_weight = sum(weight for _, weight in components if weight > 0)
    if total_weight <= 0:
        return 0.0
    return sum(score * weight for score, weight in components) / total_weight


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
