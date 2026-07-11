"""Talent Pool AI semantic search — indexer + search service tests.

Covers: indexer idempotency + consent gate, deterministic ranking (semantic + skill
filter), external-JD path, LLM-rerank path + deterministic fallback, RBAC, and
no-leak (never a raw score / provider / model / cosine / PII).

The suite runs with ``AI_REAL_CALLS_ENABLED=false`` (conftest), so the search
service takes the DETERMINISTIC keyword+filter path by default; the AI-rerank path
is exercised by monkeypatching ``real_provider_active`` + ``_run_rerank``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from app.modules.student_profiles.domain.models import StudentProfile
from app.modules.talent_pool.application import cv_indexer, talent_search_service
from app.modules.talent_pool.domain.models import CvEmbedding
from app.shared.exceptions import (
    AuthRequiredError,
    PermissionDeniedError,
    ValidationFailedError,
)
from app.shared.permissions import GUEST
from sqlalchemy import select

from tests.auth_utils import CTX
from tests.documents_utils import make_student
from tests.org_utils import add_member, make_org_with_admin


def _cv_profile(*, user_id: uuid.UUID, summary: str, skills: list[str], experience: list[dict]):
    from app.modules.documents.domain.models import CvProfile

    sections = [
        {"section_type": "summary", "title": "Summary", "content": {"text": summary}},
        {
            "section_type": "skills",
            "title": "Skills",
            "content": {"items": [{"name": s} for s in skills]},
        },
        {"section_type": "experience", "title": "Experience", "content": {"items": experience}},
        {
            "section_type": "education",
            "title": "Education",
            "content": {"items": [{"degree": "BSc Computer Science", "institution": "VinUni"}]},
        },
    ]
    return CvProfile(
        user_id=user_id,
        title="Candidate CV",
        source_type="builder",
        status="ready",
        language="en",
        version=1,
        finalized_at=datetime.now(tz=UTC),
        canvas_json={},
        matching_json={
            "schema_version": 1,
            "content_version": 1,
            "sections": sections,
            "last_activity_at": None,
        },
    )


async def _seed_candidate(
    db,
    *,
    prefix: str,
    skills: list[str],
    summary: str = "Software engineer",
    experience: list[dict] | None = None,
    visibility: str = "public",
    open_to_work: bool = True,
    index: bool = True,
):
    user, _principal = await make_student(db, prefix=prefix)
    profile = StudentProfile(
        user_id=user.id,
        profile_visibility=visibility,
        is_open_to_work=open_to_work,
        location_city="Hanoi",
        location_country="Vietnam",
    )
    db.add(profile)
    cv = _cv_profile(
        user_id=user.id,
        summary=summary,
        skills=skills,
        experience=experience
        or [{"role": "Engineer", "organization": "Example", "timeframe": "2021 - 2024"}],
    )
    db.add(cv)
    await db.commit()
    if index:
        await cv_indexer.index_cv(db, cv_id=cv.id)
        await db.commit()
    return user, profile, cv


async def _search(db, *, principal, **kwargs):
    return await talent_search_service.search_talent(
        db, principal=principal, ctx=CTX, **kwargs
    )


# --------------------------------------------------------------------------- #
# Indexer                                                                     #
# --------------------------------------------------------------------------- #


async def test_indexer_is_idempotent(db_session) -> None:
    user, _profile, cv = await _seed_candidate(
        db_session, prefix="idem", skills=["python", "sql"], index=False
    )
    first = await cv_indexer.index_cv(db_session, cv_id=cv.id)
    await db_session.commit()
    assert first is True
    # Re-index unchanged content -> no re-embed.
    second = await cv_indexer.index_cv(db_session, cv_id=cv.id)
    await db_session.commit()
    assert second is False
    rows = (
        await db_session.execute(select(CvEmbedding).where(CvEmbedding.cv_id == cv.id))
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].skills == ["python", "sql"]
    assert rows[0].vector  # a vector was stored (offline embedding)


async def test_indexer_skips_non_consenting_student(db_session) -> None:
    # Not open to work -> not indexed.
    _u, _p, cv = await _seed_candidate(
        db_session, prefix="noconsent", skills=["go"], open_to_work=False, index=False
    )
    indexed = await cv_indexer.index_cv(db_session, cv_id=cv.id)
    await db_session.commit()
    assert indexed is False
    rows = (
        await db_session.execute(select(CvEmbedding).where(CvEmbedding.cv_id == cv.id))
    ).scalars().all()
    assert rows == []


async def test_backfill_indexes_consented_pool(db_session) -> None:
    await _seed_candidate(db_session, prefix="bf1", skills=["python"], index=False)
    await _seed_candidate(db_session, prefix="bf2", skills=["java"], index=False)
    await _seed_candidate(
        db_session, prefix="bf3", skills=["c++"], open_to_work=False, index=False
    )
    summary = await cv_indexer.backfill_talent_pool(db_session)
    assert summary["indexed"] == 2  # the two open-to-work candidates


# --------------------------------------------------------------------------- #
# Search — deterministic ranking + filters                                    #
# --------------------------------------------------------------------------- #


async def test_search_ranks_and_returns_reasons_no_score(db_session) -> None:
    await _seed_candidate(
        db_session, prefix="pyeng", skills=["python", "django", "sql"], summary="Python engineer"
    )
    await _seed_candidate(
        db_session, prefix="designer", skills=["figma", "photoshop"], summary="Product designer"
    )
    _pu, _org, partner = await make_org_with_admin(db_session, display_name="Recruiter Co")

    result = await _search(
        db_session, principal=partner, query_text="Python backend engineer", skills=["python"]
    )
    items = result["items"]
    assert items, "expected at least one match"
    top = items[0]
    # The Python engineer must rank ahead of the designer.
    assert "python" in [s.lower() for s in top["matched_skills"]]
    assert top["match_tier"] in talent_search_service._TIERS
    assert isinstance(top["match_reasons"], list) and top["match_reasons"]
    assert result["source"] == "keyword_fallback"  # AI off in tests
    # No raw score / provider / model / cosine anywhere in the payload.
    blob = str(result).lower()
    for forbidden in ("score", "cosine", "similarity", "provider", "model_alias", "token"):
        assert forbidden not in blob


async def test_skill_filter_excludes_non_matching(db_session) -> None:
    await _seed_candidate(db_session, prefix="hasdocker", skills=["docker", "kubernetes"])
    await _seed_candidate(db_session, prefix="nodocker", skills=["excel", "word"])
    _pu, _org, partner = await make_org_with_admin(db_session)

    result = await _search(db_session, principal=partner, skills=["docker"])
    assert result["page"]["total"] == 1
    assert len(result["items"]) == 1


async def test_min_experience_filter(db_session) -> None:
    await _seed_candidate(
        db_session,
        prefix="senior",
        skills=["python"],
        experience=[{"role": "Engineer", "organization": "A", "timeframe": "2016 - 2024"}],
    )
    await _seed_candidate(
        db_session,
        prefix="junior",
        skills=["python"],
        experience=[{"role": "Intern", "organization": "B", "timeframe": "2023 - 2024"}],
    )
    _pu, _org, partner = await make_org_with_admin(db_session)

    result = await _search(db_session, principal=partner, skills=["python"], min_experience=5)
    assert result["page"]["total"] == 1  # only the senior clears >= 5 years


async def test_external_jd_text_path(db_session) -> None:
    await _seed_candidate(
        db_session, prefix="mleng", skills=["python", "pytorch", "ml"], summary="ML engineer"
    )
    _pu, _org, partner = await make_org_with_admin(db_session)

    jd = (
        "We are hiring a Machine Learning Engineer. Required: Python, PyTorch, and "
        "hands-on ML model training. This role is not yet posted."
    )
    result = await _search(db_session, principal=partner, jd_text=jd)
    assert result["items"], "external JD text should match candidates"


async def test_empty_query_rejected(db_session) -> None:
    _pu, _org, partner = await make_org_with_admin(db_session)
    with pytest.raises(ValidationFailedError):
        await _search(db_session, principal=partner)


# --------------------------------------------------------------------------- #
# RBAC + visibility isolation                                                 #
# --------------------------------------------------------------------------- #


async def test_rbac_member_without_capability_denied(db_session) -> None:
    _pu, org, _admin = await make_org_with_admin(db_session)
    _mu, _m, member = await add_member(
        db_session, org=org, permissions=[("applications", "read")]
    )
    with pytest.raises(PermissionDeniedError):
        await _search(db_session, principal=member, skills=["python"])


async def test_rbac_guest_denied(db_session) -> None:
    await _seed_candidate(db_session, prefix="g1", skills=["python"])
    with pytest.raises(AuthRequiredError):
        await _search(db_session, principal=GUEST, skills=["python"])


async def test_vinuni_only_candidate_hidden_from_external_partner(db_session) -> None:
    await _seed_candidate(
        db_session, prefix="vonly", skills=["python"], visibility="vinuni_only"
    )
    _pu, _org, partner = await make_org_with_admin(db_session)  # external partner
    _su, _uorg, staff = await make_org_with_admin(db_session, org_type="university")

    external = await _search(db_session, principal=partner, skills=["python"])
    assert external["page"]["total"] == 0  # vinuni_only not visible to external partner

    internal = await _search(db_session, principal=staff, skills=["python"])
    assert internal["page"]["total"] == 1  # university staff sees vinuni_only


async def test_private_candidate_never_surfaced(db_session) -> None:
    # A private profile is not discoverable and is never indexed.
    _u, _p, cv = await _seed_candidate(
        db_session, prefix="priv", skills=["python"], visibility="private", index=False
    )
    indexed = await cv_indexer.index_cv(db_session, cv_id=cv.id)
    await db_session.commit()
    assert indexed is False


# --------------------------------------------------------------------------- #
# LLM rerank path (monkeypatched) + deterministic fallback                    #
# --------------------------------------------------------------------------- #


async def test_llm_rerank_path(db_session, monkeypatch) -> None:
    await _seed_candidate(db_session, prefix="rr", skills=["python", "sql"])
    _pu, _org, partner = await make_org_with_admin(db_session)

    monkeypatch.setattr(talent_search_service, "real_provider_active", lambda: True)

    async def _fake_rerank(*_args, **_kwargs) -> str:
        return (
            '{"candidates": [{"ref": 0, "tier": "excellent", '
            '"reasons": ["Strong Python and SQL, missing Docker"]}]}'
        )

    monkeypatch.setattr(talent_search_service, "_run_rerank", _fake_rerank)

    result = await _search(db_session, principal=partner, skills=["python"])
    assert result["source"] == "ai_semantic"
    top = result["items"][0]
    assert top["match_tier"] == "excellent"
    assert top["match_reasons"] == ["Strong Python and SQL, missing Docker"]


async def test_llm_unavailable_falls_back_deterministically(db_session, monkeypatch) -> None:
    await _seed_candidate(db_session, prefix="fb", skills=["python", "sql"])
    _pu, _org, partner = await make_org_with_admin(db_session)

    monkeypatch.setattr(talent_search_service, "real_provider_active", lambda: True)

    async def _boom(*_args, **_kwargs) -> str:
        from app.shared.exceptions import AIUnavailableError

        raise AIUnavailableError()

    monkeypatch.setattr(talent_search_service, "_run_rerank", _boom)

    result = await _search(db_session, principal=partner, skills=["python"])
    # AI down -> never 500; falls back to deterministic reasons + tier.
    assert result["source"] == "keyword_fallback"
    top = result["items"][0]
    assert isinstance(top["match_reasons"], list) and top["match_reasons"]


async def test_rerank_reason_leak_is_scrubbed(db_session, monkeypatch) -> None:
    await _seed_candidate(db_session, prefix="leak", skills=["python"])
    _pu, _org, partner = await make_org_with_admin(db_session)

    monkeypatch.setattr(talent_search_service, "real_provider_active", lambda: True)

    async def _leaky(*_args, **_kwargs) -> str:
        return (
            '{"candidates": [{"ref": 0, "tier": "strong", "reasons": '
            '["Ranked by OpenAI gpt-4 with cosine similarity 0.91, email a@b.com"]}]}'
        )

    monkeypatch.setattr(talent_search_service, "_run_rerank", _leaky)

    result = await _search(db_session, principal=partner, skills=["python"])
    blob = str(result).lower()
    for forbidden in ("openai", "gpt-4", "0.91", "a@b.com"):
        assert forbidden not in blob
