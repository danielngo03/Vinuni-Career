"""Streamlit home page for the Corhort demo UI."""

from __future__ import annotations

from demo_auth import get_current_role, get_current_user_id, render_login, render_logout_sidebar
from shared import job_repo, render_parser_status_sidebar

try:
    import streamlit as st
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("Install streamlit to run the demo UI.") from exc


st.set_page_config(page_title="Corhort Matching Demo", layout="wide")
user = st.session_state.get("auth_user")
if not isinstance(user, dict):
    render_login()
    st.stop()

render_parser_status_sidebar()
render_logout_sidebar(user)
role = get_current_role()
user_id = get_current_user_id()

st.title("Corhort Matching Demo")
st.caption("Use the sidebar navigation to work with JD matching and CV analysis.")

col_jobs, col_open = st.columns(2)
jobs = [job for job in job_repo.list() if role == "enterprise" and job.company_id == user_id]
open_jobs = [job for job in jobs if job.status == "open"]

col_jobs.metric("Saved jobs", len(jobs))
col_open.metric("Open jobs", len(open_jobs))

st.subheader("Pages")
if role == "enterprise":
    st.page_link("pages/1_JD_Workspace.py", label="JD Workspace")
else:
    st.page_link("pages/2_CV_Analysis.py", label="CV Analysis")
