from __future__ import annotations

import streamlit as st

from api_data import (
    delete_job,
    list_companies,
    list_jobs,
    match_candidates_for_job,
    render_api_controls,
    update_job_status,
)


st.set_page_config(page_title="Company", page_icon="CO", layout="wide")

st.title("Company")

api_base, token = render_api_controls()
try:
    companies = list_companies(api_base, token)
    jobs = list_jobs(api_base, token)
except RuntimeError as exc:
    st.error(str(exc))
    st.stop()
company_id = st.text_input("Company ID", "")
if company_id:
    companies = [company for company in companies if company["company_id"] == company_id.strip()]

jobs_by_company: dict[str, list[dict]] = {}
for job in jobs:
    jobs_by_company.setdefault(job["company_id"], []).append(job)

with st.expander("Manage JD by ID", expanded=True):
    job_id = st.text_input("JD ID")
    status = st.segmented_control("Status", ["open", "closed"], default="open")
    left, right = st.columns(2)
    with left:
        if st.button("Update status", type="primary"):
            try:
                st.json(update_job_status(api_base, job_id, status, token))
                st.rerun()
            except (RuntimeError, ValueError) as exc:
                st.error(str(exc))
    with right:
        if st.button("Delete JD"):
            try:
                delete_job(api_base, job_id, token)
                st.success("Deleted")
                st.rerun()
            except (RuntimeError, ValueError) as exc:
                st.error(str(exc))

with st.expander("Candidate matching rulebase", expanded=True):
    job_options = {
        f"{job['title']} - {job['job_id']} - {job.get('status', '-')}": job
        for job in jobs
    }
    if job_options:
        selected_job_label = st.selectbox("JD", list(job_options))
        mode = st.segmented_control(
            "Matching mode",
            ["balanced", "strict", "intern_friendly"],
            default="balanced",
        )
        config_left, config_mid, config_right = st.columns(3)
        with config_left:
            required_weight = st.slider("Required weight", 0.5, 1.0, 0.85, 0.05)
            optional_weight = round(1.0 - required_weight, 2)
            st.caption(f"Optional weight: {optional_weight:.2f}")
        with config_mid:
            minimum_confidence = st.slider("Minimum confidence", 0.0, 1.0, 0.65, 0.05)
            missing_policy = st.selectbox("Missing required policy", ["penalize", "reject"])
        with config_right:
            missing_penalty = st.slider("Missing required penalty", 0, 60, 25, 5)
            shortlist_threshold = st.slider("Shortlist threshold", 50, 100, 85, 5)

        if st.button("Rank all candidates", type="primary"):
            selected_job = job_options[selected_job_label]
            config = {
                "mode": mode,
                "required_skill_weight": required_weight,
                "optional_skill_weight": optional_weight,
                "minimum_confidence": minimum_confidence,
                "missing_required_policy": missing_policy,
                "missing_required_penalty": float(missing_penalty),
                "shortlist_threshold": float(shortlist_threshold),
            }
            try:
                st.session_state["company_match_results"] = match_candidates_for_job(
                    api_base,
                    selected_job["job_id"],
                    config,
                    token,
                )
                st.session_state["company_match_job"] = selected_job["job_id"]
            except (RuntimeError, ValueError) as exc:
                st.error(str(exc))

        results = st.session_state.get("company_match_results", [])
        if results:
            st.caption(
                f"Matched {len(results)} candidates for "
                f"{st.session_state.get('company_match_job', '-')}. "
                "Query below filters display only."
            )
            filter_left, filter_mid, filter_right = st.columns(3)
            with filter_left:
                candidate_query = st.text_input("Query student name or ID", "")
            with filter_mid:
                min_score = st.slider("Display minimum score", 0, 100, 0, 5)
            with filter_right:
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
                and (
                    not candidate_query
                    or candidate_query.lower() in result["student_id"].lower()
                    or candidate_query.lower() in (result.get("student_name") or "").lower()
                )
            ]
            st.caption(f"Showing {len(visible_results)} of {len(results)} matched candidates.")
            for result in visible_results:
                with st.container(border=True):
                    top_left, top_mid, top_right = st.columns([3, 1, 1])
                    with top_left:
                        st.write(result.get("student_name") or result["student_id"])
                        st.caption(result["student_id"])
                    with top_mid:
                        st.metric(result["label"], result["match_score"])
                    with top_right:
                        st.write(result["decision"])
                    matched = ", ".join(result["required_skills"]["matched"]) or "-"
                    st.write("Required matched:", matched)
                    missing = (
                        result["required_skills"]["missing"]
                        + result["required_skills"]["weak"]
                    )
                    st.write("Risks/gaps:", ", ".join(missing or result["risks"]) or "-")
                    if result["explanations"]:
                        st.info(" | ".join(result["explanations"]))
                    with st.popover("Full matching JSON"):
                        st.json(result)
    else:
        st.info("No JD available for matching.")

for company in companies:
    company_jobs = jobs_by_company.get(company["company_id"], [])
    with st.container(border=True):
        top_left, top_right = st.columns([3, 1])
        with top_left:
            st.subheader(company["name"])
            st.caption(f'{company["company_id"]} - {company.get("industry", "")}')
        with top_right:
            st.metric("JD", len(company_jobs))

        for job in company_jobs:
            row_left, row_mid, row_right = st.columns([4, 1, 2])
            with row_left:
                st.write(job["title"])
                st.caption(job["job_id"])
            with row_mid:
                st.write(job["status"])
            with row_right:
                next_status = "closed" if job["status"] == "open" else "open"
                if st.button(f"Set {next_status}", key=f"status-{job['job_id']}"):
                    update_job_status(api_base, job["job_id"], next_status, token)
                    st.rerun()
                if st.button("Delete", key=f"delete-{job['job_id']}"):
                    delete_job(api_base, job["job_id"], token)
                    st.rerun()
            with st.popover(f"JSON {job['job_id']}"):
                st.json(job)

if not companies:
    st.info("No company found.")
