"""Simple Streamlit demo UI for enterprise JD matching."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    import streamlit as st
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("Install streamlit to run the demo UI.") from exc

from backend.src.core.config import settings
from backend.src.models.schemas import MatchThresholds, job_from_dict, job_to_dict, match_result_to_dict
from backend.src.services.document_reader import extract_text_from_bytes
from backend.src.services.jd_parser import (
    parse_jd_form_with_metadata,
    parse_jd_text_with_metadata,
    parse_metadata_to_dict,
)
from backend.src.services.matching import match_students_for_job
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


def log_ui_action(action: str, detail: str) -> None:
    logger.info("action=%s %s", action, detail)


def short_error(error: object) -> str:
    if not error:
        return ""
    cleaned = " ".join(str(error).split())
    return cleaned[:180]


def parse_detail(job_id: str, metadata: dict) -> str:
    mode = metadata.get("parser_mode", "unknown")
    model = metadata.get("model", "unknown")
    error = short_error(metadata.get("error"))
    if metadata.get("fallback_used"):
        if error:
            return f"{job_id} fallback ({model}) error={error}"
        return f"{job_id} fallback ({model}) reason=llm_not_configured_or_disabled"
    return f"{job_id} {mode} ({model})"


def render_parsed_job_review(job_data: dict, key_prefix: str) -> None:
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


st.set_page_config(page_title="Enterprise JD Matching", layout="wide")
st.title("Enterprise JD Matching")

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

tab_parse, tab_manage, tab_match = st.tabs(["Parse JD", "Manage Jobs", "Match Students"])

with tab_parse:
    input_mode = st.radio("Input mode", ["Form", "Upload", "Raw text"], horizontal=True)
    company_id = st.text_input("Company ID", value="company_demo")

    if input_mode == "Form":
        form = {
            "title": st.text_input("Job title", value="Backend Intern"),
            "location": st.text_input("Location", value="Ho Chi Minh City"),
            "salary_range": st.text_input("Salary range", value="3-5M VND"),
            "benefits": st.text_input("Benefits", value="Mentorship, flexible schedule"),
            "requirements": st.text_area("Requirements", value="Strong Python and SQL. Basic Docker is preferred."),
        }
        parse_clicked = st.button("Parse form")
        if parse_clicked:
            result = parse_jd_form_with_metadata(form, company_id=company_id)
            st.session_state["draft_job"] = job_to_dict(result.job)
            st.session_state["parser_metadata"] = parse_metadata_to_dict(result.metadata)
            log_ui_action("parse_form", parse_detail(result.job.job_id, st.session_state["parser_metadata"]))
    elif input_mode == "Upload":
        uploaded = st.file_uploader("Upload JD", type=["txt", "pdf", "docx"])
        parse_clicked = st.button("Parse upload")
        if parse_clicked and uploaded is not None:
            try:
                raw_text = extract_text_from_bytes(uploaded.name, uploaded.read())
                result = parse_jd_text_with_metadata(raw_text, company_id=company_id)
                st.session_state["draft_job"] = job_to_dict(result.job)
                st.session_state["parser_metadata"] = parse_metadata_to_dict(result.metadata)
                detail = f"{result.job.job_id} from {uploaded.name}"
                log_ui_action("parse_upload", f"{detail}; {parse_detail(result.job.job_id, st.session_state['parser_metadata'])}")
            except Exception as exc:
                log_ui_action("parse_upload_failed", str(exc)[:80])
                st.error(str(exc))
        elif parse_clicked:
            log_ui_action("parse_upload", "no file selected")
    else:
        raw_text = st.text_area("Raw JD text", height=220)
        parse_clicked = st.button("Parse text")
        if parse_clicked:
            result = parse_jd_text_with_metadata(raw_text, company_id=company_id)
            st.session_state["draft_job"] = job_to_dict(result.job)
            st.session_state["parser_metadata"] = parse_metadata_to_dict(result.metadata)
            log_ui_action("parse_text", parse_detail(result.job.job_id, st.session_state["parser_metadata"]))

    if "draft_job" in st.session_state:
        if "parser_metadata" in st.session_state:
            metadata = st.session_state["parser_metadata"]
            if metadata["used_llm"]:
                st.success(f"Last parse used {metadata['parser_mode']} ({metadata['model']}).")
            elif metadata["api_key_configured"] and metadata["fallback_used"]:
                st.warning("LLM credentials exist, but the last parse used fallback because the LLM call failed.")
                if metadata.get("error"):
                    st.caption(metadata["error"])
            else:
                st.info("Last parse used the local fallback/mock parser because the selected LLM is not configured.")
        st.subheader("Review parsed job")
        render_parsed_job_review(st.session_state["draft_job"], key_prefix="draft-job")
        st.subheader("Edit JSON before saving")
        edited = st.text_area(
            "Validated job JSON",
            value=json.dumps(st.session_state["draft_job"], indent=2, ensure_ascii=False),
            height=420,
        )
        if st.button("Validate and save job"):
            try:
                job = job_from_dict(json.loads(edited))
                job_repo.save(job)
                log_ui_action("save_job", job.job_id)
                st.success(f"Saved {job.job_id}")
            except Exception as exc:
                log_ui_action("save_failed", str(exc)[:80])
                st.error(str(exc))

with tab_manage:
    jobs = job_repo.list()
    if not jobs:
        st.info("No jobs saved yet.")
    for job in jobs:
        with st.expander(f"{job.title} ({job.job_id}) - {job.status}"):
            render_parsed_job_review(job_to_dict(job), key_prefix=f"job-{job.job_id}")
            col1, col2, col3 = st.columns(3)
            if col1.button("Open", key=f"open-{job.job_id}"):
                job_repo.update_status(job.job_id, "open")
                log_ui_action("open_job", job.job_id)
                st.rerun()
            if col2.button("Close", key=f"close-{job.job_id}"):
                job_repo.update_status(job.job_id, "closed")
                log_ui_action("close_job", job.job_id)
                st.rerun()
            if col3.button("Delete", key=f"delete-{job.job_id}"):
                job_repo.delete(job.job_id)
                log_ui_action("delete_job", job.job_id)
                st.rerun()

with tab_match:
    jobs = [job for job in job_repo.list() if job.status == "open"]
    if not jobs:
        st.info("Open at least one job before running matching.")
    else:
        selected = st.selectbox("Open job", jobs, format_func=lambda job: f"{job.title} ({job.job_id})")
        strong = st.slider("Strong match threshold", 0.0, 1.0, settings.strong_match_threshold, 0.05)
        partial = st.slider("Partial match threshold", 0.0, strong, settings.partial_match_threshold, 0.05)
        if st.button("Run matching"):
            results = match_students_for_job(
                selected,
                student_provider.list_profiles(),
                MatchThresholds(strong_match=strong, partial_match=partial),
            )
            log_ui_action("run_match", f"{selected.job_id}: {len(results)} results")
            st.dataframe(
                [
                    {
                        "student_id": result.student_id,
                        "student_name": result.student_name,
                        "score": result.match_score,
                        "status": result.match_status,
                        "matched_skills": ", ".join(result.matched_skills),
                        "explanation": result.explanation,
                    }
                    for result in results
                ],
                width="stretch",
            )
            st.json([match_result_to_dict(result) for result in results])
