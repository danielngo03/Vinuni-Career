"""Resolve JD engine settings into an effective policy for the cascade."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings, get_settings


@dataclass(slots=True)
class JdEnginePolicy:
    max_bytes: int
    ocr_langs: str
    vision_enabled: bool
    vision_max_image_px: int
    vision_max_pages: int


def resolve_jd_policy(settings: Settings | None = None) -> JdEnginePolicy:
    s = settings or get_settings()
    return JdEnginePolicy(
        max_bytes=s.jd_max_upload_bytes,
        ocr_langs=s.jd_ocr_langs,
        vision_enabled=s.jd_vision_extraction_enabled,
        vision_max_image_px=s.jd_vision_max_image_px,
        vision_max_pages=s.jd_vision_max_pages,
    )
