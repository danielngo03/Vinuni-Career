"""On-demand HR CV↔JD evaluation service tests.

Covers: RBAC (``ai_recruiting:screen_candidate`` required; cross-org 404),
deterministic fallback when AI is unavailable (structured, never 500, not
cached), the metered success path (durable ledger row + version-stamped cache
row), cache hit (no re-spend / no model re-call), and ``refresh`` re-metering.
"""

from __future__ import annotations

import json
import uuid

import pytest
from app.ai.observability.models import AiBillableUsage
from app.modules.recruitment.application import apply_service, cv_evaluation_service
from app.modules.recruitment.domain.models import CvEvaluation
from app.shared.exceptions import PermissionDeniedError, ResourceNotFoundError
from app.shared.models import AuditLog
from sqlalchemy import func, select

from tests.auth_utils import CTX
from tests.documents_utils import make_student
from tests.org_utils import add_member, make_org_with_admin
from tests.recruitment_utils import apply_payload, make_builder_cv, publish_job

_CANNED = json.dumps(
    {
        "recommendation": "consider",
        "overall_score": 61,
        "summary": "Backend fundamentals present; a couple of gaps to probe.",
        "strengths": [{"point": "Python evidenced", "evidence": "FastAPI project"}],
        "gaps": [
            {"point": "Kubernetes not evidenced", "why_it_matters": "Named in the JD"}
        ],
        "criteria": [
            {"name": "Required skills", "verdict": "partial", "note": "Python present"}
        ],
        "next_step": "Schedule a short technical screen",
    }
)


async def _setup_applied(db):
    _pu, org, partner = await make_org_with_admin(db, display_name="Partner Co")
    _uu, _uorg, uni = await make_org_with_admin(db, org_type="university")
    job_id = await publish_job(
        db,
        partner_principal=partner,
        uni_principal=uni,
        required_skills=["python", "fastapi", "postgresql", "docker"],
    )
    _su, student = await make_student(db, prefix="cand")
    sel = await make_builder_cv(db, student=student)
    app = await apply_service.apply_to_job(
        db, principal=student, payload=apply_payload(job_id=job_id, cv_selection=sel), ctx=CTX
    )
    return org, partner, job_id, uuid.UUID(app["id"])


async def _ledger_count(db) -> int:
    return (
        await db.execute(
            select(func.count())
            .select_from(AiBillableUsage)
            .where(AiBillableUsage.feature_key == "screening_brief")
        )
    ).scalar_one()


async def _cache_count(db, app_id: uuid.UUID) -> int:
    return (
        await db.execute(
            select(func.count())
            .select_from(CvEvaluation)
            .where(CvEvaluation.application_id == app_id)
        )
    ).scalar_one()


# --------------------------------------------------------------------------- #
# Deterministic fallback (AI unavailable) — structured, no 500, NOT cached      #
# --------------------------------------------------------------------------- #


async def test_evaluation_falls_back_when_ai_unavailable(db_session, monkeypatch) -> None:
    from app.shared.exceptions import AIUnavailableError

    org, partner, _job_id, app_id = await _setup_applied(db_session)

    async def _boom(*a, **k):
        raise AIUnavailableError()

    monkeypatch.setattr(cv_evaluation_service, "_run_model", _boom)

    out = await cv_evaluation_service.evaluate_candidate_cv(
        db_session, principal=partner, application_id=app_id, ctx=CTX
    )
    assert out["is_fallback"] is True
    assert out["recommendation"] in {"strong", "consider", "weak"}
    assert isinstance(out["strengths"], list)
    assert isinstance(out["gaps"], list)
    assert isinstance(out["criteria"], list)
    # No provider/model/token leakage keys.
    assert not any(k in out for k in ("provider", "model", "tokens", "latency", "prompt"))
    # A fallback is NOT cached (so a later request retries the model).
    assert await _cache_count(db_session, app_id) == 0
    # No charge on a non-success result.
    assert await _ledger_count(db_session) == 0
    # The action is still audited.
    audited = (
        await db_session.execute(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.action == "application.cv_evaluated")
        )
    ).scalar_one()
    assert audited == 1


# --------------------------------------------------------------------------- #
# Success path — meters (ledger) + version-stamped cache                        #
# --------------------------------------------------------------------------- #


