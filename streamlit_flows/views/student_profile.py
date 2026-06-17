from __future__ import annotations

import streamlit as st

from api_data import (
    ROLE_ADMIN,
    ROLE_STUDENT,
    get_user_role,
    get_user_source_id,
    list_students,
    require_role,
    update_demo_student_profile,
)


def render_student_profile_page(api_base: str, token: str) -> None:
    """Render the student-facing profile page only.

    This page is intentionally focused on the final Student Profile view/edit flow.
    Job matching lives in job_matching.py and CV parsing lives in cv_manager.py.
    """
    require_role({ROLE_STUDENT, ROLE_ADMIN})

    students = _load_visible_students(api_base, token)
    st.title("Student Profile")

    if not students:
        if get_user_role() == ROLE_STUDENT:
            st.info("No student profile yet. Open the CVs page and save a primary CV first.")
        else:
            st.info("No student found.")
        return

    selected_student = _select_student(students, get_user_role())
    _render_profile(api_base, token, selected_student)


def _load_visible_students(api_base: str, token: str) -> list[dict]:
    try:
        students = list_students(api_base, token)
    except RuntimeError as exc:
        st.error(str(exc))
        st.stop()

    role = get_user_role()
    source_id = get_user_source_id()
    if role != ROLE_STUDENT:
        return students

    if not source_id:
        st.error("This account is not linked to a demo student profile.")
        st.stop()
    return [student for student in students if student.get("student_id") == source_id]


def _select_student(students: list[dict], role: str) -> dict:
    if role == ROLE_STUDENT or len(students) == 1:
        return students[0]
    options = {_student_label(student): student for student in students}
    return options[st.selectbox("Profile", list(options))]


def _student_label(student: dict) -> str:
    return f"{student.get('name', student['student_id'])} - {student['student_id']}"


def _render_profile(api_base: str, token: str, student: dict) -> None:
    highlights = _profile_highlights(student)

    _render_profile_header(student)
    _render_profile_hero(student, highlights)
    st.divider()

    personal_tab, details_tab, edit_tab = st.tabs(
        ["Personal information", "Full CV details", "Edit display"]
    )
    with personal_tab:
        _render_personal_information_view(student)
    with details_tab:
        _render_full_cv_details(student)
    with edit_tab:
        _render_profile_editor(api_base, token, student, highlights)


def _render_profile_header(student: dict) -> None:
    profile = student.get("profile", {}) or {}
    display_name = profile.get("full_name") or student.get("name") or "Unnamed student"
    target_position = student.get("target_position", "")

    st.markdown(f"# {display_name}")
    if target_position:
        st.subheader(target_position)
    st.caption(f"Student ID: {student.get('student_id', '-')}")


def _render_profile_hero(student: dict, highlights: dict) -> None:
    left, middle, right = st.columns(3)
    with left:
        _render_selected_work_experience(student.get("work_experience", []), highlights)
    with middle:
        _render_selected_education(student.get("education", []), highlights)
    with right:
        _render_selected_skills(student.get("skills", {}), highlights)


def _render_personal_information_view(student: dict) -> None:
    profile = student.get("profile", {}) or {}
    rows = [
        ("Full name", profile.get("full_name") or student.get("name") or "-"),
        ("Age", profile.get("age") or "-"),
        ("Phone", profile.get("phone") or "-"),
        ("Email", profile.get("email") or "-"),
        ("Location", profile.get("location") or "-"),
        ("University", profile.get("university") or "-"),
        ("Major", profile.get("major") or "-"),
        ("Graduation year", profile.get("graduation_year") or "-"),
        ("LinkedIn", profile.get("linkedin") or "-"),
        ("GitHub", profile.get("github") or "-"),
        ("Portfolio", profile.get("portfolio") or "-"),
    ]
    st.dataframe(
        [{"Field": field, "Value": value} for field, value in rows],
        width="stretch",
        hide_index=True,
    )
    if profile.get("bio"):
        st.write("Bio")
        st.write(profile["bio"])

    with st.popover("Raw profile data"):
        st.json(student)


def _render_profile_editor(
    api_base: str,
    token: str,
    student: dict,
    highlights: dict,
) -> None:
    st.subheader("Displayed highlights")
    _render_highlight_editor(api_base, token, student, highlights)
    st.divider()
    st.subheader("Personal information")
    _render_personal_information_editor(api_base, token, student)


