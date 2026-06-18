from __future__ import annotations

from typing import Any

from app.ai.agents.cv_pipeline import run_cv_pipeline
from app.ai.agents.react import BoundedReActRuntime
from app.ai.agents.runtime import (
    AgentExecutionError,
    AgentRegistry,
    AgentResult,
    AgentStep,
    AgentTask,
)
from app.ai.matching import normalize_skills
from app.ai.safety import detect_prompt_injection, mask_pii
from app.modules.ai_operations.application.legacy_ai_service import (
    evaluate_job_policy,
    extract_skills,
    match_cv_to_job,
    parse_job_requirements,
)

WORKFORCE_VERSION = "workforce-v1"

AGENT_CAPABILITIES = (
    {
        "task_type": "cv_extraction",
        "agent": "cv_extraction_agent",
        "purpose": "Extract, normalize, quality-check, and redact CV data.",
        "human_review_policy": "Required when quality flags are present.",
    },
    {
        "task_type": "profile_matching",
        "agent": "profile_matching_agent",
        "purpose": "Score CV-to-job fit from skills and semantic signals.",
        "human_review_policy": "Advisory only; never makes hiring decisions.",
    },
    {
        "task_type": "jd_analysis",
        "agent": "job_description_agent",
        "purpose": "Parse requirements and apply job-content policy.",
        "human_review_policy": "Required for policy or quality flags.",
    },
    {
        "task_type": "moderation",
        "agent": "moderation_agent",
        "purpose": "Detect policy risks and prompt-injection content.",
        "human_review_policy": "Flagged content is routed to review.",
    },
    {
        "task_type": "admin_review",
        "agent": "admin_review_copilot",
        "purpose": "Summarize evidence and prepare a non-binding recommendation.",
        "human_review_policy": "A human reviewer always decides.",
    },
    {
        "task_type": "verification",
        "agent": "verification_agent",
        "purpose": "Check submission completeness and evidence requirements.",
        "human_review_policy": "A human reviewer always decides.",
    },
    {
        "task_type": "career_coaching",
        "agent": "career_coaching_agent",
        "purpose": "Build a bounded, evidence-oriented development plan.",
        "human_review_policy": "User-controlled advisory output.",
    },
)


def build_agent_registry() -> AgentRegistry:
    return AgentRegistry(
        {
            "cv_extraction": _cv_extraction_agent,
            "profile_matching": _profile_matching_agent,
            "jd_analysis": _jd_analysis_agent,
            "moderation": _moderation_agent,
            "admin_review": _admin_review_agent,
            "verification": _verification_agent,
            "career_coaching": _career_coaching_agent,
        }
    )


def describe_workforce() -> list[dict[str, str]]:
    return [dict(item) for item in AGENT_CAPABILITIES]


def _cv_extraction_agent(task: AgentTask) -> AgentResult:
    raw_text = _required_text(task.payload, "raw_text")
    source_quality = str(task.payload.get("source_quality", "native_text"))
    if source_quality not in {"native_text", "ocr_needed", "vision_extracted", "unknown"}:
        source_quality = "unknown"
    pipeline = run_cv_pipeline(raw_text, source_quality=source_quality)
    return AgentResult(
        agent="cv_extraction_agent",
        status="completed",
        output={
            "extraction": pipeline.parsed_data,
            "masked_data": pipeline.masked_data,
            "normalized_skills": pipeline.normalized_skills,
            "quality_flags": pipeline.quality_flags,
            "workforce_version": WORKFORCE_VERSION,
        },
        steps=[
            AgentStep(
                sequence=index + 1,
                agent="cv_extraction_agent",
                action=item["node"],
                summary=item["result"],
            )
            for index, item in enumerate(pipeline.trace)
        ],
        confidence=float(pipeline.parsed_data.get("confidence", 0.0)),
        requires_human_review=bool(pipeline.quality_flags),
    )


def _profile_matching_agent(task: AgentTask) -> AgentResult:
    cv_text = _required_text(task.payload, "cv_text")
    job_description = _required_text(task.payload, "job_description")
    result = match_cv_to_job(cv_text, job_description)
    return AgentResult(
        agent="profile_matching_agent",
        status="completed",
        output={**result.model_dump(), "workforce_version": WORKFORCE_VERSION},
        steps=[
            AgentStep(1, "profile_matching_agent", "extract_skills", "Extracted comparable skills"),
            AgentStep(2, "profile_matching_agent", "semantic_match", "Combined skill and embedding signals"),
        ],
        confidence=min(1.0, result.score / 100),
        requires_human_review=result.score < 45,
    )


def _jd_analysis_agent(task: AgentTask) -> AgentResult:
    description = _required_text(task.payload, "job_description")
    requirements = parse_job_requirements(description)
    approved, reasons, trace = evaluate_job_policy(description)
    return AgentResult(
        agent="job_description_agent",
        status="completed",
        output={
            "requirements": requirements,
            "policy": {"eligible_for_auto_approval": approved, "reasons": reasons, "trace": trace},
            "workforce_version": WORKFORCE_VERSION,
        },
        steps=[
            AgentStep(1, "job_description_agent", "parse", "Parsed requirements and seniority"),
            AgentStep(2, "job_description_agent", "policy_check", "Applied deterministic job policy"),
        ],
        confidence=0.9 if requirements["skills"] else 0.55,
        requires_human_review=not approved,
    )


