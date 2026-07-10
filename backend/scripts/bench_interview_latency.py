"""Opt-in, real-call latency + judge benchmark for the mock-interview AI tiers.

This is NOT part of the offline CI gate. It spends real model calls, so it is
gated on ``AI_REAL_CALLS_ENABLED=true`` and honours
``AI_MAX_REAL_CALLS_PER_TEST_RUN`` (``.claude/rules/ai.md`` §18). Latency uses only
the interview alias (a cheap Gemini-class alias by default); the judge pass uses
only the isolated eval alias. Neither is ever a premium alias. It reports against
the §10.4 SLOs (P95 first-token ≤ 3s, P95 total ≤ 15s).

Two sections, both capped by the SAME real-call budget:

1. LATENCY sweep — swept per LOCALE (``vi`` then ``en``):
   - time-to-first-question — the opening interviewer turn (streamed);
   - per-turn p50/p95        — first-token AND total, over a few simulated turns;
   - report latency          — the post-session coaching report (non-streamed).
   Time-to-first-question and per-turn p50/p95 are reported per locale, plus a
   combined SLA view across both locales.

2. JUDGE pass — runs the gold judge sets
   (``datasets/mock_interview_turn/judge.jsonl`` +
   ``datasets/mock_interview_report/judge.jsonl``) through the isolated LLM judge
   and reports pass-rate (good rows scored ≥ min, bad rows scored ≤ max) plus a
   fabrication catch-rate (fabrication-labelled bad rows the judge caught). This
   measures grounding-faithfulness + fabrication catch across languages, including
   the code-switched + English rows.

Output is a single JSON object keyed by the INTERNAL ALIAS + LOCALE only. It never
contains a provider name, concrete model id, API key, base URL, or token counts.

Usage::

    # Offline default: prints a skipped report and exits 0 (spends nothing).
    uv run python -m scripts.bench_interview_latency

    # Real run (cheap aliases only), capped by AI_MAX_REAL_CALLS_PER_TEST_RUN:
    AI_REAL_CALLS_ENABLED=true uv run python -m scripts.bench_interview_latency \\
        --turns 3 --judge-rows 6

Latency calls go through the AI gateway factory (``get_provider_for_alias``); the
judge pass goes through ``app.ai.evaluation.judge`` (the isolated eval alias) —
never a direct provider SDK call.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import time
from pathlib import Path
from typing import Any

from app.ai.evaluation.harness import DATASETS_DIR
from app.ai.gateway import runtime_config
from app.ai.gateway.base import AIMessage
from app.ai.gateway.factory import get_provider_for_alias, real_provider_active
from app.ai.gateway.output_guard import scrub_text
from app.ai.prompts.mock_interview import v1 as prompts
from app.core.config import get_settings
from app.modules.mock_interview.application import caps

# §10.4 SLOs (docs/AI_PRODUCT_SPEC.md).
_FIRST_TOKEN_P95_TARGET_MS = 3000
_TOTAL_P95_TARGET_MS = 15000

_LOCALES = ("vi", "en")

_GROUNDING_EN: dict[str, Any] = {
    "locale": "en",
    "focus": "technical",
    "difficulty": "intermediate",
    "job": {
        "title": "Backend Engineer",
        "company_name": "Acme Tech",
        "requirements": [
            "Design and build REST APIs in Python",
            "Optimize PostgreSQL queries for performance",
            "Deploy services with Docker and Kubernetes",
        ],
        "required_skills": ["Python", "PostgreSQL", "Docker", "REST APIs"],
    },
    "cv": {
        "title": "Software Engineering CV",
        "highlights": [
            "Built a recommender system in Python serving thousands of users",
            "Optimized SQL queries and cut request latency by 40%",
        ],
        "skills": ["Python", "SQL", "Docker", "FastAPI"],
    },
    "matched_skills": ["Python", "Docker", "SQL"],
    "gaps": ["Kubernetes", "system design at scale"],
}

# Vietnamese grounding keeps the same English tech terms (REST API / Docker) —
# code-switching is the product norm (prompt v2).
_GROUNDING_VI: dict[str, Any] = {
    "locale": "vi",
    "focus": "technical",
    "difficulty": "intermediate",
    "job": {
        "title": "Kỹ sư Backend",
        "company_name": "Acme Tech",
        "requirements": [
            "Thiết kế và xây dựng REST API bằng Python",
            "Tối ưu truy vấn PostgreSQL",
            "Triển khai dịch vụ với Docker và Kubernetes",
        ],
        "required_skills": ["Python", "PostgreSQL", "Docker", "REST API"],
    },
    "cv": {
        "title": "CV Kỹ thuật phần mềm",
        "highlights": [
            "Xây dựng hệ thống gợi ý bằng Python phục vụ hàng nghìn người dùng",
            "Tối ưu truy vấn SQL, giảm độ trễ 40%",
        ],
        "skills": ["Python", "SQL", "Docker", "FastAPI"],
    },
    "matched_skills": ["Python", "Docker", "SQL"],
    "gaps": ["Kubernetes", "system design ở quy mô lớn"],
}

# Canned candidate answers used to drive successive interviewer turns (per locale).
_CANNED_ANSWERS_EN = [
    "I built a recommender system in Python for a student club; I owned the data "
    "pipeline and the model training end to end.",
    "I measured it with offline precision on a held-out set, then a small A/B test "
    "with real users before shipping.",
    "I have not used Kubernetes much, but I am comfortable with Docker and would "
    "start by learning deployments and services.",
    "One tricky bug was an N+1 query; I found it by profiling and fixed it by "
    "batching the loads.",
]
_CANNED_ANSWERS_VI = [
    "Em xây dựng một hệ thống recommender bằng Python cho câu lạc bộ sinh viên; em "
    "phụ trách toàn bộ data pipeline và việc train model.",
    "Em đánh giá bằng precision offline trên tập held-out, rồi chạy một A/B test nhỏ "
    "với người dùng thật trước khi deploy.",
    "Em chưa dùng Kubernetes nhiều, nhưng em quen với Docker và sẽ bắt đầu bằng việc "
    "học deployment và service.",
    "Một bug khó là N+1 query; em phát hiện qua profiling và fix bằng cách batch các "
    "lần load.",
]


def _grounding_for(locale: str) -> dict[str, Any]:
    return _GROUNDING_VI if (locale or "en").startswith("vi") else _GROUNDING_EN


def _answers_for(locale: str) -> list[str]:
    return _CANNED_ANSWERS_VI if (locale or "en").startswith("vi") else _CANNED_ANSWERS_EN


def _kickoff(locale: str) -> str:
    if (locale or "en").startswith("vi"):
        return "Bắt đầu buổi phỏng vấn nhé."
    return "Let's begin the interview."


class _Budget:
    """Shared real-call budget; ``take()`` returns False once the cap is spent."""

    def __init__(self, cap: int) -> None:
        self.cap = max(0, int(cap))
        self.used = 0

    def take(self) -> bool:
        if self.used < self.cap:
            self.used += 1
            return True
        return False


def _percentile(values: list[float], q: float) -> float | None:
    """Nearest-rank percentile (q in [0,1]); None for an empty sample."""

    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(q * len(ordered)))
    return round(ordered[rank - 1], 1)


async def _time_stream(
    provider: Any, messages: list[AIMessage]
) -> tuple[float | None, float | None, int]:
    """Stream one turn; return (first_token_ms, total_ms, scrubbed_char_count).

    On any failure returns (None, None, 0) without leaking the error text.
    """

    start = time.perf_counter()
    first_ms: float | None = None
    text_parts: list[str] = []
    try:
        async for chunk in provider.stream(
            messages,
            alias=get_settings().ai_interview_model_alias,
            temperature=0.7,
            max_tokens=caps.QUESTION_MAX_TOKENS,
        ):
            if chunk and first_ms is None:
                first_ms = (time.perf_counter() - start) * 1000.0
            if chunk:
                text_parts.append(chunk)
    except Exception:  # noqa: BLE001 — never leak provider error text
        return None, None, 0
    total_ms = (time.perf_counter() - start) * 1000.0
    scrubbed = scrub_text("".join(text_parts))
    return first_ms, round(total_ms, 1), len(scrubbed)


async def _time_report(
    provider: Any, grounding: dict[str, Any], locale: str
) -> tuple[float | None, int]:
    """Time the non-streamed coaching report; return (total_ms, char_count)."""

    system = prompts.build_report_system_prompt(locale)
    answers = _answers_for(locale)
    if locale.startswith("vi"):
        transcript = [
            "Interviewer: Kể cho tôi nghe về dự án recommender của bạn.",
            f"Candidate: {answers[0]}",
            "Interviewer: Bạn đánh giá nó như thế nào?",
            f"Candidate: {answers[1]}",
        ]
    else:
        transcript = [
            "Interviewer: Walk me through your recommender project.",
            f"Candidate: {answers[0]}",
            "Interviewer: How did you evaluate it?",
            f"Candidate: {answers[1]}",
        ]
    user = prompts.build_report_user_message(grounding, transcript)
    start = time.perf_counter()
    try:
        completion = await provider.complete(
            [
                AIMessage(role="system", content=system),
                AIMessage(role="user", content=user),
            ],
            alias=get_settings().ai_interview_model_alias,
            temperature=0.4,
            max_tokens=caps.REPORT_MAX_TOKENS,
        )
    except Exception:  # noqa: BLE001
        return None, 0
    total_ms = (time.perf_counter() - start) * 1000.0
    return round(total_ms, 1), len(scrub_text(completion.text))


async def _run_locale(
    provider: Any, *, locale: str, turns: int, budget: _Budget
) -> tuple[dict[str, Any], list[float], list[float]]:
    """Latency sweep for ONE locale; returns (metrics, ft_for_sla, total_for_sla)."""

    grounding = _grounding_for(locale)
    answers = _answers_for(locale)
    system = prompts.build_conversation_system_prompt(
        grounding, target_questions=caps.DEFAULT_TARGET_QUESTIONS
    )
    convo = [
        AIMessage(role="system", content=system),
        AIMessage(role="user", content=_kickoff(locale)),
    ]

    ttfq_ms: float | None = None
    opening_total_ms: float | None = None
    opening_chars = 0
    if budget.take():
        ttfq_ms, opening_total_ms, opening_chars = await _time_stream(provider, convo)
    convo.append(AIMessage(role="assistant", content="(opening question)"))

    ft_samples: list[float] = []
    total_samples: list[float] = []
    for i in range(max(0, turns)):
        if not budget.take():
            break
        convo.append(AIMessage(role="user", content=answers[i % len(answers)]))
        ft, tot, _ = await _time_stream(provider, convo)
        if ft is not None:
            ft_samples.append(ft)
        if tot is not None:
            total_samples.append(tot)
        convo.append(AIMessage(role="assistant", content="(next question)"))

    report_ms: float | None = None
    report_chars = 0
    if budget.take():
        report_ms, report_chars = await _time_report(provider, grounding, locale)

    metrics = {
        "locale": locale,
        "time_to_first_question_ms": ttfq_ms,
        "opening_total_ms": opening_total_ms,
        "opening_chars": opening_chars,
        "per_turn": {
            "samples": len(ft_samples),
            "first_token_p50_ms": _percentile(ft_samples, 0.50),
            "first_token_p95_ms": _percentile(ft_samples, 0.95),
            "total_p50_ms": _percentile(total_samples, 0.50),
            "total_p95_ms": _percentile(total_samples, 0.95),
        },
        "report_ms": report_ms,
        "report_chars": report_chars,
        "calls_made": budget.used,
    }
    ft_for_sla = [v for v in ([ttfq_ms] + ft_samples) if v is not None]
    total_for_sla = [v for v in ([opening_total_ms] + total_samples) if v is not None]
    return metrics, ft_for_sla, total_for_sla


def _load_judge_rows(family: str) -> list[dict[str, Any]]:
    path: Path = DATASETS_DIR / family / "judge.jsonl"
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _is_fabrication_row(row: dict[str, Any]) -> bool:
    rid = str(row.get("id") or "")
    return "fabricat" in rid or "invent" in rid


async def _run_judge(budget: _Budget, max_rows: int) -> dict[str, Any]:
    """Run gold judge rows through the isolated judge; report pass + fabrication catch.

    Round-robins the two families so both get coverage under a small cap. Uses the
    eval alias only (judge-model isolation). Never prints reasoning text.
    """

    from app.ai.evaluation.judge import judge_response

    families = ("mock_interview_turn", "mock_interview_report")
    fam_rows = {fam: _load_judge_rows(fam) for fam in families}
    interleaved: list[tuple[str, dict[str, Any]]] = []
    depth = max((len(v) for v in fam_rows.values()), default=0)
    for i in range(depth):
        for fam in families:
            if i < len(fam_rows[fam]):
                interleaved.append((fam, fam_rows[fam][i]))

    stats = {
        fam: {"attempted": 0, "passed": 0, "fab_attempted": 0, "fab_caught": 0}
        for fam in families
    }
    processed = 0
    for fam, row in interleaved:
        if processed >= max_rows or not budget.take():
            break
        processed += 1
        try:
            verdict = await judge_response(
                fam, row.get("context") or {}, str(row.get("response") or "")
            )
        except Exception:  # noqa: BLE001 — no verdict; the call was still spent
            continue
        expect = row.get("expect") or {}
        if "min_score" in expect:
            passed = verdict.score >= int(expect["min_score"])
        elif "max_score" in expect:
            passed = verdict.score <= int(expect["max_score"])
        else:
            passed = None
        s = stats[fam]
        s["attempted"] += 1
        if passed:
            s["passed"] += 1
        if _is_fabrication_row(row):
            s["fab_attempted"] += 1
            flags = [str(f).lower() for f in (verdict.flags or [])]
            if verdict.score <= 2 or "fabrication" in flags:
                s["fab_caught"] += 1

    def _rate(num: int, den: int) -> float | None:
        return round(num / den, 3) if den else None

    per_family = {}
    tot_att = tot_pass = tot_fab_att = tot_fab_caught = 0
    for fam, s in stats.items():
        per_family[fam] = {
            "attempted": s["attempted"],
            "passed": s["passed"],
            "pass_rate": _rate(s["passed"], s["attempted"]),
            "fabrication_attempted": s["fab_attempted"],
            "fabrication_caught": s["fab_caught"],
            "fabrication_catch_rate": _rate(s["fab_caught"], s["fab_attempted"]),
        }
        tot_att += s["attempted"]
        tot_pass += s["passed"]
        tot_fab_att += s["fab_attempted"]
        tot_fab_caught += s["fab_caught"]

    return {
        "judge_alias": runtime_config.current().eval_model_alias,
        "calls_made": budget.used,
        "attempted": tot_att,
        "pass_rate": _rate(tot_pass, tot_att),
        "fabrication_catch_rate": _rate(tot_fab_caught, tot_fab_att),
        "per_family": per_family,
    }


async def run(turns: int, judge_rows: int) -> dict[str, Any]:
    settings = get_settings()
    runtime_config.reset_to_bootstrap()
    alias = settings.ai_interview_model_alias

    if not settings.ai_real_calls_enabled or not real_provider_active():
        return {
            "skipped": True,
            "reason": "real calls disabled — set AI_REAL_CALLS_ENABLED=true with a "
            "configured interview alias to benchmark",
            "alias": alias,
            "locales": list(_LOCALES),
        }

    cap = int(settings.ai_max_real_calls_per_test_run)
    provider = get_provider_for_alias(alias)

    # Split the shared real-call cap: reserve up to half for the judge pass, keep
    # the rest for the per-locale latency sweep (the ``vi`` headline locale gets the
    # odd call). Both stay within the SAME AI_MAX_REAL_CALLS_PER_TEST_RUN budget.
    judge_reserve = min(max(0, judge_rows), cap // 2)
    latency_total = cap - judge_reserve
    en_cap = latency_total // 2
    vi_cap = latency_total - en_cap

    vi_budget = _Budget(vi_cap)
    en_budget = _Budget(en_cap)
    judge_budget = _Budget(judge_reserve)

    per_locale: dict[str, Any] = {}
    sla_ft: list[float] = []
    sla_total: list[float] = []
    for locale, lbudget in (("vi", vi_budget), ("en", en_budget)):
        metrics, ft, tot = await _run_locale(
            provider, locale=locale, turns=turns, budget=lbudget
        )
        per_locale[locale] = metrics
        sla_ft += ft
        sla_total += tot

    judge = await _run_judge(judge_budget, judge_reserve)

    # Live time-to-first-audio — only when the native realtime tier is on.
    live_note = (
        "native realtime tier disabled (ai_realtime_enabled=false); Live "
        "time-to-first-audio not measured by the text-tier bench"
    )
    if settings.ai_realtime_enabled and settings.gemini_api_key:
        live_note = (
            "native realtime tier enabled but the Live socket lives in the "
            "speech/live_relay layer; run the realtime relay's own probe to measure "
            "time-to-first-audio"
        )

    ft_p95_all = _percentile(sla_ft, 0.95)
    total_p95_all = _percentile(sla_total, 0.95)
    calls_made = vi_budget.used + en_budget.used + judge_budget.used

    return {
        "skipped": False,
        "alias": alias,
        "call_cap": cap,
        "calls_made": calls_made,
        "per_locale": per_locale,
        "judge": judge,
        "live_time_to_first_audio_ms": None,
        "live_note": live_note,
        "sla": {
            "first_token_p95_ms": ft_p95_all,
            "first_token_p95_target_ms": _FIRST_TOKEN_P95_TARGET_MS,
            "first_token_p95_ok": (
                ft_p95_all is not None and ft_p95_all <= _FIRST_TOKEN_P95_TARGET_MS
            ),
            "total_p95_ms": total_p95_all,
            "total_p95_target_ms": _TOTAL_P95_TARGET_MS,
            "total_p95_ok": (
                total_p95_all is not None and total_p95_all <= _TOTAL_P95_TARGET_MS
            ),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bench_interview_latency",
        description="Opt-in real-call latency + judge benchmark for the mock interview tiers.",
    )
    parser.add_argument(
        "--turns",
        type=int,
        default=2,
        help="Per-locale per-turn samples to attempt (bounded by the shared "
        "AI_MAX_REAL_CALLS_PER_TEST_RUN budget). Default: 2.",
    )
    parser.add_argument(
        "--judge-rows",
        type=int,
        default=6,
        help="Max gold judge rows to score (bounded by the shared real-call "
        "budget; up to half the cap is reserved for the judge pass). Default: 6.",
    )
    args = parser.parse_args(argv)
    report = asyncio.run(run(max(0, args.turns), max(0, args.judge_rows)))
    # JSON only — keyed by internal alias + locale, never provider/model/key/token.
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI shim
    raise SystemExit(main())
