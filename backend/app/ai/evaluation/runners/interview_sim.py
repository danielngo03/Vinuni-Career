"""Eval runner + checker for the ``interview_sim`` family.

Mirrors the deterministic fallback path of ``_start_interview_sim`` (the
opening question + tip for a mock interview) — all cases run offline.
"""

from __future__ import annotations

import json
from typing import Any

from app.ai.evaluation.models import Probe
from app.ai.safety.input_guard import sanitize_instruction


def _sim_deterministic_result(role: str, round_type: str) -> dict[str, Any]:
    """Mirror the deterministic fallback path from ``_start_interview_sim``."""
    safe_role, _ = sanitize_instruction(role or "general role")
    safe_role = (safe_role or "general role")[:100]
    round_labels = {
        "screening": "initial HR screening",
        "technical": "technical interview",
        "behavioral": "behavioral (STAR-method) interview",
        "final": "final-round leadership interview",
    }
    # Normalise round — invalid rounds fall back to "screening"
    norm_round = round_type.lower() if round_type else "screening"
    if norm_round not in round_labels:
        norm_round = "screening"
    return {
        "ok": True,
        "role": safe_role,
        "round": norm_round,
        "question": (
            "Tell me about yourself and why you are interested in this "
            f"{safe_role} position."
        ),
        "tip": (
            "Use the Present-Past-Future structure: who you are now, "
            "your relevant experience, and why this role."
        ),
        "ai_available": False,
    }


async def run_case(case: dict[str, Any]) -> Probe:
    """Run an interview_sim eval case using the deterministic offline path."""
    inp = case.get("input") or {}
    role = inp.get("role") or ""
    round_type = inp.get("round") or "screening"
    result = _sim_deterministic_result(role, round_type)
    blob = json.dumps(result, ensure_ascii=False).lower()
    return Probe(kind="sim", blob=blob, result=result)


def check(key: str, exp: Any, probe: Probe) -> str | None:
    """Assertion checks for interview_sim probes."""
    result = probe.result or {}
    if key == "degrades_to_deterministic":
        is_det = not result.get("ai_available", True)
        return None if is_det == bool(exp) else (
            "degrades_to_deterministic expected "
            f"{exp}, got ai_available={result.get('ai_available')}"
        )
    if key == "no_crash":
        return None  # reaching here means no exception was raised
    return None  # unknown/informational key
