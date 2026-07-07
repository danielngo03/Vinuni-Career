"""Unit tests for the translation-normalization tier (``app.ai.cv.skill_translation``).

These are OFFLINE + PURE: the model call is replaced by a deterministic fake VN→EN
map and the persistent DB cache is stubbed to in-memory no-ops, so no network and
no database are touched. They lock in the four contracts the tier promises:

1. Gated on AI: with AI OFF, ``english_augment`` returns its inputs unchanged and
   ``job_fit.evaluate`` is byte-identical to the pure lexical scorer.
2. With AI ON (fake translator): a CV whose only skill is a Vietnamese phrase
   MATCHES an English JD requirement after augmentation (gap → matched).
3. ASCII/English terms skip the translator entirely (identity, no model call).
4. Cache reuse: translating the same term twice calls the model once.
"""
from __future__ import annotations

import pytest
from app.ai.cv import job_fit, skill_translation

# Deterministic VN→EN skill map the fake "model" returns.
_FAKE_MAP = {
    "quản lý chuỗi cung ứng": "supply chain management",
    "chăm sóc khách hàng": "customer service",
    "phân tích tài chính": "financial analysis",
}


@pytest.fixture(autouse=True)
def _reset_lru() -> None:
    """Clear the in-process translation LRU before each test for isolation."""
    skill_translation._LRU.clear()
    yield
    skill_translation._LRU.clear()


