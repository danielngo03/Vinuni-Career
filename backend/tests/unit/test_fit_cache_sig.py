"""The Redis fit-cache must be self-validating: a cached badge is only returned
when the caller's content signature matches, so any CV/JD/scorer version change
is a miss (owner requirement 2026-07-06 — "recompute only when CV/JD changes").
Uses a tiny in-memory fake Redis; no real Redis needed."""
from __future__ import annotations

import uuid

import pytest
from app.ai.cv import fit_cache


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key: str):
        return self.store.get(key)

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self.store[key] = value


@pytest.mark.asyncio
async def test_hit_when_sig_matches() -> None:
    r = _FakeRedis()
    u, j = uuid.uuid4(), uuid.uuid4()
    await fit_cache.set_cached(r, u, j, {"score": 82}, sig="1:3:cvsig")
    assert await fit_cache.get_cached(r, u, j, sig="1:3:cvsig") == {"score": 82}


@pytest.mark.asyncio
async def test_miss_when_job_version_changed() -> None:
    r = _FakeRedis()
    u, j = uuid.uuid4(), uuid.uuid4()
    await fit_cache.set_cached(r, u, j, {"score": 82}, sig="1:3:cvsig")
    # job.version moved 3 -> 4
    assert await fit_cache.get_cached(r, u, j, sig="1:4:cvsig") is None


@pytest.mark.asyncio
async def test_miss_when_cv_library_changed() -> None:
    r = _FakeRedis()
    u, j = uuid.uuid4(), uuid.uuid4()
    await fit_cache.set_cached(r, u, j, {"score": 82}, sig="1:3:cvA")
    # a CV was edited/added/deleted -> different library signature
    assert await fit_cache.get_cached(r, u, j, sig="1:3:cvB") is None


@pytest.mark.asyncio
async def test_miss_when_scorer_version_changed() -> None:
    r = _FakeRedis()
    u, j = uuid.uuid4(), uuid.uuid4()
    await fit_cache.set_cached(r, u, j, {"score": 82}, sig="1:3:cvsig")
    # SCORER_VERSION bumped 1 -> 2
    assert await fit_cache.get_cached(r, u, j, sig="2:3:cvsig") is None


@pytest.mark.asyncio
async def test_miss_on_absent_key() -> None:
    r = _FakeRedis()
    assert await fit_cache.get_cached(r, uuid.uuid4(), uuid.uuid4(), sig="1:1:x") is None
