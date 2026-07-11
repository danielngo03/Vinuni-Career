"""CLI entrypoint for the offline AI evaluation gate.

The actual harness (dataset loading, dispatch, threshold verdicts, and
reporting) lives in ``app.ai.evaluation.harness``; the runner + checker for
each task family lives in ``app.ai.evaluation.runners.{family}``. This module
is intentionally thin — it wires the CLI and re-exports the harness's public
names for backward compatibility (``tests/integration/test_eval_gate.py``
and any external script that does
``from app.ai.evaluation import run_eval; run_eval.TASK_FAMILIES`` etc. keep
working unchanged).

Run::

    uv run python -m app.ai.evaluation.run_eval --task-family all
    uv run python -m app.ai.evaluation.run_eval --task-family recommend_cv_for_job

Exit code is non-zero whenever the gate fails, so CI can block the PR.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from app.ai.evaluation.harness import (  # noqa: F401 — re-exported for backward compat
    CATEGORIES,
    HAPPY_PATH_THRESHOLD,
    HARD_100_CATEGORIES,
    MIN_RATE_CATEGORIES,
    TASK_FAMILIES,
    _category_verdict,
    _load_cases,
    _run_case,
    evaluate_family,
    render_report,
    run,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="run_eval",
        description="Offline AI evaluation gate (deterministic, no network).",
    )
    parser.add_argument(
        "--task-family",
        choices=(*TASK_FAMILIES, "all"),
        default="all",
        help="Which task family to evaluate (default: all). Choices: "
        + ", ".join((*TASK_FAMILIES, "all")),
    )
    args = parser.parse_args(argv)
    text, ok = asyncio.run(run(args.task_family))
    print(text)
    return 0 if ok else 1


if __name__ == "__main__":  # pragma: no cover - CLI shim
    sys.exit(main())
