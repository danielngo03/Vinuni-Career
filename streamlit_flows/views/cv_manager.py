from __future__ import annotations

import streamlit as st

from api_data import (
    ROLE_ADMIN,
    ROLE_STUDENT,
    delete_demo_cv,
    get_user_role,
    get_user_source_id,
    list_demo_cvs,
    list_students,
    parse_demo_cv,
    require_role,
    save_demo_cv,
    set_primary_demo_cv,
    update_demo_cv,
)


PARSED_CV_KEY = "parsed_cv_{student_id}"
PARSED_CV_RAW_KEY = "parsed_cv_raw_{student_id}"


def render_cv_manager_page(api_base: str, token: str) -> None:
    """Render the CV manager page only.

    This page focuses on CV parsing and saved CV management. The final profile
    display lives in student_profile.py, and matching lives in job_matching.py.
    """
    require_role({ROLE_STUDENT, ROLE_ADMIN})

    st.title("CV Management")
    student_id = _resolve_student_id(api_base, token)
    if not student_id:
        st.info("Select a student before managing CVs.")
        return

    st.caption(f"Managing CVs for {student_id}")

    parse_tab, saved_tab = st.tabs(["Parse new CV", "Saved CVs"])
    with parse_tab:
        _render_cv_parser(api_base, token, student_id)
    with saved_tab:
        _render_saved_cvs(api_base, token, student_id)


def _resolve_student_id(api_base: str, token: str) -> str | None:
    role = get_user_role()
    if role == ROLE_STUDENT:
        return get_user_source_id()

    try:
        students = list_students(api_base, token)
    except RuntimeError as exc:
        st.error(str(exc))
        return None

    if not students:
        return None

    options = {
        f"{student.get('name', student['student_id'])} - {student['student_id']}": student[
            "student_id"
        ]
        for student in students
    }
    return options[st.selectbox("Student", list(options))]


def _render_cv_parser(api_base: str, token: str, student_id: str) -> None:
    st.subheader("Parse new CV")
    st.caption("Paste a CV, parse it, review the structured preview, then save it.")

    target_position = st.text_input(
        "CV position",
        placeholder="Backend Developer, Data Analyst, Frontend Intern...",
        key=f"cv_position_new_{student_id}",
    )
    raw_text = st.text_area(
        "CV text",
        height=260,
        placeholder="Paste the CV content here...",
        key=f"cv_raw_text_{student_id}",
    )

    parse_left, parse_right = st.columns([1, 1])
    with parse_left:
        parse_clicked = st.button("Parse CV", type="primary", disabled=not raw_text.strip())
    with parse_right:
        save_primary = st.checkbox("Set as primary CV", value=True)

    if parse_clicked:
        _parse_and_store_cv(api_base, token, student_id, raw_text, target_position)

    parsed = st.session_state.get(PARSED_CV_KEY.format(student_id=student_id))
    if not parsed:
        st.info("Parsed CV preview will appear here.")
        return

    parsed_for_save = {
        **parsed,
        "target_position": target_position.strip() or _cv_position(parsed),
    }
    _render_parsed_preview(parsed_for_save)
    _render_save_parsed_cv_button(api_base, token, student_id, raw_text, parsed_for_save, save_primary)


def _parse_and_store_cv(
    api_base: str,
    token: str,
    student_id: str,
    raw_text: str,
    target_position: str,
) -> None:
    try:
        parsed = parse_demo_cv(api_base, student_id, raw_text, token)
        if target_position.strip():
            parsed["target_position"] = target_position.strip()
        st.session_state[PARSED_CV_KEY.format(student_id=student_id)] = parsed
        st.session_state[PARSED_CV_RAW_KEY.format(student_id=student_id)] = raw_text
    except RuntimeError as exc:
        st.error(str(exc))


def _render_save_parsed_cv_button(
    api_base: str,
    token: str,
    student_id: str,
    raw_text: str,
    parsed_for_save: dict,
    save_primary: bool,
) -> None:
    if not st.button("Save parsed CV", type="primary"):
        return

    try:
        save_demo_cv(
            api_base,
            student_id,
            parsed_for_save,
            st.session_state.get(PARSED_CV_RAW_KEY.format(student_id=student_id), raw_text),
            save_primary,
            token,
        )
        st.success("CV saved. Student Profile will use this CV if it is primary.")
        st.rerun()
    except RuntimeError as exc:
        st.error(str(exc))


