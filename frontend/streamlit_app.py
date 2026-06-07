"""Simple Streamlit demo UI for enterprise JD matching."""

from __future__ import annotations

import json
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

st.set_page_config(page_title="Enterprise JD Matching", layout="wide")
st.title("Enterprise JD Matching")

st.sidebar.header("Parser Status")
if settings.gemini_api_key:
    st.sidebar.success("Gemini API key configured")
    st.sidebar.caption("JD parsing will try Gemini first, then fallback if the call fails.")
else:
    st.sidebar.warning("No Gemini API key")
    st.sidebar.caption("JD parsing is using the local fallback/mock parser.")
st.sidebar.text_input("Gemini model", value=settings.gemini_model, disabled=True)
st.sidebar.metric("Default strong threshold", settings.strong_match_threshold)
st.sidebar.metric("Default partial threshold", settings.partial_match_threshold)

if "parser_metadata" in st.session_state:
    metadata = st.session_state["parser_metadata"]
    st.sidebar.divider()
    st.sidebar.subheader("Last Parse")
    if metadata["used_llm"]:
        st.sidebar.success("Used Gemini")
    elif metadata["api_key_configured"] and metadata["fallback_used"]:
        st.sidebar.error("Gemini failed, used fallback")
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
    elif input_mode == "Upload":
        uploaded = st.file_uploader("Upload JD", type=["txt", "pdf", "docx"])
        parse_clicked = st.button("Parse upload")
        if parse_clicked and uploaded is not None:
            try:
                raw_text = extract_text_from_bytes(uploaded.name, uploaded.read())
                result = parse_jd_text_with_metadata(raw_text, company_id=company_id)
                st.session_state["draft_job"] = job_to_dict(result.job)
                st.session_state["parser_metadata"] = parse_metadata_to_dict(result.metadata)
            except Exception as exc:
                st.error(str(exc))
    else:
        raw_text = st.text_area("Raw JD text", height=220)
        parse_clicked = st.button("Parse text")
        if parse_clicked:
            result = parse_jd_text_with_metadata(raw_text, company_id=company_id)
            st.session_state["draft_job"] = job_to_dict(result.job)
            st.session_state["parser_metadata"] = parse_metadata_to_dict(result.metadata)

    if "draft_job" in st.session_state:
        if "parser_metadata" in st.session_state:
            metadata = st.session_state["parser_metadata"]
            if metadata["used_llm"]:
                st.success(f"Last parse used Gemini ({metadata['model']}).")
            elif metadata["api_key_configured"] and metadata["fallback_used"]:
                st.warning("Gemini API key exists, but the last parse used fallback because the Gemini call failed.")
                if metadata.get("error"):
                    st.caption(metadata["error"])
            else:
                st.info("Last parse used the local fallback/mock parser because no Gemini API key is configured.")
        st.subheader("Review and edit parsed JSON")
        edited = st.text_area(
            "Validated job JSON",
            value=json.dumps(st.session_state["draft_job"], indent=2, ensure_ascii=False),
            height=420,
        )
        if st.button("Validate and save job"):
            try:
                job = job_from_dict(json.loads(edited))
                job_repo.save(job)
                st.success(f"Saved {job.job_id}")
            except Exception as exc:
                st.error(str(exc))

with tab_manage:
    jobs = job_repo.list()
    if not jobs:
        st.info("No jobs saved yet.")
    for job in jobs:
        with st.expander(f"{job.title} ({job.job_id}) - {job.status}"):
            st.json(job_to_dict(job))
            col1, col2, col3 = st.columns(3)
            if col1.button("Open", key=f"open-{job.job_id}"):
                job_repo.update_status(job.job_id, "open")
                st.rerun()
            if col2.button("Close", key=f"close-{job.job_id}"):
                job_repo.update_status(job.job_id, "closed")
                st.rerun()
            if col3.button("Delete", key=f"delete-{job.job_id}"):
                job_repo.delete(job.job_id)
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
                use_container_width=True,
            )
            st.json([match_result_to_dict(result) for result in results])
