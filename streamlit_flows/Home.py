from __future__ import annotations

import streamlit as st

from flow_log import render_log


st.set_page_config(page_title="C2 Flow Lab", page_icon="C2", layout="wide")

st.title("C2 Flow Lab")
st.caption("Manual backend flow checks before wiring features into the React UI.")

st.write("Use the pages in the sidebar to test one flow at a time.")

render_log()
