"""Shared helpers for Streamlit pages."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    import streamlit as st
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("Install streamlit to run the demo UI.") from exc

from backend.src.core.config import settings
from backend.src.services.storage import JsonJobRepository, MockStudentProfileProvider


job_repo = JsonJobRepository(settings.jobs_dir)
student_provider = MockStudentProfileProvider(settings.mock_students_path)

logging.basicConfig(
    level=getattr(logging, getattr(settings, "log_level", "INFO").upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("frontend.ui")


def provider_is_configured() -> bool:
    provider = settings.llm_provider.strip().lower()
    if provider == "gemini":
        return bool(settings.google_api_key)
    if provider == "openai":
        return bool(settings.openai_api_key)
    if provider == "openrouter":
        return bool(settings.openrouter_api_key and settings.openrouter_base_url)
    if provider == "ollama":
        return bool(settings.ollama_base_url)
    if provider == "custom":
        return bool(settings.custom_llm_api_key and settings.custom_llm_base_url)
    return False


def render_parser_status_sidebar() -> None:
    st.sidebar.header("Parser Status")
    if provider_is_configured():
        st.sidebar.success(f"{settings.llm_provider} configured")
        st.sidebar.caption("JD parsing will try the selected LLM first, then fallback if the call fails.")
    else:
        st.sidebar.warning(f"{settings.llm_provider} not configured")
        st.sidebar.caption("JD parsing is using the local fallback/mock parser.")
    st.sidebar.text_input("LLM model", value=settings.llm_model, disabled=True)
    st.sidebar.metric("Default strong threshold", settings.strong_match_threshold)
    st.sidebar.metric("Default partial threshold", settings.partial_match_threshold)

    if "parser_metadata" in st.session_state:
        metadata = st.session_state["parser_metadata"]
        st.sidebar.divider()
        st.sidebar.subheader("Last Parse")
        if metadata["used_llm"]:
            st.sidebar.success(f"Used {metadata['parser_mode']}")
        elif metadata["api_key_configured"] and metadata["fallback_used"]:
            st.sidebar.error("LLM failed, used fallback")
        else:
            st.sidebar.info("Used fallback/mock parser")
        st.sidebar.json(metadata)


def log_ui_action(action: str, detail: str) -> None:
    logger.info("action=%s %s", action, detail)


def short_error(error: object) -> str:
    if not error:
        return ""
    cleaned = " ".join(str(error).split())
    return cleaned[:180]


def parse_detail(job_id: str, metadata: dict[str, Any]) -> str:
    mode = metadata.get("parser_mode", "unknown")
    model = metadata.get("model", "unknown")
    error = short_error(metadata.get("error"))
    if metadata.get("fallback_used"):
        if error:
            return f"{job_id} fallback ({model}) error={error}"
        return f"{job_id} fallback ({model}) reason=llm_not_configured_or_disabled"
    return f"{job_id} {mode} ({model})"


def render_parsed_job_review(job_data: dict[str, Any], key_prefix: str) -> None:
    overview_fields = [
        "job_id",
        "company_id",
        "title",
        "status",
        "employment_type",
        "location",
        "salary_range",
    ]
    overview = {field: job_data.get(field, "") for field in overview_fields}
    skills = job_data.get("skills", {})
    benefits = job_data.get("benefits", [])
    raw_text = job_data.get("raw_text", "")

    tab_overview, tab_requirements, tab_raw = st.tabs(["Job info", "Skills & benefits", "Raw JD"])

    with tab_overview:
        col_title, col_status, col_location = st.columns(3)
        col_title.metric("Title", str(job_data.get("title", "Untitled Job")))
        col_status.metric("Status", str(job_data.get("status", "draft")))
        col_location.metric("Location", str(job_data.get("location", "unspecified")))
        st.dataframe(
            [{"field": field, "value": value} for field, value in overview.items()],
            hide_index=True,
            width="stretch",
        )

    with tab_requirements:
        skill_rows = [
            {
                "skill": skill_name,
                "required_level": requirement.get("required_level"),
                "importance": requirement.get("importance"),
                "required": requirement.get("required"),
            }
            for skill_name, requirement in skills.items()
        ]
        st.caption(f"{len(skill_rows)} skills detected")
        if skill_rows:
            st.dataframe(skill_rows, hide_index=True, width="stretch")
        else:
            st.info("No skills detected.")

        st.caption(f"{len(benefits)} benefits detected")
        if benefits:
            st.write(", ".join(str(benefit) for benefit in benefits))
        else:
            st.info("No benefits detected.")

    with tab_raw:
        st.text_area(
            "Original job description",
            value=str(raw_text),
            height=320,
            disabled=True,
            key=f"{key_prefix}-raw-text",
        )
