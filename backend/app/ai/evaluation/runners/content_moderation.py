"""Eval runner + checker for the ``content_moderation`` family.

Exercises the real deterministic scanner
(``app.ai.safety.content_moderation.check_content``) — pure, no DB/network.
"""

from __future__ import annotations

import json
from typing import Any

from app.ai.evaluation.models import Probe
from app.ai.safety.content_moderation import check_content


async def run_case(case: dict[str, Any]) -> Probe:
    inp = case.get("input") or {}
    text = inp.get("text", "")
    result = check_content(text)
    payload = result.as_dict()
    return Probe(
        kind="content_moderation",
        blob=json.dumps(payload, ensure_ascii=False).lower(),
        data=payload,
    )


def check(key: str, exp: Any, probe: Probe) -> str | None:
    d = probe.data
    if key == "flagged":
        got = bool(d.get("flagged"))
        return None if got == bool(exp) else f"flagged expected {exp}, got {got}"
    if key == "policy_violation":
        got = bool(d.get("policy_violation"))
        return None if got == bool(exp) else (f"policy_violation expected {exp}, got {got}")
    if key == "category_contains":
        categories = {f.get("category") for f in d.get("findings") or []}
        return None if exp in categories else f"expected category {exp!r} in {categories!r}"
    if key == "category_excludes":
        categories = {f.get("category") for f in d.get("findings") or []}
        return (
            None
            if exp not in categories
            else (f"category {exp!r} must NOT be present, got {categories!r}")
        )
    if key == "finding_count_gte":
        n = len(d.get("findings") or [])
        return None if n >= int(exp) else f"finding_count expected >= {exp}, got {n}"
    if key == "matched_phrase_excludes":
        phrases = " ".join(f.get("matched_phrase", "") for f in d.get("findings") or [])
        return (
            None
            if str(exp).lower() not in phrases.lower()
            else (f"matched_phrase should never contain {exp!r} (bounded-span guarantee)")
        )
    if key == "no_crash":
        return None
    return None  # unknown / informational key
