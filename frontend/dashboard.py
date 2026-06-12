"""Shared dashboard renderer for the Streamlit app."""

from __future__ import annotations

from collections import Counter

from demo_auth import get_current_account_id, get_current_role, render_login, render_logout_sidebar
from shared import job_repo, render_parser_status_sidebar, student_repo

try:
    import streamlit as st
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("Install streamlit to run the demo UI.") from exc


def render_dashboard() -> None:
    user = st.session_state.get("auth_user")
    if not isinstance(user, dict):
        render_login()
        st.stop()

    render_parser_status_sidebar()
    render_logout_sidebar(user)
    role = get_current_role()
    account_id = get_current_account_id()

    title = "Teacher Dashboard" if role == "teacher" else "Corhort Matching Demo"
    st.title(title)
    st.caption("Use the sidebar navigation to work with the available workspace for this account.")

    if role == "enterprise":
        col_jobs, col_open = st.columns(2)
        jobs = [job for job in job_repo.list() if job.company_id == account_id]
        open_jobs = [job for job in jobs if job.status == "open"]

        col_jobs.metric("Saved jobs", len(jobs))
        col_open.metric("Open jobs", len(open_jobs))
    elif role == "teacher":
        render_teacher_stats()

    st.subheader("Pages")
    if role == "enterprise":
        st.page_link("pages/1_Enterprise_JD_Workspace.py", label="Enterprise JD Workspace")
    elif role == "student":
        st.page_link("pages/2_Student_CV_Analysis.py", label="Student CV Analysis")
    else:
        st.page_link("pages/3_Teacher_RAG_Pipeline.py", label="Teacher RAG Pipeline")


def render_teacher_stats() -> None:
    jobs = job_repo.list()
    saved_students = student_repo.list_profiles()
    mock_students = [student for student in saved_students if student.metadata.get("is_mock") is True]
    company_ids = sorted({job.company_id for job in jobs})
    status_counts = Counter(job.status for job in jobs)
    skill_counts = Counter()
    for student in saved_students:
        skill_counts.update(student.skills.keys())

    col_students, col_companies, col_jobs, col_open = st.columns(4)
    col_students.metric("Saved student profiles", len(saved_students))
    col_companies.metric("Enterprises", len(company_ids))
    col_jobs.metric("Jobs", len(jobs))
    col_open.metric("Open jobs", status_counts.get("open", 0))

    col_draft, col_closed, col_mock = st.columns(3)
    col_draft.metric("Draft jobs", status_counts.get("draft", 0))
    col_closed.metric("Closed jobs", status_counts.get("closed", 0))
    col_mock.metric("Mock students", len(mock_students))

    st.subheader("Enterprise Job Summary")
    if company_ids:
        rows = []
        for company_id in company_ids:
            company_jobs = [job for job in jobs if job.company_id == company_id]
            company_status = Counter(job.status for job in company_jobs)
            rows.append(
                {
                    "company_id": company_id,
                    "total_jobs": len(company_jobs),
                    "open": company_status.get("open", 0),
                    "draft": company_status.get("draft", 0),
                    "closed": company_status.get("closed", 0),
                }
            )
        st.dataframe(rows, hide_index=True, width="stretch")
    else:
        st.info("No enterprise job data yet.")

    st.subheader("Student Skill Summary")
    if saved_students:
        st.dataframe(
            [
                {
                    "skill": skill,
                    "student_count": count,
                }
                for skill, count in skill_counts.most_common(15)
            ],
            hide_index=True,
            width="stretch",
        )
    else:
        st.info("No saved student profiles yet.")