async def test_evaluation_success_meters_and_caches(db_session, monkeypatch) -> None:
    org, partner, _job_id, app_id = await _setup_applied(db_session)

    async def _ok(*a, **k):
        return _CANNED

    monkeypatch.setattr(cv_evaluation_service, "_run_model", _ok)

    out = await cv_evaluation_service.evaluate_candidate_cv(
        db_session, principal=partner, application_id=app_id, ctx=CTX
    )
    assert out["is_fallback"] is False
    assert out["recommendation"] == "consider"
    # Categorical recommendation is the headline; match_score is the ring number.
    assert "match_score" in out and "match_band" in out
    assert out["strengths"][0]["evidence"] == "FastAPI project"
    assert out["gaps"][0]["why_it_matters"] == "Named in the JD"
    assert out["criteria"][0]["verdict"] == "partial"

    # Durable, idempotent ledger charge (one successful, user-visible result).
    assert await _ledger_count(db_session) == 1
    # Version-stamped cache row written.
    assert await _cache_count(db_session, app_id) == 1


# --------------------------------------------------------------------------- #
# Cache hit — re-opening returns instantly with NO model re-call / re-spend      #
# --------------------------------------------------------------------------- #


async def test_evaluation_cache_hit_does_not_respend(db_session, monkeypatch) -> None:
    org, partner, _job_id, app_id = await _setup_applied(db_session)

    async def _ok(*a, **k):
        return _CANNED

    monkeypatch.setattr(cv_evaluation_service, "_run_model", _ok)
    first = await cv_evaluation_service.evaluate_candidate_cv(
        db_session, principal=partner, application_id=app_id, ctx=CTX
    )
    assert first["is_fallback"] is False
    ledger_after_first = await _ledger_count(db_session)

    # Second open MUST NOT call the model again.
    async def _fail(*a, **k):
        raise AssertionError("model must not be re-called on a cache hit")

    monkeypatch.setattr(cv_evaluation_service, "_run_model", _fail)
    second = await cv_evaluation_service.evaluate_candidate_cv(
        db_session, principal=partner, application_id=app_id, ctx=CTX
    )
    assert second["cached"] is True
    assert second["recommendation"] == first["recommendation"]
    # No new charge on a cache hit.
    assert await _ledger_count(db_session) == ledger_after_first


# --------------------------------------------------------------------------- #
# Refresh — recomputes and re-meters                                            #
# --------------------------------------------------------------------------- #


async def test_evaluation_refresh_remeters(db_session, monkeypatch) -> None:
    org, partner, _job_id, app_id = await _setup_applied(db_session)

    calls = {"n": 0}

    async def _ok(*a, **k):
        calls["n"] += 1
        return _CANNED

    monkeypatch.setattr(cv_evaluation_service, "_run_model", _ok)
    await cv_evaluation_service.evaluate_candidate_cv(
        db_session, principal=partner, application_id=app_id, ctx=CTX
    )
    assert calls["n"] == 1
    ledger_1 = await _ledger_count(db_session)

    # refresh=True forces a recompute + a fresh charge.
    await cv_evaluation_service.evaluate_candidate_cv(
        db_session, principal=partner, application_id=app_id, ctx=CTX, refresh=True
    )
    assert calls["n"] == 2
    assert await _ledger_count(db_session) == ledger_1 + 1
    # Still exactly one cache row (recompute updates in place, not append).
    assert await _cache_count(db_session, app_id) == 1


# --------------------------------------------------------------------------- #
# RBAC — capability required; cross-org 404                                     #
# --------------------------------------------------------------------------- #


async def test_evaluation_requires_screen_candidate_capability(db_session) -> None:
    org, _partner, _job_id, app_id = await _setup_applied(db_session)
    # A partner member holding only ``applications:read`` (not the AI screen cap).
    _u, _m, reader = await add_member(
        db_session, org=org, permissions=[("applications", "read")]
    )
    with pytest.raises(PermissionDeniedError):
        await cv_evaluation_service.evaluate_candidate_cv(
            db_session, principal=reader, application_id=app_id, ctx=CTX
        )


async def test_evaluation_cross_org_is_404(db_session) -> None:
    _org, _partner, _job_id, app_id = await _setup_applied(db_session)
    _ou, _oorg, other = await make_org_with_admin(db_session, display_name="Other Co")
    with pytest.raises(ResourceNotFoundError):
        await cv_evaluation_service.evaluate_candidate_cv(
            db_session, principal=other, application_id=app_id, ctx=CTX
        )