def _render_personal_information_editor(api_base: str, token: str, student: dict) -> None:
    profile = student.get("profile", {}) or {}
    with st.form(f"profile_form_{student['student_id']}"):
        left, right = st.columns(2)
        with left:
            full_name = st.text_input(
                "Full name",
                value=profile.get("full_name") or student.get("name") or "",
            )
            age = st.text_input("Age", value=profile.get("age", ""))
            phone = st.text_input("Phone", value=profile.get("phone", ""))
            email = st.text_input("Email", value=profile.get("email", ""))
            location = st.text_input("Location", value=profile.get("location", ""))
        with right:
            university = st.text_input("University", value=profile.get("university", ""))
            major = st.text_input("Major", value=profile.get("major", ""))
            graduation_year = st.text_input(
                "Graduation year",
                value=profile.get("graduation_year", ""),
            )
            linkedin = st.text_input("LinkedIn", value=profile.get("linkedin", ""))
            github = st.text_input("GitHub", value=profile.get("github", ""))
            portfolio = st.text_input("Portfolio", value=profile.get("portfolio", ""))
        bio = st.text_area("Bio", value=profile.get("bio", ""), height=100)
        submitted = st.form_submit_button("Save profile", type="primary")

    if not submitted:
        return

    payload = {
        "full_name": full_name,
        "age": age,
        "phone": phone,
        "email": email,
        "location": location,
        "university": university,
        "major": major,
        "graduation_year": graduation_year,
        "linkedin": linkedin,
        "github": github,
        "portfolio": portfolio,
        "bio": bio,
    }
    try:
        update_demo_student_profile(api_base, student["student_id"], payload, token)
        st.success("Profile updated.")
        st.rerun()
    except RuntimeError as exc:
        st.error(str(exc))


def _profile_highlights(student: dict) -> dict:
    highlights = student.get("profile_highlights") or {}
    work_experience = student.get("work_experience", [])
    education = student.get("education", [])
    skills = student.get("skills", {})
    return {
        "work_experience_indexes": _valid_indexes(
            highlights.get("work_experience_indexes"),
            len(work_experience),
            fallback=_top_item_indexes(work_experience, 2),
        ),
        "education_indexes": _valid_indexes(
            highlights.get("education_indexes"),
            len(education),
            fallback=_top_item_indexes(education, 1),
        ),
        "skill_names": _valid_skill_names(
            highlights.get("skill_names"),
            skills,
            fallback=_top_skill_names(skills, 3),
        ),
    }


def _render_selected_work_experience(work_experience: list[dict], highlights: dict) -> None:
    st.subheader("Top experience")
    selected = _items_by_indexes(work_experience, highlights["work_experience_indexes"])
    if not selected:
        st.info("No highlighted work experience selected.")
        return
    for item in selected:
        st.write(f"**{item.get('title') or 'Experience'}**")
        detail = " | ".join(
            value
            for value in (item.get("company"), item.get("duration"), _score_label(item.get("score")))
            if value
        )
        if detail:
            st.caption(detail)
        if item.get("summary"):
            st.write(item["summary"])


def _render_selected_education(education: list[dict], highlights: dict) -> None:
    st.subheader("Top education")
    selected = _items_by_indexes(education, highlights["education_indexes"])
    if not selected:
        st.info("No highlighted education selected.")
        return
    for item in selected:
        st.write(f"**{item.get('degree') or 'Education'}**")
        detail = " | ".join(
            value
            for value in (item.get("institution"), item.get("year"), _score_label(item.get("score")))
            if value
        )
        if detail:
            st.caption(detail)
        if item.get("summary"):
            st.write(item["summary"])


def _render_selected_skills(skills: dict, highlights: dict) -> None:
    st.subheader("Top skills")
    selected = [skill for skill in highlights["skill_names"] if skill in skills]
    if not selected:
        st.info("No highlighted skills selected.")
        return
    rows = []
    for skill in selected:
        detail = skills.get(skill, {})
        evidence = detail.get("evidence", [])
        rows.append(
            {
                "Skill": skill.title(),
                "Score": _score_label(detail.get("score")),
                "Evidence": evidence[0] if evidence else "-",
            }
        )
    st.dataframe(rows, width="stretch", hide_index=True)


def _render_highlight_editor(
    api_base: str,
    token: str,
    student: dict,
    highlights: dict,
) -> None:
    work_experience = student.get("work_experience", [])
    education = student.get("education", [])
    skills = student.get("skills", {})
    work_options = {_work_option_label(item, index): index for index, item in enumerate(work_experience)}
    education_options = {
        _education_option_label(item, index): index for index, item in enumerate(education)
    }
    skill_options = {_skill_option_label(skill, detail): skill for skill, detail in skills.items()}

    with st.form(f"highlight_form_{student['student_id']}"):
        selected_work_labels = st.multiselect(
            "Top experience",
            list(work_options),
            default=_labels_for_indexes(work_options, highlights["work_experience_indexes"]),
        )
        selected_education_labels = st.multiselect(
            "Top education",
            list(education_options),
            default=_labels_for_indexes(education_options, highlights["education_indexes"]),
        )
        selected_skill_labels = st.multiselect(
            "Top skills",
            list(skill_options),
            default=_labels_for_values(skill_options, highlights["skill_names"]),
        )
        submitted = st.form_submit_button("Save displayed profile", type="primary")

    if not submitted:
        return

    payload = {
        "profile_highlights": {
            "work_experience_indexes": [work_options[label] for label in selected_work_labels][:2],
            "education_indexes": [education_options[label] for label in selected_education_labels][:1],
            "skill_names": [skill_options[label] for label in selected_skill_labels][:3],
        }
    }
    try:
        update_demo_student_profile(api_base, student["student_id"], payload, token)
        st.success("Displayed profile updated.")
        st.rerun()
    except RuntimeError as exc:
        st.error(str(exc))


