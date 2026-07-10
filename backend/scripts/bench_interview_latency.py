"""Opt-in, real-call latency benchmark for the mock-interview AI tiers.

This is NOT part of the offline CI gate. It spends real model calls, so it is
gated on ``AI_REAL_CALLS_ENABLED=true`` and honours
``AI_MAX_REAL_CALLS_PER_TEST_RUN`` (``.claude/rules/ai.md`` §18) — it only ever
uses the interview alias (a cheap Gemini-class alias by default) and never a
premium alias. It reports against the §10.4 SLOs (P95 first-token ≤ 3s, P95 total
≤ 15s).

It measures, purely from latency (never printing any model text, provider, model
id, or key):

- time-to-first-question  — the opening interviewer turn (streamed);
- per-turn p50/p95         — first-token AND total, over a few simulated turns;
- report latency           — the post-session coaching report (non-streamed);
- Live time-to-first-audio — ONLY if a native realtime tier is enabled; otherwise
                             reported as null with a note (the realtime socket
                             lives in the speech/live_relay layer, out of scope
                             for this text-tier bench).

Output is a single JSON object keyed by the INTERNAL ALIAS only. It never contains
a provider name, concrete model id, API key, base URL, or token counts.

Usage::

    # Offline default: prints a skipped report and exits 0 (spends nothing).
    uv run python -m scripts.bench_interview_latency

    # Real run (cheap interview alias only), capped by AI_MAX_REAL_CALLS_PER_TEST_RUN:
    AI_REAL_CALLS_ENABLED=true uv run python -m scripts.bench_interview_latency --turns 3

All calls go through the AI gateway factory (``get_provider_for_alias``) — never a
direct provider SDK call.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import time
from typing import Any

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

_GROUNDING: dict[str, Any] = {
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

# Canned candidate answers used to drive successive interviewer turns.
_CANNED_ANSWERS = [
    "I built a recommender system in Python for a student club; I owned the data "
    "pipeline and the model training end to end.",
    "I measured it with offline precision on a held-out set, then a small A/B test "
    "with real users before shipping.",
    "I have not used Kubernetes much, but I am comfortable with Docker and would "
    "start by learning deployments and services.",
    "One tricky bug was an N+1 query; I found it by profiling and fixed it by "
    "batching the loads.",
]


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


async def _time_report(provider: Any) -> tuple[float | None, int]:
    """Time the non-streamed coaching report; return (total_ms, char_count)."""

    system = prompts.build_report_system_prompt(_GROUNDING["locale"])
    transcript = [
        "Interviewer: Walk me through your recommender project.",
        f"Candidate: {_CANNED_ANSWERS[0]}",
        "Interviewer: How did you evaluate it?",
        f"Candidate: {_CANNED_ANSWERS[1]}",
    ]
    user = prompts.build_report_user_message(_GROUNDING, transcript)
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


async def run(turns: int) -> dict[str, Any]:
    settings = get_settings()
    runtime_config.reset_to_bootstrap()
    alias = settings.ai_interview_model_alias

    if not settings.ai_real_calls_enabled or not real_provider_active():
        return {
            "skipped": True,
            "reason": "real calls disabled — set AI_REAL_CALLS_ENABLED=true with a "
            "configured interview alias to benchmark",
            "alias": alias,
        }

    cap = int(settings.ai_max_real_calls_per_test_run)
    provider = get_provider_for_alias(alias)
    calls_made = 0

    # 1) Opening turn — time to first question (the headline metric). Reserve one
    #    call for the report if the cap allows it.
    reserve_report = 1 if cap >= 2 else 0
    system = prompts.build_conversation_system_prompt(
        _GROUNDING, target_questions=caps.DEFAULT_TARGET_QUESTIONS
    )
    opening_msgs = [
        AIMessage(role="system", content=system),
        AIMessage(role="user", content="Let's begin the interview."),
    ]
    ttfq_ms, opening_total_ms, opening_chars = await _time_stream(provider, opening_msgs)
    calls_made += 1

    # 2) Per-turn samples — cap-bounded.
    ft_samples: list[float] = []
    total_samples: list[float] = []
    convo = list(opening_msgs)
    convo.append(AIMessage(role="assistant", content="(opening question)"))
    turn_budget = max(0, min(turns, cap - calls_made - reserve_report))
    for i in range(turn_budget):
        convo.append(
            AIMessage(role="user", content=_CANNED_ANSWERS[i % len(_CANNED_ANSWERS)])
        )
        ft, tot, _ = await _time_stream(provider, convo)
        calls_made += 1
        if ft is not None:
            ft_samples.append(ft)
        if tot is not None:
            total_samples.append(tot)
        convo.append(AIMessage(role="assistant", content="(next question)"))

    # 3) Report latency — if budget remains.
    report_ms: float | None = None
    report_chars = 0
    if calls_made < cap:
        report_ms, report_chars = await _time_report(provider)
        calls_made += 1

    # 4) Live time-to-first-audio — only when the native realtime tier is on.
    live_ttfa_ms: float | None = None
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

    ft_p95 = _percentile(ft_samples, 0.95)
    total_p95 = _percentile(total_samples, 0.95)
    # The opening turn is itself a first-token sample for the SLA view.
    ft_for_sla = [v for v in ([ttfq_ms] + ft_samples) if v is not None]
    total_for_sla = [
        v for v in ([opening_total_ms] + total_samples) if v is not None
    ]
    ft_p95_all = _percentile(ft_for_sla, 0.95)
    total_p95_all = _percentile(total_for_sla, 0.95)

    return {
        "skipped": False,
        "alias": alias,
        "call_cap": cap,
        "calls_made": calls_made,
        "time_to_first_question_ms": ttfq_ms,
        "opening_total_ms": opening_total_ms,
        "opening_chars": opening_chars,
        "per_turn": {
            "samples": len(ft_samples),
            "first_token_p50_ms": _percentile(ft_samples, 0.50),
            "first_token_p95_ms": ft_p95,
            "total_p50_ms": _percentile(total_samples, 0.50),
            "total_p95_ms": total_p95,
        },
        "report_ms": report_ms,
        "report_chars": report_chars,
        "live_time_to_first_audio_ms": live_ttfa_ms,
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
        description="Opt-in real-call latency benchmark for the mock interview tiers.",
    )
    parser.add_argument(
        "--turns",
        type=int,
        default=2,
        help="How many per-turn samples to attempt (bounded by "
        "AI_MAX_REAL_CALLS_PER_TEST_RUN). Default: 2.",
    )
    args = parser.parse_args(argv)
    report = asyncio.run(run(max(0, args.turns)))
    # JSON only — keyed by internal alias, never provider/model/key/token.
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI shim
    raise SystemExit(main())
