"""Health and readiness endpoint tests (no Redis / no Postgres required)."""

from __future__ import annotations

from app.main import app
from fastapi.testclient import TestClient


def test_health_always_ok() -> None:
    with TestClient(app) as client:
        resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["status"] == "ok"
    assert "X-Request-ID" in resp.headers


def test_ready_reports_checks() -> None:
    with TestClient(app) as client:
        resp = client.get("/api/v1/ready")
    # DB (SQLite) is up; Redis is optional -> ready or degraded, never 503 here.
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] in {"ready", "degraded"}
    assert data["checks"]["database"] == "ok"