def _render_full_cv_details(student: dict) -> None:
    _render_work_experience(student.get("work_experience", []))
    st.divider()
    _render_education(student.get("education", []))
    st.divider()
    st.subheader("Skill profile")
    st.caption("Based on the primary CV.")
    skills = student.get("skills", {})
    if not skills:
        st.info("No skills found in this profile.")
    else:
        st.dataframe(_skill_rows(skills), width="stretch", hide_index=True)


def _render_work_experience(work_experience: list[dict]) -> None:
    st.subheader("Work experience")
    if not work_experience:
        st.info("No work experience extracted from the primary CV yet.")
        return

    rows = []
    for item in work_experience:
        rows.append(
            {
                "Score": _score_label(item.get("score")),
                "Title": item.get("title") or "-",
                "Company": item.get("company") or "-",
                "Duration": item.get("duration") or "-",
                "Summary": item.get("summary") or "-",
                "Reason": item.get("score_reason") or "-",
            }
        )
    st.dataframe(rows, width="stretch", hide_index=True)


def _render_education(education: list[dict]) -> None:
    st.subheader("Education")
    if not education:
        st.info("No education extracted from the primary CV yet.")
        return

    rows = []
    for item in education:
        rows.append(
            {
                "Score": _score_label(item.get("score")),
                "Degree": item.get("degree") or "-",
                "Institution": item.get("institution") or "-",
                "Year": item.get("year") or "-",
                "Summary": item.get("summary") or "-",
                "Reason": item.get("score_reason") or "-",
            }
        )
    st.dataframe(rows, width="stretch", hide_index=True)


def _skill_rows(skills: dict) -> list[dict]:
    rows = []
    for skill, detail in sorted(
        skills.items(),
        key=lambda item: item[1].get("score", 0),
        reverse=True,
    ):
        score = float(detail.get("score", 0))
        evidence = detail.get("evidence", [])
        rows.append(
            {
                "Skill": skill.title(),
                "Score": f"{score:.1f}/10",
                "Level": _skill_level(score),
                "Confidence": f"{float(detail.get('confidence', 0)):.0%}",
                "Evidence": evidence[0] if evidence else "-",
            }
        )
    return rows


def _score_label(value: object) -> str:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return "-"
    return f"{score:.1f}/10"


def _valid_indexes(value: object, count: int, *, fallback: list[int]) -> list[int]:
    if not isinstance(value, list):
        return fallback
    indexes = []
    for item in value:
        try:
            index = int(item)
        except (TypeError, ValueError):
            continue
        if 0 <= index < count and index not in indexes:
            indexes.append(index)
    return indexes or fallback


def _valid_skill_names(value: object, skills: dict, *, fallback: list[str]) -> list[str]:
    if not isinstance(value, list):
        return fallback
    normalized = {skill.lower(): skill for skill in skills}
    selected = []
    for item in value:
        key = str(item).strip().lower()
        if key in normalized and normalized[key] not in selected:
            selected.append(normalized[key])
    return selected or fallback


def _top_item_indexes(items: list[dict], limit: int) -> list[int]:
    scored = [
        (index, float(item.get("score", 0)) if isinstance(item, dict) else 0)
        for index, item in enumerate(items)
    ]
    return [index for index, _ in sorted(scored, key=lambda item: item[1], reverse=True)[:limit]]


def _top_skill_names(skills: dict, limit: int) -> list[str]:
    return [
        skill
        for skill, _ in sorted(
            skills.items(),
            key=lambda item: item[1].get("score", 0) if isinstance(item[1], dict) else 0,
            reverse=True,
        )[:limit]
    ]


def _items_by_indexes(items: list[dict], indexes: list[int]) -> list[dict]:
    return [items[index] for index in indexes if 0 <= index < len(items)]


def _work_option_label(item: dict, index: int) -> str:
    title = item.get("title") or f"Experience {index + 1}"
    company = item.get("company") or "No company"
    return f"{index + 1}. {title} - {company} - {_score_label(item.get('score'))}"


def _education_option_label(item: dict, index: int) -> str:
    degree = item.get("degree") or f"Education {index + 1}"
    institution = item.get("institution") or "No institution"
    return f"{index + 1}. {degree} - {institution} - {_score_label(item.get('score'))}"


def _skill_option_label(skill: str, detail: dict) -> str:
    return f"{skill.title()} - {_score_label(detail.get('score'))}"


def _labels_for_indexes(options: dict[str, int], indexes: list[int]) -> list[str]:
    wanted = set(indexes)
    return [label for label, index in options.items() if index in wanted]


def _labels_for_values(options: dict[str, str], values: list[str]) -> list[str]:
    wanted = set(values)
    return [label for label, value in options.items() if value in wanted]


def _skill_level(score: float) -> str:
    if score >= 8:
        return "Strong"
    if score >= 7:
        return "Ready"
    if score >= 6:
        return "Developing"
    return "Needs focus"
