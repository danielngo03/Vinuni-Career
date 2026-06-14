"""CV parsing and student profile management page."""

from __future__ import annotations

from demo_auth import get_current_account_id, require_login
from shared import (
    job_review_data,
    job_repo,
    log_ui_action,
    render_home_link,
    render_parsed_job_review,
    render_parse_metadata_status,
    render_parser_status_sidebar,
    render_student_profile_review,
    student_repo,
)
from theme import apply_enterprise_theme, render_page_header, render_section_header

try:
    import streamlit as st
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("Install streamlit to run the demo UI.") from exc

from backend.src.core.config import settings
from backend.src.models.schemas import MatchThresholds, student_from_dict, student_to_dict
from backend.src.services.cv_parser import (
    cv_parse_metadata_to_dict,
    parse_cv_form_with_metadata,
    parse_cv_text_with_metadata,
)
from backend.src.services.cv_reviewer import review_student_against_job
from backend.src.services.document_reader import extract_text_from_bytes
from backend.src.services.matching import match_students_for_job


st.set_page_config(page_title="CV Analysis", layout="wide")
apply_enterprise_theme()
user = require_login("student")
render_parser_status_sidebar()
student_account_id = get_current_account_id()
render_home_link()
render_page_header(
    "Student Career Portal",
    "Parse your CV, maintain a structured profile, compare against open jobs, and get targeted CV review.",
    kicker="Student workspace",
    pills=[f"Student {student_account_id}", "Matching score", "CV review"],
)

tab_parse, tab_manage, tab_match, tab_review = st.tabs(["Parse CV", "Manage Students", "Match Jobs", "Review CV"])

with tab_parse:
    render_section_header("Parse CV", "Create a structured skill profile from form data, upload, or raw text.")
    input_mode = st.radio("Input mode", ["Form", "Upload", "Raw text"], horizontal=True)

    if input_mode == "Form":
        form = {
            "name": st.text_input("Full name", value=""),
            "email": st.text_input("Email", value=""),
            "phone": st.text_input("Phone", value=""),
            "major": st.text_input("Major", value=""),
            "year": st.text_input("Year", value=""),
            "skills": st.text_area(
                "Skills",
                value="",
                height=90,
            ),
            "education": st.text_area(
                "Education",
                value="",
                height=90,
            ),
            "projects": st.text_area(
                "Projects",
                value="",
                height=120,
            ),
            "experience": st.text_area("Experience", value="", height=90),
        }
        parse_clicked = st.button("Parse form")
        if parse_clicked:
            if not any(str(value).strip() for value in form.values()):
                st.error("Enter CV information before parsing.")
                log_ui_action("parse_cv_form", "empty form")
                st.stop()
            result = parse_cv_form_with_metadata(form)
            st.session_state["draft_student"] = student_to_dict(result.student)
            st.session_state["draft_student_source_text"] = result.raw_text
            st.session_state["cv_parser_metadata"] = cv_parse_metadata_to_dict(result.metadata)
            log_ui_action("parse_cv_form", result.student.student_id)
    elif input_mode == "Upload":
        uploaded = st.file_uploader("Upload student CV", type=["txt", "pdf", "docx"])
        parse_clicked = st.button("Parse upload")
        if parse_clicked and uploaded is not None:
            try:
                raw_text = extract_text_from_bytes(uploaded.name, uploaded.read())
                result = parse_cv_text_with_metadata(raw_text)
                st.session_state["draft_student"] = student_to_dict(result.student)
                st.session_state["draft_student_source_text"] = result.raw_text
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
            if not raw_text.strip():
                st.error("Enter CV text before parsing.")
                log_ui_action("parse_cv_text", "empty text")
                st.stop()
            result = parse_cv_text_with_metadata(raw_text)
            st.session_state["draft_student"] = student_to_dict(result.student)
            st.session_state["draft_student_source_text"] = result.raw_text
            st.session_state["cv_parser_metadata"] = cv_parse_metadata_to_dict(result.metadata)
            log_ui_action("parse_cv_text", result.student.student_id)

    if "draft_student" in st.session_state:
        metadata = st.session_state.get("cv_parser_metadata", {})
        render_parse_metadata_status(metadata, "CV")

        render_section_header("Review Parsed Profile", "Check extracted skills and evidence before saving.")
        render_student_profile_review(st.session_state["draft_student"], key_prefix="draft-student")
        if st.button("Save student profile"):
            try:
                student_data = dict(st.session_state["draft_student"])
                student_data["student_id"] = student_account_id
                metadata = student_data.setdefault("metadata", {})
                if isinstance(metadata, dict):
                    metadata["owner_user_id"] = student_account_id
                    source_text = str(st.session_state.get("draft_student_source_text", "")).strip()
                    if source_text:
                        metadata["cv_text_excerpt"] = source_text[:6000]
                student = student_from_dict(student_data)
                student_repo.save(student)
                log_ui_action("save_student", student.student_id)
                st.success(f"Saved {student.student_id}")
            except Exception as exc:
                log_ui_action("save_student_failed", str(exc)[:80])
                st.error(str(exc))

