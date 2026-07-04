"""Shared dataclasses for the offline AI eval harness.

Split out of ``run_eval.py`` (clean-code pass, 2026-07-01) so every
per-family runner module can depend on ``Probe`` without importing the
harness/CLI module (which would create a circular import: the harness
imports every runner to build its dispatch table).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Probe:
    """The normalized, user-facing outcome of running one eval case.

    Not every field is used by every family — ``kind`` tells the harness
    which family-specific ``check()`` function to dispatch to, and each
    runner only populates the fields it needs. ``data`` is the generic
    bucket for families that don't fit the older cv/rec/sim shape
    (ai_assistant_chat, jd_generation, knowledge_base_query, bias_detection).
    """

    kind: str  # "cv" | "rec" | "sim" | "chat" | "jd" | "kb" | "bias"
    blob: str = ""  # lower-cased JSON/text of the user-facing payload (leak scanning)
    diff: dict[str, Any] | None = None  # cv: the pending diff
    after_blob: str | None = None  # cv: lower-cased json of diff["after"]
    summary: str | None = None  # cv: user-facing summary line
    raised_code: str | None = None  # error code when the task degraded (AIUnavailableError)
    raised_message: str = ""
    result: dict[str, Any] | None = None  # rec/sim: full payload
    second: dict[str, Any] | None = None  # rec: re-run payload (determinism probe)
    input_cv_ids: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)  # generic computed fields


@dataclass(slots=True)
class CaseResult:
    family: str
    category: str
    case_id: str
    passed: bool
    failures: list[str]
    is_leakage: bool


@dataclass(slots=True)
class FamilyReport:
    family: str
    cases: list[CaseResult] = field(default_factory=list)

    def by_category(self, category: str) -> list[CaseResult]:
        return [c for c in self.cases if c.category == category]
