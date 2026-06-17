from __future__ import annotations

import streamlit as st

from api_data import list_students, match_jobs_for_student, render_api_controls


st.set_page_config(page_title="Student", page_icon="ST", layout="wide")

st.title("Student")

api_base, token = render_api_controls()
try:
    students = list_students(api_base, token)
except RuntimeError as exc:
    st.error(str(exc))
    st.stop()
query = st.text_input("Student ID", "")
if query:
    students = [student for student in students if student["student_id"] == query.strip()]

cols = st.columns(3)
for index, student in enumerate(students):
    with cols[index % 3]:
        with st.container(border=True):
            st.subheader(student["name"])
            st.caption(student["student_id"])
            skills = student.get("skills", {})
            st.metric("Skills", len(skills))
            for skill, detail in skills.items():
                st.write(f"{skill}: {detail.get('score', 0)}")
            with st.popover("JSON"):
                st.json(student)

st.divider()
st.subheader("Job matching")

student_options = {
    f"{student.get('name', student['student_id'])} - {student['student_id']}": student
    for student in students
}
if student_options:
    selected_label = st.selectbox("Student", list(student_options))
    mode = st.segmented_control(
        "Matching mode",
        ["balanced", "strict", "intern_friendly"],
        default="balanced",
    )
    if st.button("Match all jobs", type="primary"):
        selected_student = student_options[selected_label]
        try:
            st.session_state["student_match_results"] = match_jobs_for_student(
                api_base,
                selected_student["student_id"],
                {"mode": mode},
                token,
            )
            st.session_state["student_match_owner"] = selected_student["student_id"]
        except (RuntimeError, ValueError) as exc:
            st.error(str(exc))

    results = st.session_state.get("student_match_results", [])
    if results:
        st.caption(
            f"Matched {len(results)} jobs for "
            f"{st.session_state.get('student_match_owner', '-')}. Query below filters display only."
        )
        filter_left, filter_mid, filter_right = st.columns(3)
        with filter_left:
            job_query = st.text_input("Query job title or ID", "")
        with filter_mid:
            min_score = st.slider("Display minimum score", 0, 100, 0, 5)
        with filter_right:
            status_options = sorted({result.get("job_status") or "-" for result in results})
            selected_statuses = st.multiselect("Job status", status_options, default=status_options)

        decision_options = sorted({result["decision"] for result in results})
        selected_decisions = st.multiselect(
            "Decision",
            decision_options,
            default=decision_options,
        )
        visible_results = [
            result
            for result in results
            if result["match_score"] >= min_score
            and result["decision"] in selected_decisions
            and (result.get("job_status") or "-") in selected_statuses
            and (
                not job_query
                or job_query.lower() in result["job_id"].lower()
                or job_query.lower() in result["job_title"].lower()
            )
        ]
        st.caption(f"Showing {len(visible_results)} of {len(results)} matched jobs.")
        for result in visible_results:
            with st.container(border=True):
                top_left, top_right = st.columns([3, 1])
                with top_left:
                    st.write(result["job_title"])
                    st.caption(
                        f"{result['job_id']} - {result.get('company_id') or '-'} - "
                        f"{result.get('job_status') or '-'}"
                    )
                with top_right:
                    st.metric(result["label"], result["match_score"])
                st.write("Strengths:", ", ".join(result["strengths"]) or "-")
                st.write("Gaps:", ", ".join(result["gaps"]) or "-")
                if result["recommendations"]:
                    st.warning(" | ".join(result["recommendations"]))
                with st.popover("Breakdown"):
                    st.json(result)

if not students:
    st.info("No student found.")