def _moderation_agent(task: AgentTask) -> AgentResult:
    content = _required_text(task.payload, "content")
    approved, reasons, trace = evaluate_job_policy(content)
    injection_hits = detect_prompt_injection(content)
    return AgentResult(
        agent="moderation_agent",
        status="completed",
        output={
            "decision": "allow" if approved else "review",
            "reasons": reasons,
            "prompt_injection_hits": injection_hits,
            "trace": trace,
            "workforce_version": WORKFORCE_VERSION,
        },
        steps=[
            AgentStep(1, "moderation_agent", "policy_check", "Evaluated content policy"),
            AgentStep(2, "moderation_agent", "injection_scan", "Scanned untrusted instructions"),
        ],
        confidence=0.95 if approved else 0.75,
        requires_human_review=not approved,
    )


def _admin_review_agent(task: AgentTask) -> AgentResult:
    evidence = task.payload.get("evidence")
    if not isinstance(evidence, list):
        evidence = []
    risk_flags = [str(item) for item in task.payload.get("risk_flags", [])]
    missing = [str(item) for item in task.payload.get("missing_items", [])]
    recommendation = "approve"
    if risk_flags or missing:
        recommendation = "request_changes"
    return AgentResult(
        agent="admin_review_copilot",
        status="completed",
        output={
            "recommendation": recommendation,
            "evidence_count": len(evidence),
            "risk_flags": risk_flags,
            "missing_items": missing,
            "reviewer_must_decide": True,
            "workforce_version": WORKFORCE_VERSION,
        },
        steps=[
            AgentStep(1, "admin_review_copilot", "evidence_check", "Checked supplied evidence"),
            AgentStep(2, "admin_review_copilot", "risk_summary", "Prepared non-binding recommendation"),
        ],
        confidence=0.8 if evidence else 0.4,
        requires_human_review=True,
    )


def _verification_agent(task: AgentTask) -> AgentResult:
    required = {str(item) for item in task.payload.get("required_fields", [])}
    supplied = {
        key
        for key, value in task.payload.get("submission", {}).items()
        if value not in (None, "", [], {})
    }
    missing = sorted(required - supplied)
    return AgentResult(
        agent="verification_agent",
        status="completed",
        output={
            "complete": not missing,
            "missing_fields": missing,
            "decision": "eligible_for_review" if not missing else "request_changes",
            "workforce_version": WORKFORCE_VERSION,
        },
        steps=[
            AgentStep(1, "verification_agent", "completeness", "Checked required submission fields"),
        ],
        confidence=1.0,
        requires_human_review=True,
    )


def _career_coaching_agent(task: AgentTask) -> AgentResult:
    runtime = BoundedReActRuntime(
        agent_name="career_coaching_agent",
        tools={
            "sanitize_profile": _sanitize_profile,
            "analyze_skills": _analyze_skills,
            "build_plan": _build_plan,
        },
        planner=_coaching_planner,
        max_steps=4,
    )
    execution = runtime.run(task.payload)
    safe_output = {
        key: execution.output[key]
        for key in (
            "sanitized_profile",
            "pii_entities_removed",
            "skills",
            "skill_gaps",
            "coaching_plan",
        )
        if key in execution.output
    }
    return AgentResult(
        agent="career_coaching_agent",
        status="completed",
        output={**safe_output, "workforce_version": WORKFORCE_VERSION},
        steps=execution.steps,
        confidence=0.75 if safe_output.get("skills") else 0.5,
        requires_human_review=False,
    )


def _coaching_planner(state: dict[str, Any], steps: list[AgentStep]) -> str:
    completed = {step.action for step in steps}
    if "sanitize_profile" not in completed:
        return "sanitize_profile"
    if "analyze_skills" not in completed:
        return "analyze_skills"
    if "build_plan" not in completed:
        return "build_plan"
    return "finish"


def _sanitize_profile(state: dict[str, Any]) -> dict[str, Any]:
    profile = str(state.get("profile_text") or state.get("goal") or "")
    masked, entities = mask_pii(profile)
    return {
        "sanitized_profile": masked,
        "pii_entities_removed": len(entities),
        "summary": "Removed personal identifiers before coaching analysis",
    }


def _analyze_skills(state: dict[str, Any]) -> dict[str, Any]:
    text = str(state.get("sanitized_profile", ""))
    skills = normalize_skills(extract_skills(text))
    target_skills = normalize_skills([str(item) for item in state.get("target_skills", [])])
    gaps = sorted(set(target_skills) - set(skills))
    return {
        "skills": skills,
        "skill_gaps": gaps,
        "summary": f"Identified {len(skills)} skills and {len(gaps)} target gaps",
    }


def _build_plan(state: dict[str, Any]) -> dict[str, Any]:
    gaps = [str(item) for item in state.get("skill_gaps", [])]
    if not gaps:
        gaps = ["portfolio evidence", "interview practice"]
    plan = [
        {
            "priority": index,
            "goal": gap,
            "next_action": f"Complete one measurable {gap} exercise and record evidence",
        }
        for index, gap in enumerate(gaps[:5], start=1)
    ]
    return {
        "coaching_plan": plan,
        "summary": f"Built a {len(plan)}-item evidence-based development plan",
    }


def _required_text(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise AgentExecutionError(f"Missing required text input: {key}")
    return value.strip()
