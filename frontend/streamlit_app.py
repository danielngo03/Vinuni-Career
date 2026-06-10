"""Streamlit home page for the Corhort demo UI."""

from __future__ import annotations

from shared import render_parser_status_sidebar, job_repo

try:
    import streamlit as st
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("Install streamlit to run the demo UI.") from exc


st.set_page_config(page_title="Corhort Matching Demo", layout="wide")
render_parser_status_sidebar()

st.title("Corhort Matching Demo")
st.caption("Use the sidebar navigation to work with the JD matching workspace.")

col_jobs, col_open = st.columns(2)
jobs = job_repo.list()
open_jobs = [job for job in jobs if job.status == "open"]

col_jobs.metric("Saved jobs", len(jobs))
col_open.metric("Open jobs", len(open_jobs))

st.subheader("Pages")
st.page_link("pages/1_JD_Workspace.py", label="JD Workspace")

st.info(
    "The backend now supports multiple agent-style routers. This UI mirrors that split: "
    "JD work is kept on its own page so future CV work can be added separately when needed."
)
