from __future__ import annotations

import streamlit as st

from flow_client import delete_json, get_json, post_json


DEFAULT_API_BASE = "http://127.0.0.1:8000"


def render_api_controls() -> tuple[str, str | None]:
    st.sidebar.header("FastAPI")
    api_base = st.sidebar.text_input(
        "API base",
        value=st.session_state.get("flow_api_base", DEFAULT_API_BASE),
    ).rstrip("/")
    token = st.sidebar.text_input(
        "Bearer token",
        value=st.session_state.get("flow_api_token", ""),
        type="password",
    ).strip()
    st.session_state["flow_api_base"] = api_base
    st.session_state["flow_api_token"] = token
    return api_base, token or None


def list_students(api_base: str, token: str | None = None) -> list[dict]:
    return get_json(api_base, "/students", token=token)


def list_jobs(api_base: str, token: str | None = None) -> list[dict]:
    return get_json(api_base, "/jobs", token=token)


def list_companies(api_base: str, token: str | None = None) -> list[dict]:
    return get_json(api_base, "/api/v1/companies", token=token)


def update_job_status(
    api_base: str,
    job_id: str,
    status: str,
    token: str | None = None,
) -> dict:
    endpoint = f"/jobs/{job_id}/{'open' if status == 'open' else 'close'}"
    return post_json(api_base, endpoint, {}, token=token)


def delete_job(api_base: str, job_id: str, token: str | None = None) -> dict:
    return delete_json(api_base, f"/jobs/{job_id}", token=token)


def match_jobs_for_student(
    api_base: str,
    student_id: str,
    config: dict | None = None,
    token: str | None = None,
) -> list[dict]:
    students = list_students(api_base, token)
    student = _find_record(students, "student_id", student_id)
    jobs = list_jobs(api_base, token)
    response = post_json(
        api_base,
        "/api/v1/matching/student/jobs",
        {"student": student, "jobs": jobs, "config": config or {}},
        token=token,
    )
    return response["results"]


def match_candidates_for_job(
    api_base: str,
    job_id: str,
    config: dict | None = None,
    token: str | None = None,
) -> list[dict]:
    jobs = list_jobs(api_base, token)
    job = _find_record(jobs, "job_id", job_id)
    students = list_students(api_base, token)
    response = post_json(
        api_base,
        "/api/v1/matching/company/candidates",
        {"job": job, "students": students, "config": config or {}},
        token=token,
    )
    return response["results"]


def _find_record(records: list[dict], id_field: str, record_id: str) -> dict:
    clean_id = record_id.strip()
    if not clean_id:
        raise ValueError("Missing ID")
    for record in records:
        if record.get(id_field) == clean_id:
            return record
    raise ValueError(f"{clean_id} not found")
