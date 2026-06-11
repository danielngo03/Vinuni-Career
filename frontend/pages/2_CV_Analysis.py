"""CV parsing and student profile management page."""

from __future__ import annotations

from demo_auth import get_current_user_id, require_login
from shared import (
    job_repo,
    log_ui_action,
    render_parsed_job_review,
    render_parser_status_sidebar,
    render_student_profile_review,
    student_repo,
)

try:
    import streamlit as st
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("Install streamlit to run the demo UI.") from exc

from backend.src.core.config import settings
from backend.src.models.schemas import MatchThresholds, student_from_dict, student_to_dict
from backend.src.services.cv_parser import cv_parse_metadata_to_dict, parse_cv_text_with_metadata
from backend.src.services.document_reader import extract_text_from_bytes
from backend.src.services.matching import match_students_for_job


st.set_page_config(page_title="CV Analysis", layout="wide")
user = require_login("student")
render_parser_status_sidebar()
student_user_id = get_current_user_id()
st.title("CV Analysis")

tab_parse, tab_manage, tab_match = st.tabs(["Parse CV", "Manage Students", "Match Jobs"])

with tab_parse:
    input_mode = st.radio("Input mode", ["Upload", "Raw text"], horizontal=True)

    if input_mode == "Upload":
        uploaded = st.file_uploader("Upload student CV", type=["txt", "pdf", "docx"])
        parse_clicked = st.button("Parse upload")
        if parse_clicked and uploaded is not None:
            try:
                raw_text = extract_text_from_bytes(uploaded.name, uploaded.read())
                result = parse_cv_text_with_metadata(raw_text)
                st.session_state["draft_student"] = student_to_dict(result.student)
                st.session_state["cv_parser_metadata"] = cv_parse_metadata_to_dict(result.metadata)
                log_ui_action("parse_cv_upload", f"{result.student.student_id} from {uploaded.name}")
            except Exception as exc:
                log_ui_action("parse_cv_upload_failed", str(exc)[:80])
                st.error(str(exc))
        elif parse_clicked:
            log_ui_action("parse_cv_upload", "no file selected")
    else:
        raw_text = st.text_area("Raw CV text", height=260)
        if st.button("Parse text"):
            result = parse_cv_text_with_metadata(raw_text)
            st.session_state["draft_student"] = student_to_dict(result.student)
            st.session_state["cv_parser_metadata"] = cv_parse_metadata_to_dict(result.metadata)
            log_ui_action("parse_cv_text", result.student.student_id)

    if "draft_student" in st.session_state:
        metadata = st.session_state.get("cv_parser_metadata", {})
        if metadata.get("used_llm"):
            st.success(f"Last parse used {metadata.get('parser_mode')} ({metadata.get('model')}).")
        elif metadata.get("api_key_configured") and metadata.get("fallback_used"):
            st.warning("LLM credentials exist, but the last CV parse used fallback because the LLM call failed.")
            if metadata.get("error"):
                st.caption(metadata["error"])
        else:
            st.info("Last CV parse used the local fallback parser because the selected LLM is not configured.")

        st.subheader("Review parsed student")
        render_student_profile_review(st.session_state["draft_student"], key_prefix="draft-student")
        if st.button("Save student profile"):
            try:
                student_data = dict(st.session_state["draft_student"])
                metadata = student_data.setdefault("metadata", {})
                if isinstance(metadata, dict):
                    metadata["owner_user_id"] = student_user_id
                student = student_from_dict(student_data)
                student_repo.save(student)
                log_ui_action("save_student", student.student_id)
                st.success(f"Saved {student.student_id}")
            except Exception as exc:
                log_ui_action("save_student_failed", str(exc)[:80])
                st.error(str(exc))

