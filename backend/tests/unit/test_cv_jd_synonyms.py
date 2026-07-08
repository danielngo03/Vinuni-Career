"""Golden regression tests for CV-JD synonym / abbreviation / implication
matching in the DETERMINISTIC scorer (``app.ai.cv.job_fit``).

These lock in the owner requirement (2026-07-06): a CV that writes an
abbreviation (``k8s``) must satisfy a JD that writes the canonical form
(``Kubernetes``) — and such a skill must NEVER resurface as a gap /
"improve this" suggestion. Pure functions, no DB, no LLM — fast and free.
"""
from __future__ import annotations

import pytest
from app.ai.cv import job_fit


def _job(*, required: list[str], preferred: list[str] | None = None) -> dict:
    return {
        "id": "job",
        "title": "Engineer",
        "description": "",
        "requirements": "",
        "experience_mode": "no_requirement",
        "required_skills": required,
        "preferred_skills": preferred or [],
    }


def _cv(skills_text: str) -> job_fit.CvInput:
    return job_fit.CvInput(
        cv_id="cv",
        title="CV",
        language="en",
        sections=[
            {
                "section_type": "skills",
                "title": "Skills",
                "content": {"items": [{"text": skills_text}]},
            },
            {
                "section_type": "experience",
                "title": "Experience",
                "content": {"items": [{"text": f"Hands-on production work with {skills_text}."}]},
            },
        ],
        last_updated_days=3,
    )


def _match(job: dict, cv_skills: str) -> job_fit.CvFit:
    out = job_fit.evaluate(job, [_cv(cv_skills)], stale_days=120)
    return out.results[0]


# (jd_required_term, cv_written_term) pairs that MUST be treated as the same.
_EQUIVALENT = [
    ("Kubernetes", "k8s"),
    ("k8s", "kubernetes"),
    ("JavaScript", "JS"),
    ("Machine Learning", "ML"),
    ("PostgreSQL", "postgres"),
    ("Amazon Web Services", "AWS"),
    ("TypeScript", "ts"),
    ("Natural Language Processing", "NLP"),
]


@pytest.mark.parametrize("jd_term,cv_term", _EQUIVALENT)
def test_abbreviation_counts_as_matched_not_gap(jd_term: str, cv_term: str) -> None:
    r = _match(_job(required=[jd_term]), cv_term)
    assert jd_term in r.matched_skills, f"{cv_term!r} should satisfy JD {jd_term!r}"
    assert jd_term not in r.gaps, f"{jd_term!r} must not be a gap when CV has {cv_term!r}"


# CV tech that IMPLIES a JD requirement (one-way).
_IMPLIES = [
    ("Python", "FastAPI"),        # FastAPI implies Python
    ("JavaScript", "React"),      # React implies JavaScript
    ("Java", "Spring Boot"),      # Spring Boot implies Java
    ("Kubernetes", "Helm"),       # Helm implies Kubernetes
]


@pytest.mark.parametrize("jd_term,cv_term", _IMPLIES)
def test_technology_implication_satisfies_requirement(jd_term: str, cv_term: str) -> None:
    r = _match(_job(required=[jd_term]), cv_term)
    assert jd_term in r.matched_skills, f"{cv_term!r} should imply {jd_term!r}"
    assert jd_term not in r.gaps


def test_vietnamese_abbreviation_matches_full_form() -> None:
    # JD written with the full Vietnamese term; CV uses the abbreviation.
    r = _match(_job(required=["công nghệ thông tin"]), "CNTT")
    assert "công nghệ thông tin" in r.matched_skills


# Non-tech / Vietnamese business-domain equivalences (marketing, office, HR,
# sales, design, manufacturing, soft skills) — the real student population.
_DOMAIN_EQUIVALENT = [
    ("teamwork", "kỹ năng làm việc nhóm"),
    ("communication", "giao tiếp tốt"),
    ("time management", "quản lý thời gian"),
    ("customer service", "chăm sóc khách hàng"),
    ("Excel", "thành thạo bảng tính"),
    ("digital marketing", "tiếp thị số"),
    ("recruitment", "tuyển dụng nhân sự"),
    ("quản lý sản xuất", "production management"),
    ("garment", "ngành may mặc"),
    ("quản lý chất lượng", "quality management"),
]


@pytest.mark.parametrize("jd_term,cv_term", _DOMAIN_EQUIVALENT)
def test_business_domain_equivalents_match(jd_term: str, cv_term: str) -> None:
    r = _match(_job(required=[jd_term]), cv_term)
    assert jd_term in r.matched_skills, f"{cv_term!r} should satisfy JD {jd_term!r}"
    assert jd_term not in r.gaps


# CV tool → broader discipline it demonstrates (one-way, non-tech).
_DOMAIN_IMPLIES = [
    ("digital marketing", "chạy facebook ads"),
    ("digital marketing", "làm SEO cho website"),
    ("graphic design", "thiết kế bằng Canva"),
    ("video editing", "edit video bằng CapCut"),
]


@pytest.mark.parametrize("jd_term,cv_term", _DOMAIN_IMPLIES)
def test_business_tool_implies_discipline(jd_term: str, cv_term: str) -> None:
    r = _match(_job(required=[jd_term]), cv_term)
    assert jd_term in r.matched_skills, f"{cv_term!r} should imply {jd_term!r}"


