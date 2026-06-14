"""Shared dashboard renderer for the Streamlit app."""

from __future__ import annotations

from collections import Counter

from demo_auth import get_current_account_id, get_current_role, render_login, render_logout_sidebar
from shared import job_repo, render_parser_status_sidebar, student_repo
from theme import render_page_header, render_section_header, render_status_strip, render_workspace_card
from backend.src.core.config import settings

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

    if role == "enterprise":
        render_page_header(
            "Enterprise Talent Console",
            "Create structured job requirements, manage openings, and review ranked student matches.",
            kicker="Company workspace",
            pills=[f"Account {account_id}", "JD parsing", "Talent matching"],
        )
    elif role == "student":
        render_page_header(
            "Student Career Portal",
            "Understand your current profile, discover matching jobs, and review CV gaps against open roles.",
            kicker="Student workspace",
            pills=[f"Account {account_id}", "CV analysis", "Job review"],
        )
    else:
        render_page_header(
            "Academic Operations Dashboard",
            "Monitor demo data and prepare transcript assets for retrieval-ready course content.",
            kicker="Teacher workspace",
            pills=[f"Account {account_id}", "Course data", "RAG pipeline"],
        )

    if role == "enterprise":
        jobs = [job for job in job_repo.list() if job.company_id == account_id]
        open_jobs = [job for job in jobs if job.status == "open"]
        render_status_strip(
            [
                {"label": "Saved jobs", "value": len(jobs), "note": "Owned by this company"},
                {"label": "Open jobs", "value": len(open_jobs), "note": "Visible to students"},
                {"label": "Students", "value": len(student_repo.list_profiles()), "note": "Profiles available"},
                {"label": "Default strong", "value": f"{settings.strong_match_threshold:.0%}", "note": "Configurable"},
            ]
        )
    elif role == "teacher":
        render_teacher_stats()
    else:
        students = [
            student
            for student in student_repo.list_profiles()
            if student.student_id == account_id or student.metadata.get("owner_user_id") == account_id
        ]
        open_jobs = [job for job in job_repo.list() if job.status == "open"]
        render_status_strip(
            [
                {"label": "Saved profiles", "value": len(students), "note": "Owned by student"},
                {"label": "Open jobs", "value": len(open_jobs), "note": "Ready to match"},
                {"label": "Mock profiles", "value": len([s for s in student_repo.list_profiles() if s.metadata.get("is_mock")]), "note": "Demo data"},
                {"label": "Review mode", "value": "AI", "note": "Fallback ready"},
            ]
        )

    render_section_header("Workspace", "Select the operation surface for this account.")
    if role == "enterprise":
        render_workspace_card(
            "Enterprise",
            "JD Workspace",
            "Parse job descriptions, manage status, and run explainable student matching.",
        )
        st.page_link("pages/1_Enterprise_JD_Workspace.py", label="Enterprise JD Workspace")
    elif role == "student":
        render_workspace_card(
            "Student",
            "CV Analysis",
            "Parse a CV, save a profile, match open roles, and review gaps against one JD.",
        )
        st.page_link("pages/2_Student_CV_Analysis.py", label="Student CV Analysis")
    else:
        render_workspace_card(
            "Teacher",
            "RAG Pipeline",
            "Build clean transcript data and chunk outputs from YouTube course sources.",
        )
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

    render_section_header("Enterprise Job Summary", "Live counts grouped by company account.")
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

    render_section_header("Student Skill Summary", "Most represented skills across saved student profiles.")
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
