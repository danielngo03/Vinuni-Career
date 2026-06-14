"""Streamlit home entrypoint."""

from __future__ import annotations

from dashboard import render_dashboard
from theme import apply_enterprise_theme

try:
    import streamlit as st
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("Install streamlit to run the demo UI.") from exc


def main() -> None:
    st.set_page_config(page_title="Corhort", layout="wide")
    apply_enterprise_theme()
    render_dashboard()


if __name__ == "__main__":
    main()
