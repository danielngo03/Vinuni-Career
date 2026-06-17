from __future__ import annotations

import streamlit as st


def _job_status_counts(jobs: list[dict]) -> tuple[int, int, int]:
    total = len(jobs)
    open_count = sum(1 for job in jobs if job.get("status") == "open")
    closed_count = sum(1 for job in jobs if job.get("status") == "closed")
    return total, open_count, closed_count


def render_company_overview(
    companies: list[dict],
    jobs_by_company: dict[str, list[dict]],
) -> None:
    if not companies:
        st.info("No company found.")
        return

    for company in companies:
        company_id = str(company.get("company_id", ""))
        company_jobs = jobs_by_company.get(company_id, [])
        total_jobs, open_jobs, closed_jobs = _job_status_counts(company_jobs)

        with st.container(border=True):
            header_left, header_right = st.columns([3, 1])
            with header_left:
                st.subheader(company.get("name", "Untitled company"))
                st.caption(f"{company_id} - {company.get('industry', '')}")
            with header_right:
                st.metric("Total JD", total_jobs)

            metric_left, metric_mid, metric_right = st.columns(3)
            with metric_left:
                st.metric("Open", open_jobs)
            with metric_mid:
                st.metric("Closed", closed_jobs)
            with metric_right:
                open_rate = round((open_jobs / total_jobs) * 100) if total_jobs else 0
                st.metric("Open rate", f"{open_rate}%")

            st.divider()
            st.markdown("**Recent job descriptions**")

            if not company_jobs:
                st.info("No JD available for this company.")
                continue

            for job in company_jobs:
                row_left, row_mid, row_right = st.columns([4, 1, 2])
                with row_left:
                    st.write(job.get("title", "Untitled JD"))
                    st.caption(job.get("job_id", ""))
                with row_mid:
                    status = job.get("status", "-")
                    st.write(status)
                with row_right:
                    with st.popover("View JSON"):
                        st.json(job)
