"""B-588: curated skill -> learning-resource catalog.

Known skills return a specific ``resource_type`` + tailored suggestion; unknown
skills return the generic ``practice_project`` fallback. Deterministic and
i18n-safe (vi default, en override).
"""

from __future__ import annotations

from app.modules.opportunities.domain import learning_resources


def test_docker_returns_specific_resource() -> None:
    r = learning_resources.resource_for("Docker", locale="en")
    assert r["resource_type"] == "hands_on_lab"
    assert "Docker" in r["suggestion"]


def test_sql_returns_specific_resource() -> None:
    r = learning_resources.resource_for("SQL", locale="en")
    assert r["resource_type"] == "guided_dataset"
    assert "SQL" in r["suggestion"]


def test_python_returns_specific_resource() -> None:
    r = learning_resources.resource_for("Python", locale="en")
    assert r["resource_type"] == "coding_exercises"
    assert "Python" in r["suggestion"]


def test_unknown_skill_falls_back_to_generic() -> None:
    r = learning_resources.resource_for("Underwater Basket Weaving", locale="en")
    assert r["resource_type"] == "practice_project"
    assert "Underwater Basket Weaving" in r["suggestion"]


def test_soft_skill_maps_to_experience_reflection() -> None:
    r = learning_resources.resource_for("Communication", locale="en")
    assert r["resource_type"] == "experience_reflection"
    assert "Communication" in r["suggestion"]


def test_aliases_resolve() -> None:
    assert learning_resources.resource_for("k8s")["resource_type"] == "hands_on_lab"
    assert learning_resources.resource_for("postgres")["resource_type"] == "guided_dataset"
    assert learning_resources.resource_for("JS")["resource_type"] == "coding_exercises"


def test_first_token_resolves_versioned_skill() -> None:
    r = learning_resources.resource_for("Python 3.11", locale="en")
    assert r["resource_type"] == "coding_exercises"
    assert "Python 3.11" in r["suggestion"]


def test_locale_defaults_to_vietnamese() -> None:
    vi = learning_resources.resource_for("Docker")  # default locale
    en = learning_resources.resource_for("Docker", locale="en")
    assert "Đóng gói" in vi["suggestion"]  # vi-specific wording
    assert "Containerize" in en["suggestion"]  # en-specific wording
    assert vi["resource_type"] == en["resource_type"] == "hands_on_lab"


def test_unknown_locale_falls_back_to_vietnamese() -> None:
    r = learning_resources.resource_for("Docker", locale="fr")
    assert "Đóng gói" in r["suggestion"]  # unknown locale -> vi copy


def test_deterministic() -> None:
    a = learning_resources.resource_for("Kubernetes", locale="en")
    b = learning_resources.resource_for("Kubernetes", locale="en")
    assert a == b


def test_no_provider_or_model_leak_in_suggestions() -> None:
    forbidden = ["openrouter", "openai", "anthropic", "claude", "gpt", "gemini"]
    for skill in ["Docker", "SQL", "Python", "AWS", "React", "Git", "Unknown Skill"]:
        for locale in ("vi", "en"):
            suggestion = learning_resources.resource_for(skill, locale=locale)[
                "suggestion"
            ].lower()
            for term in forbidden:
                assert term not in suggestion
