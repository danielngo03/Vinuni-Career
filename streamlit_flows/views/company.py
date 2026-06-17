from __future__ import annotations

import streamlit as st

from api_data import (
    ROLE_ADMIN,
    ROLE_COMPANY,
    get_user_role,
    get_user_source_id,
    list_companies,
    list_jobs,
    require_role,
)

try:
    from .company_overview import render_company_overview
    from .company_jobs import render_jd_management
    from .company_matching import render_candidate_matching
except ImportError:
    from company_overview import render_company_overview
    from company_jobs import render_jd_management
    from company_matching import render_candidate_matching


def _group_jobs_by_company(jobs: list[dict]) -> dict[str, list[dict]]:
    jobs_by_company: dict[str, list[dict]] = {}
    for job in jobs:
        company_id = str(job.get("company_id", ""))
        jobs_by_company.setdefault(company_id, []).append(job)
    return jobs_by_company


def _filter_company_scope(companies: list[dict], jobs: list[dict]) -> tuple[list[dict], list[dict]]:
    role = get_user_role()
    source_id = get_user_source_id()

    if role != ROLE_COMPANY:
        return companies, jobs

    if not source_id:
        st.error("This account is not linked to a demo company profile.")
        st.stop()

    scoped_companies = [
        company for company in companies if company.get("company_id") == source_id
    ]
    scoped_jobs = [job for job in jobs if job.get("company_id") == source_id]
    return scoped_companies, scoped_jobs


def render_company_page(api_base: str, token: str) -> None:
    require_role({ROLE_COMPANY, ROLE_ADMIN})

    st.title("Company")
    st.caption("Manage job descriptions and review rule-based candidate matches.")

    try:
        companies = list_companies(api_base, token)
        jobs = list_jobs(api_base, token)
    except RuntimeError as exc:
        st.error(str(exc))
        st.stop()

    companies, jobs = _filter_company_scope(companies, jobs)
    jobs_by_company = _group_jobs_by_company(jobs)

    tab_overview, tab_jobs, tab_matching = st.tabs(
        ["Overview", "JD Management", "Candidate Matching"]
    )

    with tab_overview:
        render_company_overview(companies, jobs_by_company)

    with tab_jobs:
        render_jd_management(api_base, token, jobs)

    with tab_matching:
        render_candidate_matching(api_base, token, jobs)
