from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.agents import AgentTask, build_agent_registry
from app.ai.extraction.gemini_document_cv import cv_extraction_to_text
from app.ai.extraction.schemas import CVExtraction
from app.modules.ai_operations.application.legacy_ai_service import embed_text, index_document
from app.modules.recruitment.infrastructure.models import CV
from app.platform.database.models.ai_runs import AIRun, AIRunEvent
from app.platform.database.session import SessionLocal

logger = logging.getLogger(__name__)
_registry = build_agent_registry()


def execute_ai_run(run_id: str) -> None:
    """Worker entry point for one persisted AI run."""
    with SessionLocal() as db:
        run = db.get(AIRun, run_id)
        if not run or run.status == "CANCELLED":
            return
        try:
            run.status = "RUNNING"
            run.started_at = datetime.now(UTC)
            db.commit()
            _emit_event(db, run_id, "run_started", {"run_type": run.run_type})
            db.commit()

            result = _dispatch_run_type(run)
            for step in result.get("steps", []):
                _emit_event(
                    db,
                    run_id,
                    "agent_step",
                    {
                        "agent": step.get("agent"),
                        "action": step.get("action"),
                        "summary": step.get("summary"),
                        "metadata": step.get("metadata", {}),
                    },
                )
            db.commit()

            db.refresh(run)
            if run.status == "CANCELLED":
                _emit_event(db, run_id, "run_cancelled", {"checkpoint": "before_result"})
                db.commit()
                return

            _emit_event(
                db,
                run_id,
                "result",
                {
                    "agent": result.get("agent"),
                    "confidence": result.get("confidence"),
                    "requires_human_review": result.get("requires_human_review"),
                },
            )
            _persist_run_side_effects(db, run, result)
            run.status = "DONE"
            run.result = result
            run.provider = _provider_for_result(result)
            run.model = str(result.get("output", {}).get("workforce_version", "workforce-v1"))
            run.prompt_tokens = _estimate_payload_tokens(run.run_metadata or {})
            run.completion_tokens = _estimate_payload_tokens(result)
            run.cost_usd = 0.0
            run.finished_at = datetime.now(UTC)
        except Exception as exc:  # noqa: BLE001
            logger.exception("AI run %s failed: %s", run_id, exc)
            db.refresh(run)
            if run.status == "CANCELLED":
                return
            run.status = "FAILED"
            run.error = str(exc)[:1000]
            run.finished_at = datetime.now(UTC)
            _emit_event(db, run_id, "error", {"error": run.error})
        finally:
            db.commit()


def _dispatch_run_type(run: AIRun) -> dict:
    payload = dict(run.run_metadata or {})
    if run.input_ref:
        payload.setdefault("input_ref", run.input_ref)
    result = _registry.execute(
        AgentTask(
            task_type=run.run_type,
            payload=payload,
            run_id=run.id,
            org_id=run.org_id,
            user_id=run.user_id,
        )
    )
    return result.to_dict()


def _persist_run_side_effects(db: Session, run: AIRun, result: dict) -> None:
    if run.run_type != "cv_extraction" or not run.input_ref:
        return
    prefix, _, cv_id = run.input_ref.partition(":")
    if prefix != "cv" or not cv_id:
        return

    cv = db.get(CV, cv_id)
    if not cv or cv.deleted_at is not None or cv.student_id != run.user_id:
        return

    output = result.get("output") if isinstance(result.get("output"), dict) else {}
    extraction_payload = output.get("extraction") if isinstance(output, dict) else None
    if not isinstance(extraction_payload, dict):
        return

    extraction = CVExtraction.model_validate(extraction_payload)
    raw_text = str(extraction_payload.get("raw_text") or "")
    rendered_text = cv_extraction_to_text(extraction) or raw_text
    masked_data = output.get("masked_data") if isinstance(output.get("masked_data"), dict) else {}
    normalized_skills = [
        str(skill)
        for skill in output.get("normalized_skills", [])
        if isinstance(skill, str) and skill.strip()
    ]

    cv.summary = extraction.summary or cv.summary
    cv.skills = normalized_skills or [skill.name for skill in extraction.skills]
    cv.education_history = [item.model_dump(exclude_none=True) for item in extraction.education]
    cv.work_experience = [item.model_dump(exclude_none=True) for item in extraction.experiences]
    cv.projects = [item.model_dump(exclude_none=True) for item in extraction.projects]
    cv.certificates = [{"name": item} for item in extraction.certifications]
    cv.parsed_data = {
        **(cv.parsed_data or {}),
        **extraction.model_dump(),
        "raw_text": raw_text,
        "raw_markdown": extraction.raw_markdown or rendered_text,
        "content_hash": _content_hash(raw_text or rendered_text),
        "last_analyzed_content_hash": _content_hash(raw_text or rendered_text),
        "analysis_stale": False,
        "last_ai_run_id": run.id,
        "last_ai_run_finished_at": datetime.now(UTC).isoformat(),
    }
    cv.masked_data = masked_data or cv.masked_data
    cv.embedding = embed_text(str(masked_data.get("text") or rendered_text or raw_text))
    index_document(
        document_id=cv.id,
        entity_type="cv",
        title=f"CV {cv.student_id}",
        body=str(masked_data.get("text") or rendered_text or raw_text),
        metadata={"student_id": cv.student_id, "is_primary": cv.is_primary},
    )


def _provider_for_result(result: dict) -> str:
    steps = result.get("steps")
    if isinstance(steps, list) and any(
        isinstance(step, dict)
        and step.get("action") == "llm_extractor"
        and not str(step.get("summary", "")).startswith("fallback:")
        for step in steps
    ):
        return "llm_gateway"
    return "deterministic"


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


def _emit_event(
    db: Session,
    run_id: str,
    event_type: str,
    payload: dict,
) -> None:
    max_sequence = db.scalar(
        select(func.max(AIRunEvent.sequence)).where(AIRunEvent.run_id == run_id)
    )
    sequence = int(max_sequence) + 1 if max_sequence is not None else 0
    db.add(
        AIRunEvent(
            run_id=run_id,
            sequence=sequence,
            event_type=event_type,
            payload=payload,
        )
    )
    db.flush()


def _estimate_payload_tokens(payload: dict) -> int:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return max(1, (len(serialized) + 3) // 4)
