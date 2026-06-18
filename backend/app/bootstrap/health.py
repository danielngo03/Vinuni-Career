from __future__ import annotations

from fastapi import APIRouter

from app.shared.config import settings

router = APIRouter()


@router.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name, "env": settings.app_env}
