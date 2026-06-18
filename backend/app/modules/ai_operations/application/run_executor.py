from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.agents import AgentTask, build_agent_registry
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
            run.status = "DONE"
            run.result = result
            run.provider = "deterministic"
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
