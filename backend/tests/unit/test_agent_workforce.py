from __future__ import annotations

import pytest

from app.ai.agents import AgentExecutionError, AgentTask, build_agent_registry


def test_registry_exposes_one_specialist_per_supported_run_type():
    registry = build_agent_registry()

    assert set(registry.task_types) == {
        "admin_review",
        "career_coaching",
        "cv_extraction",
        "jd_analysis",
        "moderation",
        "profile_matching",
        "verification",
    }


def test_career_coaching_uses_bounded_auditable_react_steps():
    result = build_agent_registry().execute(
        AgentTask(
            task_type="career_coaching",
            payload={
                "profile_text": "Student A\nPython FastAPI\na@example.com",
                "target_skills": ["Python", "Docker", "Kubernetes"],
            },
        )
    )

    assert [step.action for step in result.steps] == [
        "sanitize_profile",
        "analyze_skills",
        "build_plan",
    ]
    assert result.output["pii_entities_removed"] >= 1
    assert {"docker", "kubernetes"}.issubset(result.output["skill_gaps"])
    assert "a@example.com" not in str(result.to_dict())


def test_unknown_agent_task_is_rejected_instead_of_silently_completed():
    with pytest.raises(AgentExecutionError, match="No specialist agent"):
        build_agent_registry().execute(AgentTask(task_type="unknown", payload={}))
