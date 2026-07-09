"""Cross-lingual (VN CV vs EN JD) band-coverage tests for the CV-JD matcher.

Locks in the 2026-07-07 correctness fixes:

1. ROLE / EXPERIENCE / CREDENTIALS bands now benefit from the cross-lingual
   augmentation. Before the fix a Vietnamese CV (VN experience / education /
   summary prose + VN skills) scored against an English JD had a correct SKILLS
   band but depressed ROLE / EXPERIENCE / CREDENTIALS bands (~42% of weight),
   because those bands read VN prose against EN JD terms. The synthetic
   ``skills_en`` + ``translated_en`` sections now feed those bands.
2. No duplicate (VN original + its EN translation) entry in ``matched_skills`` /
   ``gaps``, and the "matched ∩ gaps = ∅" invariant holds after augmentation.
3. Offline (no augmentation) the scorer is byte-identical to the pure lexical one.

All OFFLINE + PURE: the model call is replaced by a deterministic fake VN→EN map
and the DB cache is stubbed to no-ops. No network, no database.
"""

from __future__ import annotations

import pytest
from app.ai.cv import job_fit, skill_translation

# Deterministic VN→EN map the fake "model" returns. Covers both skill terms and
# the SINGLE collected experience/education/summary prose blob (the prose sections
# are concatenated + translated as one cached unit — see ``_translate_prose_unit``).
_PROSE_VN = (
    "chuyên gia chuỗi cung ứng với kinh nghiệm phân tích dữ liệu kỹ sư chuỗi cung "
    "ứng tại công ty abc phụ trách quản lý chuỗi cung ứng và phân tích dữ liệu vận "
    "hành kho cử nhân kỹ thuật công nghiệp đại học bách khoa"
)
_PROSE_EN = (
    "supply chain specialist with data analysis experience supply chain engineer "
    "at abc company responsible for supply chain management and data analysis of "
    "warehouse operations bachelor of industrial engineering polytechnic university"
)
_FAKE_MAP = {
    "quản lý chuỗi cung ứng": "supply chain management",
    "phân tích dữ liệu": "data analysis",
    _PROSE_VN: _PROSE_EN,
}


@pytest.fixture(autouse=True)
def _reset_lru() -> None:
    skill_translation._LRU.clear()
    yield
    skill_translation._LRU.clear()


@pytest.fixture()
def _no_db_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _empty(source_norms: list[str]) -> dict[str, str]:
        return {}

    async def _noop(source_norm: str, translated: str) -> None:
        return None

    monkeypatch.setattr(skill_translation, "get_cached_translations", _empty)
    monkeypatch.setattr(skill_translation, "put_translation", _noop)