@pytest.fixture()
def _no_db_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub the persistent DB cache so the unit tests never touch a database."""
    monkeypatch.setattr(
        skill_translation, "get_cached_translations", _async_empty
    )
    monkeypatch.setattr(skill_translation, "put_translation", _async_noop)


async def _async_empty(source_norms: list[str]) -> dict[str, str]:
    return {}


async def _async_noop(source_norm: str, translated: str) -> None:
    return None


class _Counter:
    """A deterministic fake batch-translator that counts model invocations."""

    def __init__(self) -> None:
        self.calls = 0
        self.translated_terms: list[str] = []

    async def translate_batch(self, terms: list[str]) -> dict[str, str]:
        self.calls += 1
        out: dict[str, str] = {}
        for term in terms:
            self.translated_terms.append(term)
            key = skill_translation._norm_key(term)
            english = _FAKE_MAP.get(key)
            if english:
                out[term] = english
        return out


def _enable_ai(monkeypatch: pytest.MonkeyPatch, fake: _Counter) -> None:
    """Turn the AI gate on and route the model call to the counting fake."""
    monkeypatch.setattr(skill_translation, "real_provider_active", lambda: True)
    monkeypatch.setattr(skill_translation, "_translate_batch", fake.translate_batch)


def _disable_ai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(skill_translation, "real_provider_active", lambda: False)


# --------------------------------------------------------------------------- #
# Fixtures: a Vietnamese-skill CV and an English JD requiring the same skill.  #
# --------------------------------------------------------------------------- #

def _vn_skill_cv() -> job_fit.CvInput:
    return job_fit.CvInput(
        cv_id="cv-vn",
        title="CV",
        language="vi",
        sections=[
            {
                "section_type": "skills",
                "title": "Kỹ năng",
                "content": {"items": [{"name": "Quản lý chuỗi cung ứng"}]},
            },
        ],
        last_updated_days=3,
    )


def _en_jd() -> dict:
    return {
        "id": "job",
        "title": "Supply Chain Analyst",
        "description": "",
        "requirements": "",
        "experience_mode": "no_requirement",
        "required_skills": ["supply chain management"],
        "preferred_skills": [],
    }


# --------------------------------------------------------------------------- #
# 1. Gated on AI — offline augmentation is a no-op / byte-identical.           #
# --------------------------------------------------------------------------- #

async def test_english_augment_offline_is_noop(
    monkeypatch: pytest.MonkeyPatch, _no_db_cache: None
) -> None:
    _disable_ai(monkeypatch)
    job = _en_jd()
    cvs = [_vn_skill_cv()]

    aug_job, aug_cvs, _ = await skill_translation.english_augment(job, cvs)

    # Same objects returned, unchanged.
    assert aug_job is job
    assert aug_cvs is cvs


async def test_evaluate_offline_byte_identical(
    monkeypatch: pytest.MonkeyPatch, _no_db_cache: None
) -> None:
    _disable_ai(monkeypatch)
    job = _en_jd()
    cvs = [_vn_skill_cv()]

    aug_job, aug_cvs, _ = await skill_translation.english_augment(job, cvs)
    augmented = job_fit.evaluate(aug_job, aug_cvs, stale_days=120)
    pure = job_fit.evaluate(job, cvs, stale_days=120)

    a, p = augmented.results[0], pure.results[0]
    assert a.score == p.score
    assert a.matched_skills == p.matched_skills
    assert a.gaps == p.gaps
    # Offline, the VN skill is NOT matched against the English requirement.
    assert "supply chain management" in p.gaps


# --------------------------------------------------------------------------- #
# 2. AI ON — a VN-only CV matches an English requirement after augmentation.   #
# --------------------------------------------------------------------------- #

async def test_vn_cv_matches_english_jd_after_augment(
    monkeypatch: pytest.MonkeyPatch, _no_db_cache: None
) -> None:
    fake = _Counter()
    _enable_ai(monkeypatch, fake)
    job = _en_jd()
    cvs = [_vn_skill_cv()]

    # Baseline (no augmentation): the VN skill is a gap.
    baseline = job_fit.evaluate(job, cvs, stale_days=120).results[0]
    assert "supply chain management" in baseline.gaps
    assert "supply chain management" not in baseline.matched_skills

    # After English augmentation the requirement moves to matched.
    aug_job, aug_cvs, _ = await skill_translation.english_augment(job, cvs)
    result = job_fit.evaluate(aug_job, aug_cvs, stale_days=120).results[0]
    assert "supply chain management" in result.matched_skills
    assert "supply chain management" not in result.gaps
    assert result.score >= baseline.score
    # Original JD requirement string is preserved (English CV still matches it).
    assert "supply chain management" in aug_job["required_skills"]


# --------------------------------------------------------------------------- #
# 3. ASCII / English terms skip the translator.                                #
# --------------------------------------------------------------------------- #

async def test_english_terms_skip_translator(
    monkeypatch: pytest.MonkeyPatch, _no_db_cache: None
) -> None:
    fake = _Counter()
    _enable_ai(monkeypatch, fake)

    result = await skill_translation.normalize_terms_to_en(
        ["python", "supply chain management", "c++", "React Native"]
    )

    # Every ASCII term is identity-mapped.
    assert result["python"] == "python"
    assert result["supply chain management"] == "supply chain management"
    assert result["c++"] == "c++"
    assert result["React Native"] == "React Native"
    # The model was never called (no Vietnamese diacritics anywhere).
    assert fake.calls == 0
    assert fake.translated_terms == []


async def test_diacritic_detection() -> None:
    assert skill_translation._has_vietnamese_diacritics("Quản lý")
    assert skill_translation._has_vietnamese_diacritics("chăm sóc")
    assert not skill_translation._has_vietnamese_diacritics("supply chain")
    assert not skill_translation._has_vietnamese_diacritics("c++")
    assert not skill_translation._has_vietnamese_diacritics("Node.js")


# --------------------------------------------------------------------------- #
# 4. Cache reuse — the same term is translated once, not twice.                #
# --------------------------------------------------------------------------- #

async def test_lru_cache_reuse_single_model_call(
    monkeypatch: pytest.MonkeyPatch, _no_db_cache: None
) -> None:
    fake = _Counter()
    _enable_ai(monkeypatch, fake)

    first = await skill_translation.normalize_terms_to_en(["Quản lý chuỗi cung ứng"])
    assert first["Quản lý chuỗi cung ứng"] == "supply chain management"
    assert fake.calls == 1

    # Second call for the same term is served from the in-process LRU — no model.
    second = await skill_translation.normalize_terms_to_en(["Quản lý chuỗi cung ứng"])
    assert second["Quản lý chuỗi cung ứng"] == "supply chain management"
    assert fake.calls == 1  # still one — cached.


async def test_mixed_batch_translates_only_vietnamese(
    monkeypatch: pytest.MonkeyPatch, _no_db_cache: None
) -> None:
    fake = _Counter()
    _enable_ai(monkeypatch, fake)

    result = await skill_translation.normalize_terms_to_en(
        ["python", "Chăm sóc khách hàng", "sql"]
    )
    assert result["python"] == "python"
    assert result["sql"] == "sql"
    assert result["Chăm sóc khách hàng"] == "customer service"
    # Only the Vietnamese term reached the model.
    assert fake.translated_terms == ["Chăm sóc khách hàng"]


async def test_translation_failure_degrades_to_identity(
    monkeypatch: pytest.MonkeyPatch, _no_db_cache: None
) -> None:
    """A model that returns nothing → identity map, never raises."""

    async def _empty_batch(terms: list[str]) -> dict[str, str]:
        return {}

    monkeypatch.setattr(skill_translation, "real_provider_active", lambda: True)
    monkeypatch.setattr(skill_translation, "_translate_batch", _empty_batch)

    result = await skill_translation.normalize_terms_to_en(["Phân tích tài chính"])
    assert result["Phân tích tài chính"] == "Phân tích tài chính"


# --------------------------------------------------------------------------- #
# 5. Degradation signal — `complete` flag drives don't-persist-degraded.       #
# --------------------------------------------------------------------------- #

async def test_augment_complete_true_when_translation_succeeds(
    monkeypatch: pytest.MonkeyPatch, _no_db_cache: None
) -> None:
    fake = _Counter()
    _enable_ai(monkeypatch, fake)
    _job, _cvs, complete = await skill_translation.english_augment(_en_jd(), [_vn_skill_cv()])
    assert complete is True


async def test_augment_complete_false_when_translation_fails(
    monkeypatch: pytest.MonkeyPatch, _no_db_cache: None
) -> None:
    """AI on but the model returns nothing → complete=False so the caller persists
    the degraded score provisionally and retries next request."""

    async def _empty_batch(terms: list[str]) -> dict[str, str]:
        return {}

    monkeypatch.setattr(skill_translation, "real_provider_active", lambda: True)
    monkeypatch.setattr(skill_translation, "_translate_batch", _empty_batch)

    _job, _cvs, complete = await skill_translation.english_augment(_en_jd(), [_vn_skill_cv()])
    assert complete is False


async def test_augment_complete_true_offline() -> None:
    # Offline is the intended lexical result, not a degradation — cacheable.
    import pytest as _pytest  # local import to avoid unused at module import

    mp = _pytest.MonkeyPatch()
    mp.setattr(skill_translation, "real_provider_active", lambda: False)
    try:
        _job, _cvs, complete = await skill_translation.english_augment(_en_jd(), [_vn_skill_cv()])
        assert complete is True
    finally:
        mp.undo()