def _render_parsed_preview(parsed: dict) -> None:
    st.subheader("Parsed CV preview")
    with st.container(border=True):
        top_left, top_right = st.columns([3, 1])
        with top_left:
            st.write(f"**{_cv_position(parsed)}**")
            if parsed.get("student_id"):
                st.caption(parsed["student_id"])
        with top_right:
            with st.popover("Raw parse"):
                st.json(parsed)

        _render_preview_highlights(parsed)

        with st.expander("Full parsed details", expanded=False):
            work_experience = parsed.get("work_experience", [])
            if work_experience:
                st.write("Work experience")
                st.dataframe(_work_experience_rows(work_experience), width="stretch", hide_index=True)

            education = parsed.get("education", [])
            if education:
                st.write("Education")
                st.dataframe(_education_rows(education), width="stretch", hide_index=True)

            skills = parsed.get("skills", {})
            if skills:
                st.write("Skills")
                st.dataframe(_skill_rows(skills), width="stretch", hide_index=True)


def _render_preview_highlights(parsed: dict) -> None:
    work_experience = parsed.get("work_experience", [])
    education = parsed.get("education", [])
    skills = parsed.get("skills", {})

    left, middle, right = st.columns(3)
    with left:
        st.write("**Top experience**")
        item = _top_scored_item(work_experience)
        if item:
            st.write(item.get("title") or "Experience")
            st.caption(_compact_detail(item.get("company"), item.get("duration"), _score_label(item.get("score"))))
        else:
            st.caption("No experience found")

    with middle:
        st.write("**Top education**")
        item = _top_scored_item(education)
        if item:
            st.write(item.get("degree") or "Education")
            st.caption(_compact_detail(item.get("institution"), item.get("year"), _score_label(item.get("score"))))
        else:
            st.caption("No education found")

    with right:
        st.write("**Top skills**")
        top_skills = _top_skills(skills, 3)
        if top_skills:
            for skill, detail in top_skills:
                st.caption(f"{skill.title()} · {_score_label(detail.get('score'))}")
        else:
            st.caption("No skills found")


def _render_saved_cvs(api_base: str, token: str, student_id: str) -> None:
    st.subheader("Saved CVs")
    try:
        cvs = list_demo_cvs(api_base, student_id, token)
    except RuntimeError as exc:
        st.error(str(exc))
        return

    if not cvs:
        st.info("No CV saved yet.")
        return

    for cv in cvs:
        _render_saved_cv_card(api_base, token, student_id, cv)


def _render_saved_cv_card(api_base: str, token: str, student_id: str, cv: dict) -> None:
    parsed = cv.get("parsed_data", {}) or {}
    with st.container(border=True):
        top_left, top_mid, top_right, action_col = st.columns([3, 1, 1, 1])
        with top_left:
            st.write(f"**{_cv_position(parsed)}**")
            st.caption(cv.get("created_at", ""))
        with top_mid:
            st.metric("Primary", "Yes" if cv.get("is_primary") else "No")
        with top_right:
            _render_set_primary_button(api_base, token, student_id, cv)
        with action_col:
            _render_delete_cv_button(api_base, token, student_id, cv)

        _render_saved_cv_summary(parsed)
        _render_saved_cv_editor(api_base, token, student_id, cv, parsed)

        with st.popover("Raw details"):
            st.json(cv)


def _render_set_primary_button(api_base: str, token: str, student_id: str, cv: dict) -> None:
    if not st.button(
        "Set primary",
        key=f"primary_{cv['id']}",
        disabled=bool(cv.get("is_primary")),
    ):
        return

    try:
        set_primary_demo_cv(api_base, student_id, cv["id"], token)
        st.success("Primary CV updated.")
        st.rerun()
    except RuntimeError as exc:
        st.error(str(exc))


