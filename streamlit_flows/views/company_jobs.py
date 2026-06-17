from __future__ import annotations

import streamlit as st

from api_data import delete_job, update_job_status


def _job_options(jobs: list[dict]) -> dict[str, dict]:
    return {
        f"{job.get('title', 'Untitled JD')} - {job.get('job_id', '-')} - {job.get('status', '-')}": job
        for job in jobs
    }


def render_jd_management(api_base: str, token: str, jobs: list[dict]) -> None:
    st.subheader("JD Management")
    st.caption("Update JD status or remove a JD from the demo dataset.")

    job_options = _job_options(jobs)
    if not job_options:
        st.info("No JD available to manage.")
        return

    selected_job_label = st.selectbox("Select JD", list(job_options), key="manage_jd")
    selected_job = job_options[selected_job_label]

    detail_left, detail_right = st.columns([3, 1])
    with detail_left:
        st.markdown(f"**{selected_job.get('title', 'Untitled JD')}**")
        st.caption(selected_job.get("job_id", ""))
    with detail_right:
        st.metric("Current status", selected_job.get("status", "-"))

    st.divider()
    st.markdown("**Change status**")
    current_status = selected_job.get("status", "open")
    default_status_index = 0 if current_status == "open" else 1
    status = st.segmented_control(
        "New status",
        ["open", "closed"],
        default=["open", "closed"][default_status_index],
        key="manage_jd_status",
    )

    if st.button("Update status", type="primary", disabled=selected_job is None):
        try:
            result = update_job_status(api_base, selected_job["job_id"], status, token)
            st.success("JD status updated.")
            with st.popover("Updated JSON"):
                st.json(result)
            st.rerun()
        except (RuntimeError, ValueError) as exc:
            st.error(str(exc))

    with st.expander("Danger zone", expanded=False):
        st.warning("Deleting a JD removes it from this demo app.")
        confirm_delete = st.checkbox(
            "I understand and want to delete this JD",
            key=f"confirm-delete-{selected_job.get('job_id', '-')}",
        )
        if st.button("Delete JD", disabled=not confirm_delete):
            try:
                delete_job(api_base, selected_job["job_id"], token)
                st.success("JD deleted.")
                st.rerun()
            except (RuntimeError, ValueError) as exc:
                st.error(str(exc))

    with st.expander("JD JSON", expanded=False):
        st.json(selected_job)
