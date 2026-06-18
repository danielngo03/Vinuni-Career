from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.ai.extraction.schemas import CVExtraction, SkillEvidence
from app.ai.matching import normalize_skills
from app.ai.safety import mask_pii

SKILL_PATTERNS = [
    "python",
    "fastapi",
    "django",
    "sql",
    "postgresql",
    "postgres",
    "mysql",
    "redis",
    "kafka",
    "docker",
    "kubernetes",
    "k8s",
    "react",
    "reactjs",
    "typescript",
    "javascript",
    "node.js",
    "nodejs",
    "node",
    "java",
    "go",
    "machine learning",
    "nlp",
    "rag",
    "llm",
    "pytorch",
    "tensorflow",
    "data analysis",
    "elasticsearch",
    "qdrant",
    "milvus",
]


@dataclass(frozen=True)
class CVPipelineResult:
    parsed_data: dict
    masked_data: dict
    normalized_skills: list[str]
    quality_flags: list[str] = field(default_factory=list)
    trace: list[dict[str, str]] = field(default_factory=list)


def run_cv_pipeline(raw_text: str, *, source_quality: str = "native_text") -> CVPipelineResult:
    trace: list[dict[str, str]] = []
    document_type = _router_node(raw_text)
    trace.append({"node": "router", "result": document_type})
    if document_type != "cv":
        return CVPipelineResult(
            parsed_data={"raw_text": raw_text, "document_type": document_type},
            masked_data={},
            normalized_skills=[],
            quality_flags=["document_is_not_cv"],
            trace=trace,
        )

    extraction = _extractor_node(raw_text, source_quality=source_quality)
    trace.append({"node": "extractor", "result": f"{len(extraction.skills)} skills"})
    normalized = normalize_skills([skill.name for skill in extraction.skills])
    flags = _critic_node(raw_text, normalized)
    trace.append({"node": "critic", "result": ",".join(flags) or "passed"})
    masked_text, entities = mask_pii(raw_text)
    trace.append({"node": "action", "result": "masked_and_ready"})

    payload = extraction.model_dump()
    payload.update(
        {
            "raw_text": raw_text,
            "normalized_skills": normalized,
            "pipeline_trace": trace,
        }
    )
    return CVPipelineResult(
        parsed_data=payload,
        masked_data={"text": masked_text, "entities": entities, "normalized_skills": normalized},
        normalized_skills=normalized,
        quality_flags=flags,
        trace=trace,
    )


def _router_node(raw_text: str) -> str:
    head = raw_text[:500].lower()
    cv_markers = {"education", "experience", "skills", "projects", "curriculum vitae", "resume"}
    jd_markers = {"responsibilities", "requirements", "benefits", "job description"}
    cv_score = sum(marker in head for marker in cv_markers)
    jd_score = sum(marker in head for marker in jd_markers)
    if jd_score > cv_score and "skills" not in head:
        return "job_description"
    return "cv"


def _extractor_node(raw_text: str, *, source_quality: str) -> CVExtraction:
    found = []
    lowered = raw_text.lower()
    for skill in SKILL_PATTERNS:
        if re.search(rf"(?<![a-z0-9]){re.escape(skill)}(?![a-z0-9])", lowered):
            found.append(SkillEvidence(name=skill, evidence=_evidence_for(raw_text, skill)))
    return CVExtraction(
        summary=_summary(raw_text),
        skills=found,
        languages=_extract_languages(raw_text),
        raw_text_quality=source_quality,  # type: ignore[arg-type]
        confidence=0.72 if found else 0.35,
    )


def _critic_node(raw_text: str, normalized_skills: list[str]) -> list[str]:
    lowered = raw_text.lower()
    flags = []
    for skill in normalized_skills:
        if skill not in lowered and skill not in {"node", "react", "postgresql", "kubernetes"}:
            flags.append(f"skill_needs_evidence:{skill}")
    if len(raw_text.strip()) < 120:
        flags.append("cv_text_too_short")
    return flags


def _evidence_for(raw_text: str, skill: str) -> str:
    for line in raw_text.splitlines():
        if skill.lower().replace(".", "") in line.lower().replace(".", ""):
            return line.strip()[:300]
    return ""


def _summary(raw_text: str) -> str:
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    return " ".join(lines[:4])[:1000]


def _extract_languages(raw_text: str) -> list[str]:
    lowered = raw_text.lower()
    languages = []
    for language in ("english", "vietnamese", "japanese", "korean", "chinese", "french"):
        if language in lowered:
            languages.append(language)
    return languages
