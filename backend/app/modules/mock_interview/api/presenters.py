"""Presenters — ORM → student-safe dicts.

Strips ALL internal fields: ``provider_ref``, ``model_ref``, ``grounding_json``,
``grounding_version``, ``text_redacted``, and ``flagged`` (an internal safety
signal). The coaching report is passed through as-is because ``report_service``
already produced a leak-safe, score-free shape.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.modules.mock_interview.application import plan_service
from app.modules.mock_interview.domain.models import (
    MockInterviewSession,
    MockInterviewTurn,
)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def turn(row: MockInterviewTurn) -> dict[str, Any]:
    return {
        "seq": row.seq,
        "speaker": row.speaker,
        "text": row.text,
        "created_at": _iso(row.created_at),
    }


def _job_title(row: MockInterviewSession) -> str | None:
    """Read the (already leak-safe) job title from the frozen grounding.

    Avoids a cross-module join to the jobs table for the history list; the title
    is not sensitive and was captured at session start.
    """

    grounding = row.grounding_json
    if isinstance(grounding, dict):
        job = grounding.get("job")
        if isinstance(job, dict):
            title = job.get("title")
            return str(title) if title else None
    return None


def session_summary(row: MockInterviewSession) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "job_id": str(row.job_id),
        "job_title": _job_title(row),
        "cv_id": str(row.cv_profile_id) if row.cv_profile_id else None,
        "locale": row.locale,
        "modality": row.modality,
        "status": row.status,
        "started_at": _iso(row.started_at),
        "ended_at": _iso(row.ended_at),
        "duration_seconds": row.duration_seconds,
        "question_count": row.question_count,
        "has_report": row.report_json is not None,
        "created_at": _iso(row.created_at),
    }


def session_detail(
    row: MockInterviewSession, turns: list[MockInterviewTurn]
) -> dict[str, Any]:
    data = session_summary(row)
    data["share_opt_in"] = bool(row.share_opt_in)
    data["transcript"] = [turn(t) for t in turns]
    data["report"] = row.report_json
    # Leak-safe interview-plan progress: which competencies are covered / still to
    # cover (labels + counts only — no weights, question bank, ids, or scores).
    data["coverage"] = plan_service.coverage_summary(row.coverage_json)
    return data
