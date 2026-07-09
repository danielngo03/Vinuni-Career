"""Graceful degradation: batch CV-JD fit scoring when Redis is unavailable.

Redis is a best-effort accelerator for the job-card fit badges; the DB
``fit_store`` is the source of truth. If Redis raises on read OR write, the
endpoint must still return real scores (recomputed / store-backed) instead of
500ing. Covers the owner requirement: "provider/quota/cache failure must degrade
gracefully, no crash, clear status".
"""

from __future__ import annotations

from app.modules.documents.application import job_fit_batch_service

from tests.documents_utils import make_student
from tests.integration.test_cv_job_fit import _build_strong_cv, _create_job


class _ReadFailingRedis:
    """Redis whose GET always errors (outage / connection reset on read)."""

    async def get(self, key: str) -> str | None:
        raise ConnectionError("redis down")

    async def setex(self, key: str, ttl: int, value: str) -> None:
        raise ConnectionError("redis down")


class _WriteFailingRedis:
    """Redis that reads (always miss) but errors on SET."""

    async def get(self, key: str) -> str | None:
        return None

    async def setex(self, key: str, ttl: int, value: str) -> None:
        raise ConnectionError("redis down")


async def test_batch_fit_survives_redis_read_failure(db_session) -> None:
    _user, student = await make_student(db_session)
    await _build_strong_cv(db_session, student)
    job_id = await _create_job(db_session)

    scores = await job_fit_batch_service.batch_fit_for_jobs(
        db_session, _ReadFailingRedis(), principal=student, job_ids=[job_id]
    )

    # Degraded to "always miss" -> recomputed from the store, no exception.
    assert str(job_id) in scores
    assert 0 <= scores[str(job_id)]["score"] <= 100


async def test_batch_fit_survives_redis_write_failure(db_session) -> None:
    _user, student = await make_student(db_session)
    await _build_strong_cv(db_session, student)
    job_id = await _create_job(db_session)

    scores = await job_fit_batch_service.batch_fit_for_jobs(
        db_session, _WriteFailingRedis(), principal=student, job_ids=[job_id]
    )

    assert str(job_id) in scores
    assert 0 <= scores[str(job_id)]["score"] <= 100


async def test_batch_fit_with_no_redis_at_all(db_session) -> None:
    _user, student = await make_student(db_session)
    await _build_strong_cv(db_session, student)
    job_id = await _create_job(db_session)

    # redis=None (cache disabled entirely) must also work store-backed.
    scores = await job_fit_batch_service.batch_fit_for_jobs(
        db_session, None, principal=student, job_ids=[job_id]
    )

    assert str(job_id) in scores
