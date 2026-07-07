"""Regression tests for the v10 SIX-criteria HR CV-JD scorer (``app.ai.cv.job_fit``).

Locks in the owner's authoritative rubric (2026-07-07): the score is built from
exactly six recruiter criteria — skills, experience, scope, credentials,
soft_skills, trajectory — with skills+experience as the survival core. The old
standalone ``domain`` band was removed as redundant with skills; field fit now
lives inside experience (title/field relevance) and credentials (major
alignment). Pure functions, no DB, no LLM.
"""

from __future__ import annotations

from app.ai.cv import job_fit


def _cv(
    *,
    skills: str = "",
    experience: str = "",
    education: str = "",
    objective: str = "",
    cv_id: str = "cv",
    language: str = "en",
) -> job_fit.CvInput:
    sections: list[dict] = []
    if skills:
        sections.append(
            {"section_type": "skills", "title": "Skills", "content": {"items": [{"text": skills}]}}
        )
    if experience:
        sections.append(
            {
                "section_type": "experience",
                "title": "Experience",
                "content": {"items": [{"text": experience}]},
            }
        )
    if education:
        sections.append(
            {
                "section_type": "education",
                "title": "Education",
                "content": {"items": [{"text": education}]},
            }
        )
    if objective:
        sections.append(
            {
                "section_type": "summary",
                "title": "Summary",
                "content": {"items": [{"text": objective}]},
            }
        )
    return job_fit.CvInput(
        cv_id=cv_id, title="CV", language=language, sections=sections, last_updated_days=3
    )


def _score(job: dict, cv: job_fit.CvInput) -> job_fit.CvFit:
    return job_fit.evaluate(job, [cv], stale_days=120).results[0]


# --------------------------------------------------------------------------- #
# Band SHAPE: exactly the six criteria, no legacy keys.                       #
# --------------------------------------------------------------------------- #


def test_bands_expose_exactly_six_criteria() -> None:
    job = {
        "id": "j",
        "title": "Engineer",
        "description": "",
        "experience_mode": "no_requirement",
        "required_skills": ["Python"],
        "preferred_skills": [],
    }
    bands = _score(job, _cv(skills="Python")).bands.as_dict()
    assert set(bands) == {
        "skills",
        "experience",
        "scope",
        "credentials",
        "soft_skills",
        "trajectory",
    }


# --------------------------------------------------------------------------- #
# 1. Skills — contextual depth: a skill proven in experience beats one listed. #
# --------------------------------------------------------------------------- #


def test_skill_in_experience_scores_higher_than_only_listed() -> None:
    job = {
        "id": "j",
        "title": "Backend Engineer",
        "description": "",
        "experience_mode": "no_requirement",
        "required_skills": ["Python", "PostgreSQL"],
        "preferred_skills": [],
    }
    listed_only = _score(job, _cv(skills="Python, PostgreSQL"))
    in_context = _score(
        job,
        _cv(
            skills="Python, PostgreSQL",
            experience="Built and shipped production services in Python backed by PostgreSQL.",
        ),
    )
    # Same coverage, but the contextual-depth multiplier lifts the proven CV.
    assert in_context.bands.skills > listed_only.bands.skills


# --------------------------------------------------------------------------- #
# 3. Scope — leadership + metrics beat plain participation.                    #
# --------------------------------------------------------------------------- #


def test_leadership_and_metrics_beat_participation_on_scope() -> None:
    job = {
        "id": "j",
        "title": "Senior Engineer",
        "description": "",
        "experience_mode": "no_requirement",
        "seniority_level": "senior",
        "required_skills": ["Python"],
        "preferred_skills": [],
    }
    leader = _score(
        job,
        _cv(
            skills="Python",
            experience="Led a team of 6; reduced infra cost by 30% and scaled to 2M users.",
        ),
    )
    helper = _score(
        job,
        _cv(
            skills="Python",
            experience="Participated in the project and assisted the team with tasks.",
        ),
    )
    assert leader.bands.scope > helper.bands.scope + 10


# --------------------------------------------------------------------------- #
# 5. Soft skills — JD-requested soft skills, credited for context.            #
# --------------------------------------------------------------------------- #


