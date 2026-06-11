"""Streamlit demo login helpers."""

from __future__ import annotations

from typing import Any

try:
    import streamlit as st
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("Install streamlit to run the demo UI.") from exc


def get_current_user() -> dict[str, str] | None:
    user = st.session_state.get("auth_user")
    return user if isinstance(user, dict) else None


def get_current_user_id() -> str:
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
        role = st.selectbox("Account type", ["enterprise", "student"])
        user_id = st.text_input("User ID")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")

    if submitted:
        clean_user_id = user_id.strip()
        if not clean_user_id:
            st.error("User ID is required.")
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
    st.sidebar.write(str(user.get("user_id", "")))
    st.sidebar.caption(str(user.get("role", "")))
    if st.sidebar.button("Logout"):
        for key in ["auth_user", "draft_job", "draft_student", "parser_metadata", "cv_parser_metadata"]:
            st.session_state.pop(key, None)
        st.rerun()