# Confusable pairs the LEXICAL matcher must NOT collapse (word-boundary precision).
_CONFUSABLE_NON_MATCH = [
    ("Java", "experienced javascript developer"),   # java ⊄ javascript
    ("C", "c++ and c# programming"),                # c ⊄ c++ / c#
    ("develop", "senior developer"),                # develop ⊄ developer
]


@pytest.mark.parametrize("jd_term,cv_text", _CONFUSABLE_NON_MATCH)
def test_confusable_substrings_do_not_falsely_match(jd_term: str, cv_text: str) -> None:
    r = _match(_job(required=[jd_term]), cv_text)
    assert jd_term not in r.matched_skills, f"{jd_term!r} must not match {cv_text!r}"
    assert jd_term in r.gaps


def test_confusable_real_skills_still_match() -> None:
    # The precision fix must not break genuine matches for these tokens.
    assert "Java" in _match(_job(required=["Java"]), "strong in Java and Spring Boot").matched_skills
    assert "C++" in _match(_job(required=["C++"]), "C++ and CUDA").matched_skills
    assert "C#" in _match(_job(required=["C#"]), "built APIs in C#").matched_skills


def _degree_result(cv_education: str, degree_required: str) -> job_fit.CvFit:
    job = {
        "id": "job", "title": "Role", "description": "", "requirements": "",
        "experience_mode": "no_requirement", "required_skills": [], "preferred_skills": [],
        "degree_required": degree_required,
    }
    cv = job_fit.CvInput(
        cv_id="cv", title="CV", language="vi",
        sections=[{"section_type": "education", "title": "Học vấn",
                   "content": {"items": [{"text": cv_education}]}}],
        last_updated_days=5,
    )
    return job_fit.evaluate(job, [cv], stale_days=120).results[0]


def test_vietnamese_degree_satisfies_english_requirement() -> None:
    r = _degree_result("Cử nhân Quản trị Kinh doanh, Đại học Kinh tế", "bachelor")
    assert r.bands.credentials == 100
    assert "bachelor" not in r.gaps  # student HAS the degree — never a gap
    assert "bachelor" in r.matched_skills


def test_higher_degree_satisfies_lower_requirement() -> None:
    assert _degree_result("Thạc sĩ Khoa học Máy tính", "bachelor").bands.credentials == 100


def test_insufficient_degree_is_a_gap() -> None:
    r = _degree_result("Tốt nghiệp THPT", "bachelor")
    assert "bachelor" in r.gaps
    assert r.bands.credentials < 100


def test_degree_not_double_counted_as_aliases() -> None:
    # A single degree requirement must surface as ONE term, never bsc/ba/etc.
    r = _degree_result("Bằng cử nhân", "bachelor")
    assert r.gaps.count("bachelor") == 0
    for noise in ("bsc", "ba", "đại học"):
        assert noise not in r.gaps and noise not in r.matched_skills


def test_genuine_gap_stays_a_gap() -> None:
    # CV has Docker only; JD needs Kubernetes + Python -> both are real gaps.
    r = _match(_job(required=["Kubernetes", "Python"]), "Docker, Bash")
    assert "Kubernetes" in r.gaps
    assert "Python" in r.gaps
    assert "Kubernetes" not in r.matched_skills


def test_matched_and_gap_are_disjoint() -> None:
    r = _match(
        _job(required=["Kubernetes", "Python", "Docker"]),
        "k8s and docker experience",
    )
    # A term can never be both matched and a gap.
    assert not (set(r.matched_skills) & set(r.gaps))
    assert "Kubernetes" in r.matched_skills
    assert "Docker" in r.matched_skills
    assert "Python" in r.gaps


def test_scores_are_deterministic_across_runs() -> None:
    job = _job(required=["Kubernetes", "Python"], preferred=["AWS"])
    first = _match(job, "k8s, python, aws")
    second = _match(job, "k8s, python, aws")
    assert first.score == second.score
    assert first.bands.as_dict() == second.bands.as_dict()


def _leveled_cv(cv_id: str, level: int) -> job_fit.CvInput:
    """Two CVs with identical matchable text but different self-rated levels."""
    return job_fit.CvInput(
        cv_id=cv_id,
        title=cv_id,
        language="en",
        sections=[
            {"section_type": "skills", "title": "Skills",
             "content": {"items": [{"name": "Python", "level": level},
                                    {"name": "Docker", "level": level}]}},
            {"section_type": "experience", "title": "Experience",
             "content": {"items": [{"text": "Production Python and Docker work."}]}},
        ],
        last_updated_days=5,
    )


def test_skill_level_breaks_ties_but_not_score() -> None:
    job = _job(required=["Python", "Docker"])
    strong = _leveled_cv("strong", 90)
    weak = _leveled_cv("weak", 20)
    out = job_fit.evaluate(job, [weak, strong], stale_days=120)
    # Identical matchable content -> identical score (levels never move the number).
    by_id = {r.cv_id: r for r in out.results}
    assert by_id["strong"].score == by_id["weak"].score
    # ...but the higher self-rated CV is recommended on the tie.
    assert out.recommended_cv_id == "strong"


def test_absent_levels_are_neutral_not_penalized() -> None:
    # A CV with no numeric levels must not lose the tie to a low-rated one.
    job = _job(required=["Python", "Docker"])
    prose = _match(job, "Python and Docker")  # no levels -> neutral 50
    assert prose.avg_skill_level == 50.0