async def _fake_translate_batch(terms: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for term in terms:
        english = _FAKE_MAP.get(skill_translation._norm_key(term))
        if english:
            out[term] = english
    return out


def _enable_ai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(skill_translation, "real_provider_active", lambda: True)
    monkeypatch.setattr(skill_translation, "_translate_batch", _fake_translate_batch)


def _disable_ai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(skill_translation, "real_provider_active", lambda: False)


# --------------------------------------------------------------------------- #
# Fixtures                                                                     #
# --------------------------------------------------------------------------- #


def _vn_cv() -> job_fit.CvInput:
    """A fully Vietnamese CV: VN summary, experience, education, and skills."""
    return job_fit.CvInput(
        cv_id="cv-vn",
        title="CV Tiếng Việt",
        language="vi",
        sections=[
            {
                "section_type": "summary",
                "title": "Tóm tắt",
                "content": {
                    "items": [
                        {"text": ("Chuyên gia chuỗi cung ứng với kinh nghiệm phân tích dữ liệu")}
                    ]
                },
            },
            {
                "section_type": "experience",
                "title": "Kinh nghiệm",
                "content": {
                    "items": [
                        {
                            "text": (
                                "Kỹ sư chuỗi cung ứng tại công ty ABC phụ trách "
                                "quản lý chuỗi cung ứng và phân tích dữ liệu vận "
                                "hành kho"
                            )
                        }
                    ]
                },
            },
            {
                "section_type": "education",
                "title": "Học vấn",
                "content": {
                    "items": [{"text": ("Cử nhân kỹ thuật công nghiệp Đại học Bách Khoa")}]
                },
            },
            {
                "section_type": "skills",
                "title": "Kỹ năng",
                "content": {
                    "items": [
                        {"name": "Quản lý chuỗi cung ứng"},
                        {"name": "Phân tích dữ liệu"},
                    ]
                },
            },
        ],
        last_updated_days=3,
    )


def _en_jd() -> dict:
    return {
        "id": "job",
        "title": "Supply Chain Analyst",
        "description": (
            "We are hiring a supply chain analyst to run supply chain management "
            "and data analysis for warehouse operations."
        ),
        "requirements": "Bachelor of engineering. Supply chain management experience.",
        "benefits": "",
        "experience_mode": "min",
        "experience_min_years": 1,
        "degree_required": "bachelor",
        "required_skills": ["supply chain management", "data analysis"],
        "preferred_skills": [],
    }


# --------------------------------------------------------------------------- #
# 1. ROLE + EXPERIENCE bands materially higher WITH augmentation.             #
# --------------------------------------------------------------------------- #


async def test_role_experience_bands_lift_with_augmentation(
    monkeypatch: pytest.MonkeyPatch, _no_db_cache: None
) -> None:
    _enable_ai(monkeypatch)
    job = _en_jd()
    cvs = [_vn_cv()]

    # Baseline: pure lexical, VN prose vs EN JD → depressed role/experience.
    baseline = job_fit.evaluate(job, cvs, stale_days=120).results[0]

    aug_job, aug_cvs, _ = await skill_translation.english_augment(job, cvs)
    augmented = job_fit.evaluate(aug_job, aug_cvs, stale_days=120).results[0]

    # SKILLS and EXPERIENCE (which now folds job-title/role relevance) must be
    # materially higher after augmentation. Role signal lives inside EXPERIENCE
    # since the v10 6-criteria rebuild (no standalone role band).
    assert augmented.bands.skills > baseline.bands.skills + 10
    assert augmented.bands.experience > baseline.bands.experience + 10
    # Overall score improves too.
    assert augmented.score > baseline.score
    # A translated_en section was actually injected on the CV.
    assert any(s.get("section_type") == "translated_en" for s in aug_cvs[0].sections)


async def test_credentials_band_uses_translated_prose(
    monkeypatch: pytest.MonkeyPatch, _no_db_cache: None
) -> None:
    _enable_ai(monkeypatch)
    job = _en_jd()
    cvs = [_vn_cv()]

    baseline = job_fit.evaluate(job, cvs, stale_days=120).results[0]
    aug_job, aug_cvs, _ = await skill_translation.english_augment(job, cvs)
    augmented = job_fit.evaluate(aug_job, aug_cvs, stale_days=120).results[0]

    # The English "bachelor of ... engineering" prose now satisfies the JD's
    # bachelor requirement, so credentials must not regress and should improve.
    assert augmented.bands.credentials >= baseline.bands.credentials


# --------------------------------------------------------------------------- #
# 2. No duplicate VN+EN entry; matched ∩ gaps == ∅.                            #
# --------------------------------------------------------------------------- #


async def test_no_duplicate_vn_en_surfaced_terms(
    monkeypatch: pytest.MonkeyPatch, _no_db_cache: None
) -> None:
    _enable_ai(monkeypatch)
    # JD carries Vietnamese skills; augmentation appends their English forms.
    job = {
        "id": "job",
        "title": "Kỹ sư chuỗi cung ứng",
        "description": "",
        "requirements": "",
        "benefits": "",
        "experience_mode": "no_requirement",
        "required_skills": ["Quản lý chuỗi cung ứng", "Phân tích dữ liệu"],
        "preferred_skills": [],
    }
    cvs = [_vn_cv()]

    aug_job, aug_cvs, _ = await skill_translation.english_augment(job, cvs)
    # The JD now carries BOTH VN + EN forms of each skill.
    assert "supply chain management" in aug_job["required_skills"]
    assert "Quản lý chuỗi cung ứng" in aug_job["required_skills"]

    result = job_fit.evaluate(aug_job, aug_cvs, stale_days=120).results[0]

    surfaced = [*result.matched_skills, *result.gaps]
    norm = job_fit.grounding.normalize
    # No entry appears twice by normalized key (no VN + EN of the same skill).
    keys = [norm(t) for t in surfaced]
    assert len(keys) == len(set(keys)), surfaced
    # The English translation string must NOT surface alongside its VN original.
    assert "supply chain management" not in surfaced
    assert "data analysis" not in surfaced
    # matched ∩ gaps == ∅
    matched_keys = {norm(t) for t in result.matched_skills}
    gap_keys = {norm(t) for t in result.gaps}
    assert matched_keys.isdisjoint(gap_keys)


# --------------------------------------------------------------------------- #
# 3. Offline = byte-identical, no synthetic sections.                          #
# --------------------------------------------------------------------------- #


async def test_offline_byte_identical_no_synthetic_sections(
    monkeypatch: pytest.MonkeyPatch, _no_db_cache: None
) -> None:
    _disable_ai(monkeypatch)
    job = _en_jd()
    cvs = [_vn_cv()]

    aug_job, aug_cvs, _ = await skill_translation.english_augment(job, cvs)
    assert aug_job is job
    assert aug_cvs is cvs

    augmented = job_fit.evaluate(aug_job, aug_cvs, stale_days=120).results[0]
    pure = job_fit.evaluate(job, cvs, stale_days=120).results[0]
    assert augmented.score == pure.score
    assert augmented.bands.as_dict() == pure.bands.as_dict()
    assert augmented.matched_skills == pure.matched_skills
    assert augmented.gaps == pure.gaps


# --------------------------------------------------------------------------- #
# 4. English CV skips prose translation entirely (diacritic gate).            #
# --------------------------------------------------------------------------- #


async def test_english_cv_skips_prose_translation(
    monkeypatch: pytest.MonkeyPatch, _no_db_cache: None
) -> None:
    _enable_ai(monkeypatch)
    job = _en_jd()
    en_cv = job_fit.CvInput(
        cv_id="cv-en",
        title="EN CV",
        language="en",
        sections=[
            {
                "section_type": "experience",
                "title": "Experience",
                "content": {"items": [{"text": "Supply chain engineer with data analysis work"}]},
            },
            {
                "section_type": "skills",
                "title": "Skills",
                "content": {
                    "items": [
                        {"name": "supply chain management"},
                        {"name": "data analysis"},
                    ]
                },
            },
        ],
        last_updated_days=3,
    )

    _aug_job, aug_cvs, _ = await skill_translation.english_augment(job, [en_cv])
    # No translated_en / skills_en section for an all-English CV (identity terms).
    types = {s.get("section_type") for s in aug_cvs[0].sections}
    assert "translated_en" not in types
    assert "skills_en" not in types