with tab_manage:
    students = [
        student
        for student in student_repo.list_profiles()
        if student.metadata.get("owner_user_id") == student_user_id
    ]
    if not students:
        st.info("No CV-derived students saved yet.")
    for student in students:
        with st.expander(f"{student.name} ({student.student_id})"):
            render_student_profile_review(student_to_dict(student), key_prefix=f"student-{student.student_id}")
            if st.button("Delete", key=f"delete-student-{student.student_id}"):
                student_repo.delete(student.student_id)
                log_ui_action("delete_student", student.student_id)
                st.rerun()

with tab_match:
    students = [
        student
        for student in student_repo.list_profiles()
        if student.metadata.get("owner_user_id") == student_user_id
    ]
    open_jobs = [job for job in job_repo.list() if job.status == "open"]

    if not students:
        st.info("No saved student profile yet.")
    elif not open_jobs:
        st.info("No open jobs available.")
    else:
        selected_student = st.selectbox(
            "Student profile",
            students,
            format_func=lambda student: f"{student.name} ({student.student_id})",
        )
        strong = st.slider("Strong match threshold", 0.0, 1.0, settings.strong_match_threshold, 0.05)
        partial = st.slider("Partial match threshold", 0.0, strong, settings.partial_match_threshold, 0.05)

        st.subheader("Open Job Details")
        for job in open_jobs:
            with st.expander(f"{job.title} ({job.job_id})"):
                render_parsed_job_review(
                    {
                        "job_id": job.job_id,
                        "company_id": job.company_id,
                        "title": job.title,
                        "status": job.status,
                        "employment_type": job.employment_type,
                        "location": job.location,
                        "salary_range": job.salary_range,
                        "benefits": job.benefits,
                        "skills": {
                            name: {
                                "required_level": requirement.required_level,
                                "importance": requirement.importance,
                                "required": requirement.required,
                            }
                            for name, requirement in job.skills.items()
                        },
                        "raw_text": job.raw_text,
                    },
                    key_prefix=f"student-job-detail-{job.job_id}",
                )

        if st.button("Run matching"):
            thresholds = MatchThresholds(strong_match=strong, partial_match=partial)
            matched_jobs = [
                (job, match_students_for_job(job, [selected_student], thresholds)[0])
                for job in open_jobs
            ]
            matched_jobs.sort(key=lambda item: item[1].match_score, reverse=True)
            log_ui_action("student_run_match", f"{selected_student.student_id}: {len(matched_jobs)} jobs")

            st.subheader("Match Results")
            st.dataframe(
                [
                    {
                        "job_id": job.job_id,
                        "title": job.title,
                        "company_id": job.company_id,
                        "score": result.match_score,
                        "status": result.match_status,
                        "matched_skills": ", ".join(result.matched_skills),
                        "explanation": result.explanation,
                    }
                    for job, result in matched_jobs
                ],
                width="stretch",
            )

            for job, result in matched_jobs:
                with st.expander(f"{job.title} - {result.match_status} ({result.match_score})"):
                    st.write(result.explanation)
                    if result.missing_or_weak_skills:
                        st.dataframe(
                            [
                                {
                                    "skill": skill_name,
                                    "student_score": gap.user_score,
                                    "required_level": gap.required_level,
                                    "gap": gap.gap,
                                    "importance": gap.importance,
                                    "required": gap.required,
                                }
                                for skill_name, gap in result.missing_or_weak_skills.items()
                            ],
                            hide_index=True,
                            width="stretch",
                        )
                    render_parsed_job_review(
                        {
                            "job_id": job.job_id,
                            "company_id": job.company_id,
                            "title": job.title,
                            "status": job.status,
                            "employment_type": job.employment_type,
                            "location": job.location,
                            "salary_range": job.salary_range,
                            "benefits": job.benefits,
                            "skills": {
                                name: {
                                    "required_level": requirement.required_level,
                                    "importance": requirement.importance,
                                    "required": requirement.required,
                                }
                                for name, requirement in job.skills.items()
                            },
                            "raw_text": job.raw_text,
                        },
                        key_prefix=f"student-match-result-{job.job_id}",
                    )
