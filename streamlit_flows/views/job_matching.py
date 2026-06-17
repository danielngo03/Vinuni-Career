from __future__ import annotations

import streamlit as st

from api_data import (
    ROLE_ADMIN,
    ROLE_STUDENT,
    get_user_role,
    get_user_source_id,
    list_students,
    match_jobs_for_student,
    require_role,
)


def render_job_matching_page(api_base: str, token: str) -> None:
    """Render job matching as its own focused page."""
    require_role({ROLE_STUDENT, ROLE_ADMIN})

    students = _load_visible_students(api_base, token)
    st.title("Job Matching")

    if not students:
        if get_user_role() == ROLE_STUDENT:
            st.info("No student profile yet. Open the CVs page and save a primary CV first.")
        else:
            st.info("No student found.")
        return

    selected_student = _select_student(students, get_user_role())
    _render_matching_controls(api_base, token, selected_student)
    _render_stored_results()


def _load_visible_students(api_base: str, token: str) -> list[dict]:
    try:
        students = list_students(api_base, token)
    except RuntimeError as exc:
        st.error(str(exc))
        st.stop()

    role = get_user_role()
    source_id = get_user_source_id()
    if role != ROLE_STUDENT:
        return students

    if not source_id:
        st.error("This account is not linked to a demo student profile.")
        st.stop()
    return [student for student in students if student.get("student_id") == source_id]


def _select_student(students: list[dict], role: str) -> dict:
    if role == ROLE_STUDENT or len(students) == 1:
        return students[0]
    options = {_student_label(student): student for student in students}
    return options[st.selectbox("Student", list(options))]


def _student_label(student: dict) -> str:
    return f"{student.get('name', student['student_id'])} - {student['student_id']}"


def _render_matching_controls(api_base: str, token: str, student: dict) -> None:
    st.caption(f"Matching jobs for {_student_label(student)}")
    left, right = st.columns([2, 1])
    with left:
        mode = st.segmented_control(
            "Matching mode",
            ["balanced", "strict", "intern_friendly"],
            default="balanced",
        )
    with right:
        st.write("")
        st.write("")
        match_clicked = st.button("Match all jobs", type="primary")

    if not match_clicked:
        return

    try:
        st.session_state["student_match_results"] = match_jobs_for_student(
            api_base,
            student["student_id"],
            {"mode": mode},
            token,
        )
        st.session_state["student_match_owner"] = student["student_id"]
    except (RuntimeError, ValueError) as exc:
        st.error(str(exc))


def _render_stored_results() -> None:
    results = st.session_state.get("student_match_results", [])
    if not results:
        st.info("Run matching to see job recommendations.")
        return

    st.caption(
        f"Matched {len(results)} jobs for "
        f"{st.session_state.get('student_match_owner', '-')}. Filters affect display only."
    )
    visible_results = _filter_results(results)
    _render_match_results(visible_results, len(results))


def _filter_results(results: list[dict]) -> list[dict]:
    filter_left, filter_mid, filter_right = st.columns(3)
    with filter_left:
        job_query = st.text_input("Query job title or ID", "")
    with filter_mid:
        min_score = st.slider("Display minimum score", 0, 100, 0, 5)
    with filter_right:
        status_options = sorted({result.get("job_status") or "-" for result in results})
        selected_statuses = st.multiselect(
            "Job status",
            status_options,
            default=status_options,
        )

    decision_options = sorted({result["decision"] for result in results})
    selected_decisions = st.multiselect(
        "Decision",
        decision_options,
        default=decision_options,
    )

    query = job_query.strip().lower()
    return [
        result
        for result in results
        if result["match_score"] >= min_score
        and result["decision"] in selected_decisions
        and (result.get("job_status") or "-") in selected_statuses
        and (
            not query
            or query in result["job_id"].lower()
            or query in result["job_title"].lower()
        )
    ]


def _render_match_results(visible_results: list[dict], total_count: int) -> None:
    st.caption(f"Showing {len(visible_results)} of {total_count} matched jobs.")
    rows = [
        {
            "Score": result["match_score"],
            "Job": result["job_title"],
            "Company": result.get("company_id") or "-",
            "Decision": result["decision"],
            "Top gaps": ", ".join(result.get("gaps", [])[:3]) or "-",
        }
        for result in visible_results
    ]
    st.dataframe(rows, width="stretch", hide_index=True)

    for result in visible_results:
        with st.expander(f"{result['match_score']} - {result['job_title']}"):
            st.write("Strengths:", ", ".join(result.get("strengths", [])) or "-")
            st.write("Gaps:", ", ".join(result.get("gaps", [])) or "-")
            if result.get("recommendations"):
                st.warning(" | ".join(result["recommendations"]))
            with st.popover("Breakdown"):
                st.json(result)
