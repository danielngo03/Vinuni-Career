"""API routes for teacher-owned YouTube transcript RAG pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.src.core.auth import DemoUser, require_roles
from backend.src.services.youtube_rag_pipeline import DEFAULT_OUTPUT_DIR, PipelineConfig, detect_source_type, run_youtube_rag_pipeline

try:
    from fastapi import APIRouter, Depends, HTTPException
except ImportError:  # pragma: no cover
    APIRouter = None  # type: ignore[assignment]
    Depends = None  # type: ignore[assignment]
    HTTPException = Exception  # type: ignore[assignment]


if APIRouter is not None:
    router = APIRouter(prefix="/agents/teacher-rag", tags=["teacher_rag"])

    @router.get("/health")
    def health() -> dict[str, str]:
        return {"agent": "teacher_rag", "status": "ok"}

    @router.post("/detect")
    def detect_source(payload: dict[str, Any], _user: DemoUser = Depends(require_roles("teacher"))) -> dict[str, str]:
        source_url = str(payload.get("source_url", "")).strip()
        if not source_url:
            raise HTTPException(status_code=422, detail="source_url is required.")
        return {"source_type": detect_source_type(source_url)}

    @router.post("/run")
    def run_pipeline(payload: dict[str, Any], user: DemoUser = Depends(require_roles("teacher"))) -> dict[str, Any]:
        try:
            languages = payload.get("languages", ["vi", "en"])
            if isinstance(languages, str):
                languages = [item.strip() for item in languages.split(",") if item.strip()]
            return run_youtube_rag_pipeline(
                PipelineConfig(
                    source_url=str(payload.get("source_url", "")).strip(),
                    output_dir=Path(str(payload.get("output_dir", DEFAULT_OUTPUT_DIR))),
                    teacher_user_id=user.user_id,
                    category=str(payload.get("category", "Uncategorized")).strip() or "Uncategorized",
                    course_title=str(payload.get("course_title", "")).strip() or None,
                    languages=tuple(str(item).strip() for item in languages if str(item).strip()),
                    chunk_size_words=int(payload.get("chunk_size_words", 420)),
                    overlap_words=int(payload.get("overlap_words", 100)),
                    keep_vtt=bool(payload.get("keep_vtt", False)),
                    force=bool(payload.get("force", False)),
                    sleep_seconds=float(payload.get("sleep_seconds", 2.0)),
                )
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
else:
    router = None
