"""Eval runner + checker for the ``fraud_detection`` family.

Exercises the real deterministic rule engine
(``app.ai.safety.fraud_detection.assess_fraud_signals``) — pure, no DB/network.
"""

from __future__ import annotations

import json
from typing import Any

from app.ai.evaluation.models import Probe
from app.ai.safety.fraud_detection import assess_fraud_signals


async def run_case(case: dict[str, Any]) -> Probe:
    inp = case.get("input") or {}
    signals = inp.get("signals")
    result = assess_fraud_signals(signals)
    payload = result.as_dict()
    return Probe(
        kind="fraud_detection",
        blob=json.dumps(payload, ensure_ascii=False).lower(),
        data=payload,
    )


def check(key: str, exp: Any, probe: Probe) -> str | None:
    d = probe.data
    if key == "risk_level":
        got = d.get("risk_level")
        return None if got == exp else f"risk_level expected {exp!r}, got {got!r}"
    if key == "requires_human_review":
        got = bool(d.get("requires_human_review"))
        return None if got == bool(exp) else (f"requires_human_review expected {exp}, got {got}")
    if key == "signal_contains":
        codes = {s.get("code") for s in d.get("signals") or []}
        return None if exp in codes else f"expected signal {exp!r} in {codes!r}"
    if key == "signal_excludes":
        codes = {s.get("code") for s in d.get("signals") or []}
        return None if exp not in codes else (f"signal {exp!r} must NOT be present, got {codes!r}")
    if key == "signal_count":
        n = len(d.get("signals") or [])
        return None if n == int(exp) else f"signal_count expected {exp}, got {n}"
    if key == "risk_score_lte":
        score = float(d.get("risk_score") or 0.0)
        return None if score <= float(exp) else (f"risk_score expected <= {exp}, got {score}")
    if key == "no_crash":
        return None
    return None  # unknown / informational key
