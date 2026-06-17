from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import streamlit as st


MAX_TEXT_LENGTH = 180
MAX_LIST_ITEMS = 6
LOG_DIR = Path(__file__).resolve().parent / "logs"
LOG_FILE = LOG_DIR / "flow_events.jsonl"


def add_log(event: str, **details: Any) -> None:
    timestamp = datetime.now()
    record = {
        "timestamp": timestamp.isoformat(timespec="seconds"),
        "page": _current_page(),
        "event": event,
        "details": compact(details),
    }
    append_file_log(record)

    logs = st.session_state.setdefault("flow_logs", [])
    logs.insert(
        0,
        {
            "time": timestamp.strftime("%H:%M:%S"),
            "event": event,
            "details": record["details"],
        },
    )
    del logs[30:]


def append_file_log(record: dict[str, Any]) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")


def render_log() -> None:
    with st.sidebar:
        st.divider()
        st.subheader("Flow log")
        st.caption(f"Saved to `{LOG_FILE}`")
        if st.button("Clear screen log"):
            st.session_state["flow_logs"] = []
            st.rerun()

        logs = st.session_state.get("flow_logs", [])
        if not logs:
            st.caption("No activity yet.")
            return

        for item in logs:
            with st.expander(f"{item['time']} - {item['event']}", expanded=False):
                st.json(item["details"])


def compact(value: Any) -> Any:
    if isinstance(value, str):
        return shorten(value)
    if isinstance(value, bytes):
        return f"<{len(value)} bytes>"
    if isinstance(value, dict):
        return {str(key): compact(item) for key, item in value.items()}
    if isinstance(value, list):
        items = [compact(item) for item in value[:MAX_LIST_ITEMS]]
        if len(value) > MAX_LIST_ITEMS:
            items.append("...")
        return items
    return value


def shorten(text: str) -> str:
    clean = " ".join(text.split())
    if len(clean) <= MAX_TEXT_LENGTH:
        return clean
    return f"{clean[:MAX_TEXT_LENGTH].rstrip()}..."


def _current_page() -> str:
    try:
        return Path(st.context.page_script_path).name
    except Exception:
        return "unknown"
