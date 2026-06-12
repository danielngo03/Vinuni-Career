"""Teacher page for building RAG-ready YouTube transcript data."""

from __future__ import annotations

from pathlib import Path

from demo_auth import get_current_user_id, require_login
from shared import render_parser_status_sidebar

try:
    import streamlit as st
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("Install streamlit to run the demo UI.") from exc

from backend.src.services.youtube_rag_pipeline import DEFAULT_OUTPUT_DIR, PipelineConfig, detect_source_type, run_youtube_rag_pipeline


st.set_page_config(page_title="Teacher RAG Pipeline", layout="wide")
require_login("teacher")
render_parser_status_sidebar()
teacher_user_id = get_current_user_id()

st.page_link("pages/0_Home.py", label="Back to Teacher Dashboard")
st.title("Teacher RAG Pipeline")

with st.form("youtube-rag-pipeline-form"):
    source_url = st.text_input("YouTube video or playlist URL")
    category = st.text_input("Category", value="Uncategorized")
    course_title = st.text_input("Course title")
    output_dir = st.text_input("Output directory", value=str(DEFAULT_OUTPUT_DIR))
    languages = st.multiselect("Subtitle language priority", ["vi", "en", "en-US", "en-GB"], default=["vi", "en"])
    col_chunk, col_overlap, col_sleep = st.columns(3)
    chunk_size_words = col_chunk.number_input("Chunk size words", min_value=100, max_value=1200, value=420, step=20)
    overlap_words = col_overlap.number_input("Overlap words", min_value=0, max_value=500, value=100, step=10)
    sleep_seconds = col_sleep.number_input("Sleep seconds", min_value=0.0, max_value=30.0, value=2.0, step=0.5)
    col_keep, col_force = st.columns(2)
    keep_vtt = col_keep.checkbox("Keep VTT files", value=False)
    force = col_force.checkbox("Force rebuild", value=False)
    submitted = st.form_submit_button("Crawl and build RAG data")

if source_url.strip():
    st.caption(f"Detected source type: {detect_source_type(source_url)}")

if submitted:
    if not source_url.strip():
        st.error("YouTube URL is required.")
    elif not languages:
        st.error("Select at least one subtitle language.")
    elif overlap_words >= chunk_size_words:
        st.error("Overlap must be smaller than chunk size.")
    else:
        try:
            with st.spinner("Running transcript pipeline..."):
                report = run_youtube_rag_pipeline(
                    PipelineConfig(
                        source_url=source_url.strip(),
                        output_dir=Path(output_dir),
                        teacher_user_id=teacher_user_id,
                        category=category.strip() or "Uncategorized",
                        course_title=course_title.strip() or None,
                        languages=tuple(languages),
                        chunk_size_words=int(chunk_size_words),
                        overlap_words=int(overlap_words),
                        keep_vtt=keep_vtt,
                        force=force,
                        sleep_seconds=float(sleep_seconds),
                    )
                )
            st.success("Pipeline completed.")
            col_found, col_saved, col_failed, col_chunks = st.columns(4)
            col_found.metric("Videos found", report.get("videos_found", 0))
            col_saved.metric("Videos saved", report.get("videos_saved", 0))
            col_failed.metric("Videos failed", report.get("videos_failed", 0))
            col_chunks.metric("Chunks created", report.get("chunks_created", 0))
            st.subheader("Outputs")
            st.dataframe(
                [
                    {"name": "chunks", "path": report.get("chunks_output", "")},
                    {"name": "report", "path": report.get("report_output", "")},
                ],
                hide_index=True,
                width="stretch",
            )
            st.subheader("Videos")
            st.dataframe(report.get("videos", []), hide_index=True, width="stretch")
        except Exception as exc:
            st.error(str(exc))