with tab_manage:
    render_section_header("Manage Profiles", "Review saved CV-derived profiles for this student account.")
    students = [
        student
        for student in student_repo.list_profiles()
        if student.student_id == student_account_id or student.metadata.get("owner_user_id") == student_account_id
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
    render_section_header("Match Open Jobs", "Compare one saved student profile against every open job.")
    students = [
        student
        for student in student_repo.list_profiles()
        if student.student_id == student_account_id or student.metadata.get("owner_user_id") == student_account_id
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

        render_section_header("Open Job Details", "Inspect requirements before running the match.")
        for job in open_jobs:
            with st.expander(f"{job.title} ({job.job_id})"):
                render_parsed_job_review(job_review_data(job), key_prefix=f"student-job-detail-{job.job_id}")

        if st.button("Run matching"):
            thresholds = MatchThresholds(strong_match=strong, partial_match=partial)
            matched_jobs = [
                (job, match_students_for_job(job, [selected_student], thresholds)[0])
                for job in open_jobs
            ]
            matched_jobs.sort(key=lambda item: item[1].match_score, reverse=True)
            log_ui_action("student_run_match", f"{selected_student.student_id}: {len(matched_jobs)} jobs")

            render_section_header("Match Results", "Jobs are sorted by highest matching score.")
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
                        job_review_data(job),
                        key_prefix=f"student-match-result-{job.job_id}",
                    )

with tab_review:
    render_section_header("Review CV Against JD", "Generate a structured gap review for one selected open job.")
    students = [
        student
        for student in student_repo.list_profiles()
        if student.student_id == student_account_id or student.metadata.get("owner_user_id") == student_account_id
    ]
    open_jobs = [job for job in job_repo.list() if job.status == "open"]

    if not students:
        st.info("No saved student profile yet.")
    elif not open_jobs:
        st.info("No open jobs available.")
    else:
        col_student, col_job = st.columns(2)
        selected_student = col_student.selectbox(
            "Student profile",
            students,
            format_func=lambda student: f"{student.name} ({student.student_id})",
            key="review-student",
        )
        selected_job = col_job.selectbox(
            "Open job",
            open_jobs,
            format_func=lambda job: f"{job.title} ({job.job_id})",
            key="review-job",
        )

        col_strong, col_partial, col_llm = st.columns(3)
        strong = col_strong.slider(
            "Strong match threshold",
            0.0,
            1.0,
            settings.strong_match_threshold,
            0.05,
            key="review-strong",
        )
        partial = col_partial.slider(
            "Partial match threshold",
            0.0,
            strong,
            settings.partial_match_threshold,
            0.05,
            key="review-partial",
        )
        use_llm = col_llm.checkbox("Use LLM review when configured", value=True)

        if st.button("Review selected job"):
            try:
                review = review_student_against_job(
                    selected_student,
                    selected_job,
                    thresholds=MatchThresholds(strong_match=strong, partial_match=partial),
                    use_llm=use_llm,
                )
                st.session_state["student_job_review"] = review
                log_ui_action("review_student_job", f"{selected_student.student_id} -> {selected_job.job_id}")
            except Exception as exc:
                log_ui_action("review_student_job_failed", str(exc)[:80])
                st.error(str(exc))

        review = st.session_state.get("student_job_review")
        if isinstance(review, dict):
            metadata = review.get("_reviewer", {})
            if metadata.get("used_llm"):
                st.success(f"Review used {metadata.get('reviewer_mode')} ({metadata.get('model')}).")
            elif metadata.get("api_key_configured") and metadata.get("fallback_used"):
                st.warning("LLM review failed, so the app used deterministic fallback review.")
                if metadata.get("error"):
                    st.caption(metadata["error"])
            else:
                st.info("Review used deterministic fallback because the selected LLM is not configured.")

            match = review.get("match", {})
            col_score, col_status, col_level = st.columns(3)
            col_score.metric("Matching Score", f"{float(match.get('match_score', 0)) * 100:.1f}%")
            col_status.metric("Match Status", str(match.get("match_status", "")))
            col_level.metric("Review Level", str(review.get("match_level", "")))

            render_section_header("Overall Assessment")
            st.write(review.get("overall_assessment", ""))

            render_section_header("Strengths")
            st.write(review.get("strengths", []))

            render_section_header("Missing Skills")
            missing_skills = review.get("missing_skills", [])
            if missing_skills:
                st.dataframe(missing_skills, hide_index=True, width="stretch")
            else:
                st.success("No missing or weak required skills detected.")

            render_section_header("Missing Keywords")
            missing_keywords = review.get("missing_keywords", [])
            if missing_keywords:
                st.write(", ".join(str(keyword) for keyword in missing_keywords))
            else:
                st.success("No important missing keywords detected.")

            col_improve, col_cv = st.columns(2)
            with col_improve:
                render_section_header("Skill Improvements")
                st.write(review.get("improvement_suggestions", []))
            with col_cv:
                render_section_header("CV Improvements")
                st.write(review.get("cv_improvements", []))

            render_section_header("Priority Actions")
            st.write(review.get("priority_actions", []))
