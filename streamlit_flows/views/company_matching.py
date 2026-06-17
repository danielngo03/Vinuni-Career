from __future__ import annotations

import streamlit as st

from api_data import match_candidates_for_job


def _job_options(jobs: list[dict]) -> dict[str, dict]:
    return {
        f"{job.get('title', 'Untitled JD')} - {job.get('job_id', '-')} - {job.get('status', '-')}": job
        for job in jobs
    }


def _score(result: dict, *keys: str, default: float = 0) -> float:
    for key in keys:
        value = result.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    return float(default)


def _list_text(items: list | None) -> str:
    if not items:
        return "-"
    return ", ".join(str(item) for item in items if item)


def _build_config(
    mode: str,
    required_weight: float,
    minimum_confidence: float,
    missing_policy: str,
    missing_penalty: int,
    shortlist_threshold: int,
    skill_weight: int,
    experience_weight: int,
    education_weight: int,
) -> dict:
    optional_weight = round(1.0 - required_weight, 2)
    return {
        "mode": mode,
        "required_skill_weight": required_weight,
        "optional_skill_weight": optional_weight,
        "minimum_confidence": minimum_confidence,
        "missing_required_policy": missing_policy,
        "missing_required_penalty": float(missing_penalty),
        "shortlist_threshold": float(shortlist_threshold),
        "score_weights": {
            "skills": float(skill_weight) / 100,
            "experience": float(experience_weight) / 100,
            "education": float(education_weight) / 100,
        },
    }


def render_candidate_matching(api_base: str, token: str, jobs: list[dict]) -> None:
    st.subheader("Candidate Matching")
    st.caption("Rank candidates with skill-first rule-based matching.")

    job_options = _job_options(jobs)
    if not job_options:
        st.info("No JD available for matching.")
        return

    selected_job_label = st.selectbox("Select JD", list(job_options), key="matching_jd")
    selected_job = job_options[selected_job_label]

    mode = st.segmented_control(
        "Matching mode",
        ["balanced", "strict", "intern_friendly"],
        default="balanced",
        key="matching_mode",
    )

    st.markdown("**Score weights**")
    weight_left, weight_mid, weight_right = st.columns(3)
    with weight_left:
        skill_weight = st.slider("Skills", 50, 100, 75, 5, key="skill_weight")
    with weight_mid:
        experience_weight = st.slider("Experience", 0, 40, 15, 5, key="experience_weight")
    with weight_right:
        education_weight = st.slider("Education", 0, 30, 10, 5, key="education_weight")

    total_weight = skill_weight + experience_weight + education_weight
    if total_weight != 100:
        st.warning(f"Current total weight is {total_weight}%. Recommended total is 100%.")

    with st.expander("Advanced matching settings", expanded=False):
        config_left, config_mid, config_right = st.columns(3)
        with config_left:
            required_weight = st.slider("Required skill weight", 0.5, 1.0, 0.85, 0.05)
            optional_weight = round(1.0 - required_weight, 2)
            st.caption(f"Optional skill weight: {optional_weight:.2f}")
        with config_mid:
            minimum_confidence = st.slider("Minimum confidence", 0.0, 1.0, 0.65, 0.05)
            missing_policy = st.selectbox("Missing required policy", ["penalize", "reject"])
        with config_right:
            missing_penalty = st.slider("Missing required penalty", 0, 60, 25, 5)
            shortlist_threshold = st.slider("Shortlist threshold", 50, 100, 85, 5)

    if st.button("Rank all candidates", type="primary"):
        if total_weight != 100:
            st.error("Please adjust score weights so the total equals 100%.")
            return

        config = _build_config(
            mode=mode,
            required_weight=required_weight,
            minimum_confidence=minimum_confidence,
            missing_policy=missing_policy,
            missing_penalty=missing_penalty,
            shortlist_threshold=shortlist_threshold,
            skill_weight=skill_weight,
            experience_weight=experience_weight,
            education_weight=education_weight,
        )
        try:
            st.session_state["company_match_results"] = match_candidates_for_job(
                api_base,
                selected_job["job_id"],
                config,
                token,
            )
            st.session_state["company_match_job"] = selected_job["job_id"]
        except (RuntimeError, ValueError) as exc:
            st.error(str(exc))

    _render_results()


def _render_results() -> None:
    results = st.session_state.get("company_match_results", [])
    if not results:
        return

    st.divider()
    st.caption(
        f"Matched {len(results)} candidates for "
        f"{st.session_state.get('company_match_job', '-')}. "
        "Filters below only affect the display."
    )

    filter_left, filter_mid, filter_right = st.columns(3)
    with filter_left:
        candidate_query = st.text_input("Search student name or ID", "")
    with filter_mid:
        min_score = st.slider("Minimum overall score", 0, 100, 0, 5)
    with filter_right:
        decision_options = sorted({result.get("decision", "-") for result in results})
        selected_decisions = st.multiselect(
            "Decision",
            decision_options,
            default=decision_options,
        )

    visible_results = []
    for result in results:
        overall_score = _score(result, "overall_score", "match_score")
        student_id = str(result.get("student_id", ""))
        student_name = str(result.get("student_name") or "")
        decision = result.get("decision", "-")
        query_match = (
            not candidate_query
            or candidate_query.lower() in student_id.lower()
            or candidate_query.lower() in student_name.lower()
        )
        if overall_score >= min_score and decision in selected_decisions and query_match:
            visible_results.append(result)

    st.caption(f"Showing {len(visible_results)} of {len(results)} matched candidates.")

    for result in visible_results:
        _render_candidate_card(result)


def _render_candidate_card(result: dict) -> None:
    overall_score = _score(result, "overall_score", "match_score")
    skill_score = _score(result, "skill_score", "skills_score", default=overall_score)
    experience_score = _score(result, "experience_score", default=0)
    education_score = _score(result, "education_score", default=0)

    with st.container(border=True):
        top_left, top_mid, top_right = st.columns([3, 1, 1])
        with top_left:
            st.markdown(f"**{result.get('student_name') or result.get('student_id', '-') }**")
            st.caption(result.get("student_id", ""))
        with top_mid:
            label = result.get("label", "Overall Fit")
            st.metric(label, round(overall_score, 1))
        with top_right:
            st.write(result.get("decision", "-"))

        score_left, score_mid, score_right = st.columns(3)
        with score_left:
            st.metric("Skills", round(skill_score, 1))
        with score_mid:
            st.metric("Experience", round(experience_score, 1))
        with score_right:
            st.metric("Education", round(education_score, 1))

        required_skills = result.get("required_skills", {}) or {}
        matched = required_skills.get("matched", [])
        missing = required_skills.get("missing", []) + required_skills.get("weak", [])
        risks = result.get("risks", [])

        st.write("Required matched:", _list_text(matched))
        st.write("Risks/gaps:", _list_text(missing or risks))

        explanations = result.get("explanations", []) or []
        if explanations:
            st.info(" | ".join(str(item) for item in explanations))

        with st.popover("Full matching JSON"):
            st.json(result)
