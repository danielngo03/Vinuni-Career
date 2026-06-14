"""Enterprise visual system helpers for the Streamlit frontend."""

from __future__ import annotations

from html import escape
from typing import Any

try:
    import streamlit as st
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("Install streamlit to run the demo UI.") from exc


def apply_enterprise_theme() -> None:
    """Inject global CSS for a polished enterprise application surface."""
    st.markdown(
        """
        <style>
        :root {
          --surface: #ffffff;
          --surface-subtle: #f6f8fb;
          --surface-strong: #eef3f8;
          --ink: #17202a;
          --muted: #667085;
          --line: #d8e0ea;
          --line-soft: #e8edf3;
          --accent: #0f766e;
          --accent-strong: #115e59;
          --accent-blue: #2563eb;
          --accent-amber: #b7791f;
          --danger: #b42318;
          --shadow: 0 18px 42px rgba(18, 38, 63, 0.08);
          --shadow-soft: 0 8px 24px rgba(18, 38, 63, 0.06);
          --radius: 8px;
        }

        html, body, [data-testid="stAppViewContainer"] {
          background:
            linear-gradient(180deg, rgba(246, 248, 251, 0.95), rgba(255, 255, 255, 0.98) 340px),
            #ffffff;
          color: var(--ink);
        }

        .main .block-container {
          max-width: 1240px;
          padding-top: 1.4rem;
          padding-bottom: 4rem;
        }

        [data-testid="stSidebar"] {
          background: #101820;
          border-right: 1px solid rgba(255, 255, 255, 0.08);
        }

        [data-testid="stSidebar"] * {
          color: rgba(255, 255, 255, 0.88);
        }

        [data-testid="stSidebar"] input {
          background: rgba(255, 255, 255, 0.08);
          border-color: rgba(255, 255, 255, 0.16);
          color: #ffffff;
        }

        h1, h2, h3 {
          letter-spacing: 0;
          color: var(--ink);
        }

        h1 {
          font-size: 2rem;
          line-height: 1.18;
        }

        h2 {
          font-size: 1.28rem;
        }

        h3 {
          font-size: 1.04rem;
        }

        .stButton > button,
        [data-testid="stFormSubmitButton"] button,
        .stDownloadButton button {
          border-radius: 8px;
          border: 1px solid var(--accent);
          background: var(--accent);
          color: #ffffff;
          font-weight: 650;
          letter-spacing: 0;
          box-shadow: var(--shadow-soft);
          transition: transform 160ms ease, box-shadow 160ms ease, background 160ms ease;
        }

        .stButton > button:hover,
        [data-testid="stFormSubmitButton"] button:hover,
        .stDownloadButton button:hover {
          background: var(--accent-strong);
          border-color: var(--accent-strong);
          transform: translateY(-1px);
          box-shadow: var(--shadow);
          color: #ffffff;
        }

        .stButton > button:disabled {
          background: #e6ebf1;
          border-color: #d6dee8;
          color: #8a94a6;
          box-shadow: none;
        }

        [data-testid="stTabs"] [role="tablist"] {
          gap: 0.25rem;
          border-bottom: 1px solid var(--line);
        }

        [data-testid="stTabs"] [role="tab"] {
          border-radius: 8px 8px 0 0;
          padding: 0.7rem 1rem;
          color: var(--muted);
          font-weight: 650;
        }

        [data-testid="stTabs"] [aria-selected="true"] {
          background: #ffffff;
          color: var(--accent);
          border-bottom: 2px solid var(--accent);
        }

        [data-testid="stMetric"] {
          background: var(--surface);
          border: 1px solid var(--line-soft);
          border-radius: var(--radius);
          padding: 1rem 1.05rem;
          box-shadow: var(--shadow-soft);
          min-height: 112px;
        }

        [data-testid="stMetricLabel"] {
          color: var(--muted);
          font-weight: 650;
        }

        [data-testid="stMetricValue"] {
          color: var(--ink);
          font-weight: 750;
        }

        .stDataFrame,
        [data-testid="stDataFrame"] {
          border-radius: var(--radius);
          overflow: hidden;
          border: 1px solid var(--line-soft);
          box-shadow: var(--shadow-soft);
        }

        [data-testid="stExpander"] {
          border: 1px solid var(--line-soft);
          border-radius: var(--radius);
          box-shadow: var(--shadow-soft);
          background: #ffffff;
        }

        [data-testid="stTextInput"] input,
        [data-testid="stTextArea"] textarea,
        [data-testid="stSelectbox"] div[data-baseweb="select"],
        [data-testid="stNumberInput"] input {
          border-radius: 8px;
        }

        .enterprise-hero {
          position: relative;
          display: grid;
          grid-template-columns: minmax(0, 1fr) auto;
          gap: 1.25rem;
          align-items: end;
          padding: 1.35rem 1.45rem;
          margin: 0 0 1.1rem 0;
          background:
            linear-gradient(135deg, rgba(255, 255, 255, 0.96), rgba(239, 246, 255, 0.86)),
            #ffffff;
          border: 1px solid var(--line-soft);
          border-radius: var(--radius);
          box-shadow: var(--shadow);
          overflow: hidden;
        }

        .enterprise-hero::before {
          content: "";
          position: absolute;
          inset: 0;
          border-top: 3px solid var(--accent);
          pointer-events: none;
        }

        .enterprise-hero h1 {
          margin: 0.2rem 0 0.35rem 0;
          font-size: clamp(1.7rem, 2vw, 2.2rem);
        }

        .enterprise-kicker {
          color: var(--accent);
          font-size: 0.78rem;
          font-weight: 800;
          letter-spacing: 0.08em;
          text-transform: uppercase;
        }

        .enterprise-subtitle {
          color: var(--muted);
          font-size: 0.98rem;
          max-width: 760px;
        }

        .enterprise-pill-row {
          display: flex;
          flex-wrap: wrap;
          gap: 0.45rem;
          justify-content: flex-end;
        }

        .enterprise-pill {
          display: inline-flex;
          align-items: center;
          gap: 0.4rem;
          padding: 0.38rem 0.62rem;
          border-radius: 999px;
          background: #f2f6fb;
          color: #344054;
          border: 1px solid var(--line-soft);
          font-size: 0.78rem;
          font-weight: 650;
          white-space: nowrap;
        }

        .enterprise-section {
          margin: 1.15rem 0 0.7rem 0;
          padding-top: 0.15rem;
        }

        .enterprise-section h2 {
          margin: 0 0 0.15rem 0;
        }

        .enterprise-section p {
          margin: 0;
          color: var(--muted);
        }

        .enterprise-card {
          background: var(--surface);
          border: 1px solid var(--line-soft);
          border-radius: var(--radius);
          box-shadow: var(--shadow-soft);
          padding: 1rem;
          margin: 0.45rem 0 0.75rem 0;
        }

        .workspace-card {
          display: block;
          min-height: 148px;
          padding: 1rem;
          border-radius: var(--radius);
          border: 1px solid var(--line-soft);
          background: #ffffff;
          box-shadow: var(--shadow-soft);
          transition: transform 160ms ease, box-shadow 160ms ease, border-color 160ms ease;
        }

        .workspace-card:hover {
          transform: translateY(-2px);
          box-shadow: var(--shadow);
          border-color: rgba(15, 118, 110, 0.42);
        }

        .workspace-card .eyebrow {
          color: var(--accent);
          font-size: 0.72rem;
          font-weight: 800;
          letter-spacing: 0.08em;
          text-transform: uppercase;
        }

        .workspace-card .title {
          margin-top: 0.45rem;
          font-size: 1.04rem;
          font-weight: 780;
          color: var(--ink);
        }

        .workspace-card .body {
          margin-top: 0.35rem;
          color: var(--muted);
          font-size: 0.9rem;
        }

        .status-strip {
          display: grid;
          grid-template-columns: repeat(4, minmax(0, 1fr));
          gap: 0.75rem;
          margin: 0.9rem 0 1rem 0;
        }

        .status-tile {
          background: #ffffff;
          border: 1px solid var(--line-soft);
          border-radius: var(--radius);
          padding: 0.9rem 1rem;
          box-shadow: var(--shadow-soft);
        }

        .status-tile .label {
          color: var(--muted);
          font-size: 0.78rem;
          font-weight: 700;
        }

        .status-tile .value {
          margin-top: 0.25rem;
          color: var(--ink);
          font-size: 1.55rem;
          font-weight: 820;
        }

        .status-tile .note {
          margin-top: 0.18rem;
          color: var(--accent);
          font-size: 0.78rem;
          font-weight: 650;
        }

        .login-shell {
          max-width: 560px;
          margin: 4vh auto 0 auto;
          padding: 1.35rem;
          background: #ffffff;
          border: 1px solid var(--line-soft);
          border-radius: var(--radius);
          box-shadow: var(--shadow);
        }

        .login-shell h1 {
          margin: 0 0 0.4rem 0;
        }

        .login-shell p {
          color: var(--muted);
          margin-bottom: 0.85rem;
        }

        @media (max-width: 820px) {
          .enterprise-hero {
            grid-template-columns: 1fr;
          }

          .enterprise-pill-row {
            justify-content: flex-start;
          }

          .status-strip {
            grid-template-columns: repeat(2, minmax(0, 1fr));
          }
        }

        @media (max-width: 520px) {
          .status-strip {
            grid-template-columns: 1fr;
          }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_page_header(title: str, subtitle: str, kicker: str | None = None, pills: list[str] | None = None) -> None:
    safe_kicker = escape(kicker or "Corhort")
    safe_title = escape(title)
    safe_subtitle = escape(subtitle)
    pill_html = "".join(f'<span class="enterprise-pill">{escape(item)}</span>' for item in (pills or []))
    st.markdown(
        f"""
        <section class="enterprise-hero">
          <div>
            <div class="enterprise-kicker">{safe_kicker}</div>
            <h1>{safe_title}</h1>
            <div class="enterprise-subtitle">{safe_subtitle}</div>
          </div>
          <div class="enterprise-pill-row">{pill_html}</div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_section_header(title: str, subtitle: str | None = None) -> None:
    subtitle_html = f"<p>{escape(subtitle)}</p>" if subtitle else ""
    st.markdown(
        f"""
        <div class="enterprise-section">
          <h2>{escape(title)}</h2>
          {subtitle_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_status_strip(items: list[dict[str, Any]]) -> None:
    tiles = []
    for item in items:
        label = escape(str(item.get("label", "")))
        value = escape(str(item.get("value", "")))
        note = escape(str(item.get("note", "")))
        tiles.append(
            f'<div class="status-tile"><div class="label">{label}</div>'
            f'<div class="value">{value}</div><div class="note">{note}</div></div>'
        )
    st.markdown(f'<div class="status-strip">{"".join(tiles)}</div>', unsafe_allow_html=True)


def render_workspace_card(eyebrow: str, title: str, body: str) -> None:
    st.markdown(
        f"""
        <div class="workspace-card">
          <div class="eyebrow">{escape(eyebrow)}</div>
          <div class="title">{escape(title)}</div>
          <div class="body">{escape(body)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
