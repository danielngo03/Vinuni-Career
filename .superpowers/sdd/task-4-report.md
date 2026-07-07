# Task 4 Report — AiTaskRunner Instrumentation

## Goal
Instrument the single AI gateway chokepoint `AiTaskRunner` so every call records:
- an admin `AiOpsEvent` row (via `ops_recorder.record_ops_event`)
- upserts the daily rollup `AiUsageDaily`
- fires a best-effort Langfuse trace (via `langfuse_client.trace_call`)
without changing the existing PII-safe `ai_usage_log` write.

## Files Modified
- `backend/app/ai/gateway/task_runner.py` — main implementation
- `backend/app/core/metadata.py` — registered `ai_eval_samples` model (pre-existing schema gap causing teardown errors in tests that call `log_ai_usage_async`)
- `backend/app/modules/ai_assistant/application/tools/cv_ai.py` — threaded `org_id=principal.org_id` at the one call site that has a `Principal` in scope

## Files Created
- `backend/tests/ai/gateway/__init__.py`
- `backend/tests/ai/gateway/test_task_runner_instrumentation.py` — 6 tests

## Decisions Made

### Provider/model resolution
`_resolve_provider_model(alias)` reads `runtime_config.current().provider_route_chains[alias][0]` (first/active hop) — no DB call, falls back to `provider_routes` flat map, then `(None, None)`. This avoids any DB dependency on the hot path.

### Telemetry helper isolation
`_record_telemetry(...)` is a module-level async helper that:
1. Calls `trace_call(...)` (Langfuse — best-effort, swallowed on any error)
2. Calls `estimate_cost_usd_db(...)` (DB-backed pricing, falls back to alias estimator)
3. Builds `OpsEventInput` and calls `record_ops_event(...)` (already never-raises)
4. The outer wrapper catches all exceptions and logs at WARNING — telemetry never breaks the call path.

### Blocked path
Budget `check_async` is wrapped in try/except in both `complete` and `stream`. On `PaymentRequiredError`, a `status="blocked"` event is recorded before re-raising.

### Error path
Provider call failure records `status="error"` event before re-raising `AIUnavailableError`.

### stream() token counts
Streaming does not produce a final `AICompletion.usage` dict (chunks are raw strings), so `prompt_tokens` and `completion_tokens` are passed as `None` for stream ops events — this is noted in the `OpsEventInput` contract.

### org_id threading
- `cv_ai.py` interview_sim call: `org_id=principal.org_id` (principal in scope)
- `tool_loop.py::llm_stream_chunks`: no principal → `org_id=None` (platform-level)
- `translation_service.py`: no principal → `org_id=None`
- `rerank.py`: no principal → `org_id=None`

### ai_eval_samples schema fix
`app/ai/observability/eval_samples.py` defines `AiEvalSample` / `ai_eval_samples` table but was not imported in `app/core/metadata.py`. After `log_ai_usage_async` dynamically imports it, SQLAlchemy registers it on `Base.metadata`, causing `_clean_tables` in conftest to attempt `DELETE FROM ai_eval_samples` against a table that was never created. Fixed by adding the import to `metadata.py` (side-effect import pattern consistent with all other entries).

## Tests
- 6 new tests in `tests/ai/gateway/test_task_runner_instrumentation.py`
- Covers: ops event + usage log both written; correct provider/model/tokens/latency/status fields; error path; budget-blocked path; org_id=None backward compat; db=None no-crash
- Fake `FakeProvider` with known `prompt_tokens=42, completion_tokens=17`
- Patches target `app.ai.gateway.factory.get_provider_for_alias` and `app.ai.gateway.factory.real_provider_active` (where task_runner imports from locally at call time)
- Budget guard patched at `app.modules.ai_settings.application.budget_guard.check_async`

## Quality Gates
- `uv run ruff check app/ai/gateway/task_runner.py app/core/metadata.py app/modules/ai_assistant/application/tools/cv_ai.py` — clean
- `uv run mypy app/ai/gateway/task_runner.py app/core/metadata.py app/modules/ai_assistant/application/tools/cv_ai.py --ignore-missing-imports` — 0 errors in touched files (22 pre-existing errors in other files unchanged)
- `uv run pytest tests/ai/ tests/unit/test_ai_governance.py` — 40/40 passed

## Rollback
Remove `_record_telemetry` calls and `org_id` param from `__init__`. The existing `log_ai_usage_async` path is untouched and will continue working.

---

## Post-Commit Review Fixes (2026-07-07)

Four findings from code review of the gateway instrumentation commit were resolved:

**Important I — stream() finally block (task_runner.py)**
Wrapped the `_record_telemetry(...)` call in `stream()`'s `finally` block with its own `try/except Exception: pass`, matching the pattern already used for `log_ai_usage_async` directly above it. An exception inside a `finally` block would otherwise replace the original exception (e.g. `AIUnavailableError`) with the telemetry error.

**Important II — fragile test assertion (test_task_runner_instrumentation.py)**
Replaced `assert ev.provider is not None` with a deterministic monkeypatch of `app.ai.gateway.task_runner._resolve_provider_model` returning `("test_provider", "test-model-v1")`, then asserting the exact concrete values. The test no longer depends on `chat_default` being bootstrapped in the test environment's `runtime_config`.

**Minor B — stale docstring comment (langfuse_client.py)**
Updated the `trace_call` docstring and the inline metadata comment to state that `provider`/`model` are the concrete resolved provider identity and model ID (admin-only observability, §5.6), never surfaced to end users — replacing the inaccurate claim that they were "function-slot aliases".

**Minor C — wrong monkeypatch target (test_task_runner_instrumentation.py)**
Changed `test_complete_no_db_does_not_crash` patch target from `app.ai.gateway.task_runner.real_provider_active` to `app.ai.gateway.factory.real_provider_active` with `raising=True`. Since `complete()` imports `real_provider_active` fresh from `factory` at call time, the old target was silently a no-op.

**Quality gates after fixes:**
- `uv run pytest tests/ai/gateway/ -v` — 6/6 passed
- `uv run ruff check app/ai/gateway app/ai/observability tests/ai/gateway` — clean
- `uv run mypy app/ai/gateway app/ai/observability --ignore-missing-imports` — 0 errors