def test_soft_skills_require_jd_signal_and_reward_context() -> None:
    job = {
        "id": "j",
        "title": "Consultant",
        "description": "Strong communication and teamwork; must present to clients.",
        "experience_mode": "no_requirement",
        "required_skills": ["Excel"],
        "preferred_skills": [],
    }
    proven = _score(
        job,
        _cv(
            skills="Excel",
            experience="Presented solutions to the board; led teamwork across 3 teams.",
        ),
    )
    absent = _score(job, _cv(skills="Excel", experience="Did data entry in Excel."))
    assert proven.bands.soft_skills > absent.bands.soft_skills

    # When the JD asks for no soft skills, the band is neutral (never punitive).
    job_no_soft = {
        "id": "j",
        "title": "Data Clerk",
        "description": "Enter numbers.",
        "experience_mode": "no_requirement",
        "required_skills": ["Excel"],
        "preferred_skills": [],
    }
    neutral = _score(job_no_soft, _cv(skills="Excel", experience="Data entry."))
    assert neutral.bands.soft_skills == 70


# --------------------------------------------------------------------------- #
# 6. Trajectory — job-hopping is a risk; stable tenure is not.                #
# --------------------------------------------------------------------------- #


def test_job_hopping_lowers_trajectory() -> None:
    job = {
        "id": "j",
        "title": "Engineer",
        "description": "",
        "experience_mode": "no_requirement",
        "required_skills": ["Python"],
        "preferred_skills": [],
    }
    hopper = _score(
        job,
        _cv(
            skills="Python",
            experience="A 01/2022 - 04/2022. B 05/2022 - 08/2022. C 09/2022 - 12/2022.",
        ),
    )
    stable = _score(
        job,
        _cv(
            skills="Python",
            experience="Company A 01/2019 - 12/2021. Company B 01/2022 - present.",
        ),
    )
    assert stable.bands.trajectory > hopper.bands.trajectory + 10

    # A student with no dated history is neutral, never penalised as a hopper.
    fresh = _score(job, _cv(skills="Python", experience="University projects in Python."))
    assert fresh.bands.trajectory >= 65


# --------------------------------------------------------------------------- #
# HR-realism ordering: a same-field CV must outrank a wrong-field CV.          #
# The definitive owner example — Nursing < Full-Stack < DevSecOps-tailored     #
# for a Senior DevSecOps JD — must hold WITHOUT a standalone domain band.      #
# --------------------------------------------------------------------------- #


def _devsecops_job() -> dict:
    return {
        "id": "j",
        "title": "Senior DevSecOps Engineer",
        "description": (
            "We need a Senior DevSecOps engineer to own CI/CD security, harden "
            "Kubernetes and AWS infrastructure, and automate security scanning."
        ),
        "requirements": "Kubernetes, AWS, Docker, CI/CD, security automation, Terraform.",
        "experience_mode": "range",
        "experience_min_years": 5,
        "seniority_level": "senior",
        "required_skills": [
            "Kubernetes",
            "AWS",
            "Docker",
            "CI/CD",
            "Terraform",
            "Security automation",
        ],
        "preferred_skills": ["Python", "Linux"],
    }


def test_devsecops_ordering_nursing_below_fullstack() -> None:
    job = _devsecops_job()

    nursing = _cv(
        cv_id="nurse",
        skills="Patient care, medication administration, vital signs, clinical documentation",
        experience=(
            "Registered nurse at City Hospital 01/2019 - present. Cared for patients, "
            "administered medication, supported doctors on clinical rounds."
        ),
        education="Bachelor of Nursing, University of Medicine",
    )
    fullstack = _cv(
        cv_id="fullstack",
        skills="JavaScript, React, Node.js, Python, Docker, Linux, SQL",
        experience=(
            "Full-stack developer 01/2019 - present. Built web apps in React and Node.js, "
            "containerised services with Docker on Linux, deployed to AWS."
        ),
        education="Bachelor of Computer Science",
    )
    devsecops = _cv(
        cv_id="devsecops",
        skills="Kubernetes, AWS, Docker, CI/CD, Terraform, security automation, Python, Linux",
        experience=(
            "Senior DevSecOps engineer 01/2018 - present. Owned CI/CD security, hardened "
            "Kubernetes and AWS, automated security scanning with Terraform. Led a team of 5, "
            "reduced deployment incidents by 40%."
        ),
        education="Bachelor of Computer Science",
    )

    out = job_fit.evaluate(job, [nursing, fullstack, devsecops], stale_days=120)
    by_id = {r.cv_id: r for r in out.results}

    # Strict HR ordering.
    assert by_id["nurse"].score < by_id["fullstack"].score < by_id["devsecops"].score
    # The wrong-field candidate is decisively rejected, not merely a bit lower.
    assert by_id["nurse"].score < 30
    # The tailored candidate is a strong recommend.
    assert by_id["devsecops"].score >= 70
    assert out.recommended_cv_id == "devsecops"
