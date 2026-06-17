from __future__ import annotations

from collections.abc import Callable

import streamlit as st

from api_data import (
    ROLE_ADMIN,
    ROLE_COMPANY,
    ROLE_STUDENT,
    create_demo_accounts,
    get_user_role,
    get_current_user,
    register_account,
    render_api_base_control,
    render_login_form,
    render_sidebar_session,
)
from flow_log import render_log
from views.cv_manager import render_cv_manager_page
from views.company import render_company_page
from views.student import render_student_page
from views.job_matching import render_job_matching_page


st.set_page_config(page_title="C2 Flow Lab", page_icon="C2", layout="wide")


def main() -> None:
    api_base = render_api_base_control()
    token = st.session_state.get("flow_api_token")
    user = st.session_state.get("flow_user")
    if token:
        try:
            user = get_current_user(api_base, token)
            st.session_state["flow_user"] = user
        except RuntimeError:
            pass

    st.sidebar.divider()
    render_sidebar_session(api_base)

    if not token or not user:
        render_login_page(api_base)
        return

    role = get_user_role(user)
    pages = allowed_pages(role)
    selected_page = st.sidebar.radio("Navigation", list(pages), label_visibility="collapsed")
    pages[selected_page](api_base, token)


def render_login_page(api_base: str) -> None:
    st.title("Login")
    st.caption("Sign in before accessing C2 Flow Lab.")

    left, right = st.columns([1, 1])
    with left:
        login_tab, register_tab = st.tabs(["Login", "Create account"])
        with login_tab:
            render_login_form(api_base)
        with register_tab:
            render_register_form(api_base)
    with right:
        st.subheader("Demo accounts")
        st.write("Create or refresh demo login accounts through FastAPI.")
        if st.button("Create demo accounts", type="secondary"):
            try:
                accounts = create_demo_accounts(api_base)
                st.success("Demo accounts are ready.")
                st.dataframe(accounts, width="stretch", hide_index=True)
            except RuntimeError as exc:
                st.error(str(exc))

    st.divider()
    render_log()


def allowed_pages(role: str) -> dict[str, Callable[[str, str], None]]:
    if role == ROLE_STUDENT:
        return {
            "Student Profile": render_student_page,
            "CVs": render_cv_manager_page,
            "Job Matching": render_job_matching_page,
        }
    if role == ROLE_COMPANY:
        return {"Company": render_company_page}
    if role == ROLE_ADMIN:
        return {
            "Student Profile": render_student_page,
            "CVs": render_cv_manager_page,
            "Job Matching": render_job_matching_page,
            "Company": render_company_page,
        }
    return {}


def render_register_form(api_base: str) -> None:
    with st.form("flow_register_form"):
        account_type = st.segmented_control("Account type", ["student", "company"], default="student")
        account = st.text_input("Account", placeholder="student_4 or company_3").strip()
        full_name = st.text_input("Display name", placeholder="Nguyen Van A").strip()
        password = st.text_input("Password", value="1", type="password")
        submitted = st.form_submit_button("Create account", type="primary")

    if not submitted:
        return
    if not account.startswith(f"{account_type}_"):
        st.error(f"Account must start with {account_type}_.")
        return
    if not full_name:
        st.error("Display name is required.")
        return
    try:
        register_account(api_base, account, password, full_name)
        st.success("Account created. You can login now.")
    except RuntimeError as exc:
        st.error(str(exc))


main()