def _render_delete_cv_button(api_base: str, token: str, student_id: str, cv: dict) -> None:
    if not st.button(
        "Delete",
        key=f"delete_{cv['id']}",
        disabled=bool(cv.get("is_primary")),
    ):
        return

    try:
        delete_demo_cv(api_base, student_id, cv["id"], token)
        st.success("CV deleted.")
        st.rerun()
    except RuntimeError as exc:
        st.error(str(exc))


def _render_saved_cv_summary(parsed: dict) -> None:
    skills = parsed.get("skills", {})
    strongest_skill = _top_skills(skills, 1)
    work_count = len(parsed.get("work_experience", []) or [])
    education_count = len(parsed.get("education", []) or [])

    left, middle, right = st.columns(3)
    with left:
        st.caption(f"Work items: {work_count}")
    with middle:
        st.caption(f"Education items: {education_count}")
    with right:
        if strongest_skill:
            skill, detail = strongest_skill[0]
            st.caption(f"Top skill: {skill.title()} {_score_label(detail.get('score'))}")
        else:
            st.caption("Top skill: -")


def _render_saved_cv_editor(
    api_base: str,
    token: str,
    student_id: str,
    cv: dict,
    parsed: dict,
) -> None:
    with st.expander("Edit CV position and raw detail", expanded=False):
        with st.form(f"edit_cv_{cv['id']}"):
            edited_position = st.text_input(
                "CV position",
                value=_cv_position(parsed),
                key=f"cv_position_{cv['id']}",
            )
            edited_raw_text = st.text_area(
                "Raw detail",
                value=cv.get("raw_text", ""),
                height=240,
                key=f"cv_raw_{cv['id']}",
            )
            submitted = st.form_submit_button("Save and reparse", type="primary")

    if not submitted:
        return

    try:
        reparsed = parse_demo_cv(api_base, student_id, edited_raw_text, token)
        reparsed["target_position"] = edited_position.strip() or _cv_position(reparsed)
        update_demo_cv(
            api_base,
            student_id,
            cv["id"],
            reparsed,
            edited_raw_text,
            bool(cv.get("is_primary")),
            token,
        )
        st.success("CV updated.")
        st.rerun()
    except RuntimeError as exc:
        st.error(str(exc))


def _work_experience_rows(work_experience: list[dict]) -> list[dict]:
    return [
        {
            "Score": _score_label(item.get("score")),
            "Title": item.get("title") or "-",
            "Company": item.get("company") or "-",
            "Duration": item.get("duration") or "-",
            "Summary": item.get("summary") or "-",
            "Reason": item.get("score_reason") or "-",
        }
        for item in work_experience
    ]


def _education_rows(education: list[dict]) -> list[dict]:
    return [
        {
            "Score": _score_label(item.get("score")),
            "Degree": item.get("degree") or "-",
            "Institution": item.get("institution") or "-",
            "Year": item.get("year") or "-",
            "Summary": item.get("summary") or "-",
            "Reason": item.get("score_reason") or "-",
        }
        for item in education
    ]


def _skill_rows(skills: dict) -> list[dict]:
    return [
        {
            "Skill": skill.title(),
            "Score": _score_label(detail.get("score")),
            "Confidence": f"{float(detail.get('confidence', 0)):.0%}",
            "Evidence": (detail.get("evidence") or ["-"])[0],
        }
        for skill, detail in _top_skills(skills, len(skills))
    ]


def _cv_position(parsed: dict) -> str:
    return (
        parsed.get("target_position")
        or parsed.get("position")
        or parsed.get("role")
        or "Untitled CV"
    )


def _score_label(value: object) -> str:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return "-"
    return f"{score:.1f}/10"


def _top_scored_item(items: list[dict]) -> dict | None:
    if not items:
        return None
    return max(items, key=lambda item: float(item.get("score", 0) or 0))


def _top_skills(skills: dict, limit: int) -> list[tuple[str, dict]]:
    return sorted(
        skills.items(),
        key=lambda item: item[1].get("score", 0) if isinstance(item[1], dict) else 0,
        reverse=True,
    )[:limit]


def _compact_detail(*values: object) -> str:
    return " | ".join(str(value) for value in values if value)
