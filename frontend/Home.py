"""Streamlit home entrypoint."""

from __future__ import annotations

from dashboard import render_dashboard

try:
    import streamlit as st
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("Install streamlit to run the demo UI.") from exc


def main() -> None:
    st.set_page_config(page_title="Home", layout="wide")
    render_dashboard()


if __name__ == "__main__":
    main()
