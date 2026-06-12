"""Streamlit demo login helpers."""

from __future__ import annotations

from typing import Any

try:
    import streamlit as st
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("Install streamlit to run the demo UI.") from exc


ACCOUNT_TYPE_LABELS = {
    "enterprise": "Enterprise / Company",
    "student": "Student",
    "teacher": "Teacher / School",
}

ACCOUNT_ID_LABELS = {
    "enterprise": "Company ID",
    "student": "Student ID",
    "teacher": "Teacher ID",
}

ACCOUNT_ID_DEFAULTS = {
    "enterprise": "company_demo",
    "student": "mock-student-ai-001",
    "teacher": "teacher_demo",
}


def get_current_user() -> dict[str, str] | None:
    user = st.session_state.get("auth_user")
    return user if isinstance(user, dict) else None


def get_current_account_id() -> str:
    user = get_current_user()
    return str(user.get("user_id", "")) if user else ""


def get_current_role() -> str:
    user = get_current_user()
    return str(user.get("role", "")) if user else ""


def require_login(*allowed_roles: str) -> dict[str, str]:
    user = get_current_user()
    if user is None:
        render_login()
        st.stop()

    if allowed_roles and user.get("role") not in allowed_roles:
        st.warning("This account does not have access to this page.")
        render_logout_sidebar(user)
        st.stop()

    render_logout_sidebar(user)
    return user


def render_login() -> None:
    st.title("Login")
    with st.form("login-form"):
        account_label = st.selectbox("Account type", list(ACCOUNT_TYPE_LABELS.values()))
        role = next(key for key, label in ACCOUNT_TYPE_LABELS.items() if label == account_label)
        user_id = st.text_input(
            ACCOUNT_ID_LABELS.get(role, "Account ID"),
            value=ACCOUNT_ID_DEFAULTS.get(role, ""),
        )
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")

    if submitted:
        clean_user_id = user_id.strip()
        if not clean_user_id:
            st.error("Account ID is required.")
            return
        if not password.strip():
            st.error("Password is required.")
            return
        st.session_state["auth_user"] = {
            "role": role,
            "user_id": clean_user_id,
        }
        st.rerun()


def render_logout_sidebar(user: dict[str, Any]) -> None:
    st.sidebar.header("Account")
    role = str(user.get("role", ""))
    st.sidebar.text_input("Account type", value=ACCOUNT_TYPE_LABELS.get(role, role), disabled=True)
    st.sidebar.text_input(ACCOUNT_ID_LABELS.get(role, "Account ID"), value=str(user.get("user_id", "")), disabled=True)
    if st.sidebar.button("Logout"):
        for key in ["auth_user", "draft_job", "draft_student", "parser_metadata", "cv_parser_metadata"]:
            st.session_state.pop(key, None)
        st.rerun()
