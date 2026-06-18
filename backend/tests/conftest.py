from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key-with-enough-length")
os.environ.setdefault("ENFORCE_RBAC", "false")
os.environ.setdefault("LLM_PROVIDER", "offline")
os.environ.setdefault("LLM_PROVIDER_CHAIN", "offline")
os.environ.setdefault("EMBEDDING_PROVIDER_CHAIN", "offline")
os.environ.setdefault("RERANK_PROVIDER", "offline")
os.environ.setdefault("INTERNAL_SERVICE_TOKEN", "test-internal-service-token")

from app.main import app  # noqa: E402
from app.platform.cache.factory import get_cache  # noqa: E402
from app.platform.database import models  # noqa: E402,F401
from app.platform.database.session import Base, engine  # noqa: E402
from app.platform.search.factory import get_search_client  # noqa: E402


@pytest.fixture(autouse=True)
def reset_database():
    get_cache.cache_clear()
    get_search_client.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    shutil.rmtree(Path(".data"), ignore_errors=True)


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "owner@example.com",
            "password": "StrongPass123!",
            "full_name": "Platform Owner",
        },
    )
    assert response.status_code == 201
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "StrongPass123!"},
    )
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}
