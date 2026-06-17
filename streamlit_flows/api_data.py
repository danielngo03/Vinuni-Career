from __future__ import annotations

import re

import streamlit as st

from flow_client import delete_json, get_json, patch_json, post_json


DEFAULT_API_BASE = "http://127.0.0.1:8000"
AUTH_LOGIN_PATH = "/api/v1/auth/login"
AUTH_REGISTER_PATH = "/api/v1/auth/register"
AUTH_ME_PATH = "/api/v1/auth/me"
AUTH_DEMO_ACCOUNTS_PATH = "/api/v1/auth/demo-accounts"
ROLE_STUDENT = "student"
ROLE_COMPANY = "company"
ROLE_ADMIN = "admin"


def render_api_base_control() -> str:
    st.sidebar.header("FastAPI")
    api_base = st.sidebar.text_input(
        "API base",
        value=st.session_state.get("flow_api_base", DEFAULT_API_BASE),
    ).rstrip("/")
    st.session_state["flow_api_base"] = api_base
    return api_base


def render_api_controls(require_auth: bool = True) -> tuple[str, str | None]:
    api_base = render_api_base_control()

    st.sidebar.divider()
    render_sidebar_session(api_base)

    token = st.session_state.get("flow_api_token", "")
    if require_auth and not token:
        st.info("Login with a FastAPI account from the sidebar before using this flow.")
        st.stop()
    return api_base, token or None


def render_sidebar_session(api_base: str) -> None:
    st.sidebar.subheader("Session")
    user = st.session_state.get("flow_user")
    token = st.session_state.get("flow_api_token")

    if token and user:
        st.sidebar.success(f"Logged in as {user.get('email', 'user')}")
        st.sidebar.caption(f"{get_user_role(user).title()} - {user.get('full_name', '')}")
        if st.sidebar.button("Logout", width="stretch"):
            clear_session()
            st.rerun()
        return

    st.sidebar.caption("Not logged in.")


def render_login_form(api_base: str) -> None:
    with st.form("flow_login_form"):
        email = st.text_input("Account", placeholder="student_1 or company_1").strip()
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login", type="primary")

    if not submitted:
        return
    if not email or not password:
        st.sidebar.error("Account and password are required.")
        return

    try:
        login_response = login(api_base, email, password)
        access_token = login_response["access_token"]
        current_user = get_current_user(api_base, access_token)
        st.session_state["flow_api_token"] = access_token
        st.session_state["flow_user"] = current_user
        st.rerun()
    except (KeyError, RuntimeError) as exc:
        st.error(str(exc))


def clear_session() -> None:
    for key in (
        "flow_api_token",
        "flow_user",
        "student_match_results",
        "student_match_owner",
        "company_match_results",
        "company_match_job",
    ):
        st.session_state.pop(key, None)


def get_user_role(user: dict | None = None) -> str:
    account = (user or st.session_state.get("flow_user") or {}).get("email", "")
    if account.startswith("student_"):
        return ROLE_STUDENT
    if account.startswith("company_"):
        return ROLE_COMPANY
    return ROLE_ADMIN


def get_user_source_id(user: dict | None = None) -> str | None:
    full_name = (user or st.session_state.get("flow_user") or {}).get("full_name", "")
    match = re.search(r"\(([^()]+)\)\s*$", full_name)
    if match:
        return match.group(1)
    account = (user or st.session_state.get("flow_user") or {}).get("email", "")
    if account.startswith(("student_", "company_")):
        return account
    return None


def require_role(allowed_roles: set[str]) -> None:
    user = st.session_state.get("flow_user")
    if not user:
        st.error("Please login first.")
        st.stop()
    role = get_user_role(user)
    if role not in allowed_roles:
        st.error("You do not have permission to access this page.")
        st.stop()


def login(api_base: str, email: str, password: str) -> dict:
    return post_json(
        api_base,
        AUTH_LOGIN_PATH,
        {"email": email, "password": password},
    )


def register_account(api_base: str, account: str, password: str, full_name: str) -> dict:
    return post_json(
        api_base,
        AUTH_REGISTER_PATH,
        {"email": account, "password": password, "full_name": full_name},
    )


def get_current_user(api_base: str, token: str) -> dict:
    return get_json(api_base, AUTH_ME_PATH, token=token)


def create_demo_accounts(api_base: str) -> list[dict]:
    return post_json(api_base, AUTH_DEMO_ACCOUNTS_PATH, {})


def list_students(api_base: str, token: str | None = None) -> list[dict]:
    return get_json(api_base, "/students", token=token)


def list_demo_cvs(api_base: str, student_id: str, token: str | None = None) -> list[dict]:
    return get_json(api_base, f"/api/v1/cvs/demo/{student_id}", token=token)


def update_demo_student_profile(
    api_base: str,
    student_id: str,
    profile: dict,
    token: str | None = None,
) -> dict:
    return patch_json(
        api_base,
        f"/api/v1/students/demo/{student_id}/profile",
        profile,
        token=token,
    )


def parse_demo_cv(
    api_base: str,
    student_id: str,
    raw_text: str,
    token: str | None = None,
) -> dict:
    return post_json(
        api_base,
        f"/api/v1/cvs/demo/{student_id}/parse/raw",
        {"raw_text": raw_text, "student_id": student_id},
        token=token,
    )


def save_demo_cv(
    api_base: str,
    student_id: str,
    parsed_data: dict,
    raw_text: str,
    is_primary: bool,
    token: str | None = None,
) -> dict:
    return post_json(
        api_base,
        f"/api/v1/cvs/demo/{student_id}",
        {
            "student_id": student_id,
            "parsed_data": parsed_data,
            "raw_text": raw_text,
            "is_primary": is_primary,
        },
        token=token,
    )


def set_primary_demo_cv(
    api_base: str,
    student_id: str,
    cv_id: str,
    token: str | None = None,
) -> dict:
    return post_json(
        api_base,
        f"/api/v1/cvs/demo/{student_id}/{cv_id}/primary",
        {},
        token=token,
    )


def update_demo_cv(
    api_base: str,
    student_id: str,
    cv_id: str,
    parsed_data: dict,
    raw_text: str,
    is_primary: bool,
    token: str | None = None,
) -> dict:
    return patch_json(
        api_base,
        f"/api/v1/cvs/demo/{student_id}/{cv_id}",
        {
            "student_id": student_id,
            "parsed_data": parsed_data,
            "raw_text": raw_text,
            "is_primary": is_primary,
        },
        token=token,
    )


def delete_demo_cv(
    api_base: str,
    student_id: str,
    cv_id: str,
    token: str | None = None,
) -> dict:
    return delete_json(
        api_base,
        f"/api/v1/cvs/demo/{student_id}/{cv_id}",
        token=token,
    )


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
