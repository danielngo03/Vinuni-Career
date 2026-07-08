"""AI prompt for the university operations deep-analysis narrative pass — v1.

The multi-agent operations analysis is DETERMINISTIC-FIRST: every sub-pass
computes privacy-safe aggregate signals from the owning module's read models
without any model call. A cheap text-LLM narrative is generated ONLY for a
LOW-CONFIDENCE pass (sparse / ambiguous data) to help a human interpret the
numbers with appropriate care — the "many layers, save tokens" pattern
(``docs/AI_PRODUCT_SPEC.md`` §4.2).

The model receives ONLY the aggregate signals already computed by the
deterministic pass (counts / bands / labels). It never receives student or
candidate PII, raw CV text, provider/model identity, or token/cost internals,
and it must NOT invent any number or fact that is not in the provided signals —
it only phrases them in plain language. Output is advisory; the human keeps
final say.
"""

from __future__ import annotations

import json

PROMPT_VERSION = 1

# English by convention (.claude/rules/ai.md) — output language is controlled by
# ``target_language`` at call time, not hardcoded here.
STATIC_SYSTEM_PROMPT = """\
You are an impartial university operations analyst. A deterministic system has \
already computed privacy-safe AGGREGATE signals about one area of a partner \
employer's hiring quality. Your only job is to write a short, careful, \
plain-language interpretation of those signals for busy university staff.

Rules:
1. Write 1-2 sentences (max 45 words total). No headings, no lists.
2. Use ONLY the numbers and labels in the provided signals. Do NOT invent, \
estimate, or extrapolate any figure, rate, name, or trend that is not given.
3. The data is sparse or ambiguous (this is why you were asked). Be measured: \
note uncertainty rather than overstating a conclusion.
4. Never mention a specific student, candidate, or person; never reference \
provider, model, prompt, tokens, cost, or confidence scores.
5. Frame everything as an advisory observation for a human to verify — never a \
decision or an instruction to act.
6. Respond with ONLY a JSON object: {"narrative": "<your 1-2 sentences>"}
"""


def build_user_message(*, area: str, signals: dict, target_language: str = "en") -> str:
    """Build the grounded user message from one pass's deterministic signals.

    ``signals`` is the exact privacy-safe aggregate dict the deterministic pass
    produced — the model may not go beyond it.
    """

    lang = "Vietnamese" if str(target_language).lower().startswith("vi") else "English"
    return (
        f"Analysis area: {area}\n"
        f"Aggregate signals (the only facts you may use):\n"
        f"{json.dumps(signals, ensure_ascii=False, sort_keys=True)}\n\n"
        f"Write the interpretation in {lang}. Return ONLY the JSON object."
    )
