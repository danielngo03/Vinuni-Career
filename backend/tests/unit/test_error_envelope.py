"""Error envelope shape and no-leak behavior."""

from __future__ import annotations

from app.bootstrap.errors import register_exception_handlers
from app.bootstrap.middleware import RequestIdMiddleware
from app.shared.exceptions import PermissionDeniedError
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _app_with_routes() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)
    register_exception_handlers(app)

    @app.get("/boom")
    async def boom() -> dict:
        raise PermissionDeniedError()

    @app.get("/crash")
    async def crash() -> dict:
        raise RuntimeError("internal secret detail provider=openrouter model=gpt-4")

    return app


def test_app_error_envelope() -> None:
    with TestClient(_app_with_routes()) as client:
        resp = client.get("/boom")
    assert resp.status_code == 403
    err = resp.json()["error"]
    assert err["code"] == "PERMISSION_DENIED"
    assert set(err.keys()) == {"code", "message", "details", "request_id"}
    assert err["request_id"]


def test_unhandled_error_does_not_leak_internals() -> None:
    with TestClient(_app_with_routes(), raise_server_exceptions=False) as client:
        resp = client.get("/crash")
    assert resp.status_code == 500
    err = resp.json()["error"]
    assert err["code"] == "INTERNAL_ERROR"
    # Friendly message only; no provider/model/stacktrace leakage.
    blob = str(err).lower()
    assert "openrouter" not in blob
    assert "gpt-4" not in blob
    assert "runtimeerror" not in blob


def test_not_found_envelope() -> None:
    with TestClient(_app_with_routes()) as client:
        resp = client.get("/missing")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
