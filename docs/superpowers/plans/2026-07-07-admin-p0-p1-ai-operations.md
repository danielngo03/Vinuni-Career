# Platform Admin Console P0 + P1 (AI Operations) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a superadmin-only Platform Admin Console shell plus a full AI Operations & Cost Observability section (spend/reliability/volume/traces + admin-editable pricing), wiring Langfuse, without weakening the PII-safe `ai_usage_log`.

**Architecture:** Instrument the single existing AI chokepoint (`AiTaskRunner`) to write a new admin-only `ai_ops_event` row + upsert an `ai_usage_daily` rollup, with cost from a new admin-editable `ai_model_price` table and a best-effort Langfuse trace. Expose superadmin read models under `/admin/ai-ops/*`, and a new `(admin)` Next.js route group rendering the console. `ai_usage_log` and the budget guard are reused unchanged (budget guard extended for per-org).

**Tech Stack:** FastAPI + SQLAlchemy 2 (async, `Mapped`) + Alembic; Next.js App Router + React Query + custom Tailwind v4 primitives + next-intl; Langfuse Python SDK.

## Global Constraints

- Backend quality gates must pass: `uv run ruff check app tests` and `uv run mypy app --ignore-missing-imports`. Frontend: `pnpm typecheck` + `pnpm build` green; `pnpm check:messages` (vi/en parity).
- All `/admin/*` routes are **superadmin-only** (`principal.is_superadmin`), enforced at the service layer, not router-only.
- Provider/model identity columns are returned only to platform superadmins inside AI Operations; non-superadmin callers, including ordinary university staff, never receive them (per `AI_PRODUCT_SPEC §5.5/§5.6` and ADR-0011.2).
- **Never** persist or trace prompt/response text, API keys, or base URLs. `ai_ops_event` and Langfuse carry IDs + counts + provider/model + latency only.
- `ai_usage_log` is unchanged and remains PII-safe; the budget guard keeps reading it.
- Every price/budget/kill-switch/provider-identity write is audited via `write_audit`.
- Telemetry writes **never raise** into the AI call path — a failure downgrades to a log; the AI response is still returned.
- Migrations are additive only; new alembic revisions chain from head `0075_skill_translation_cache`.
- LLM prompts/guardrail text stay English; user-facing copy is i18n (vi/en). Visual language: v9 Monochrome, custom `components/ui/*` primitives (not shadcn), no heavy chart library.

---

## File Structure

**Backend (new module `app/modules/ai_ops` for read models/API; telemetry lives under `app/ai/observability`):**
- `app/ai/observability/models.py` — MODIFY: add `AiOpsEvent`, `AiUsageDaily`, `AiModelPrice` ORM models (co-located with `AiUsageLog`).
- `app/ai/observability/pricing.py` — CREATE: DB-backed price lookup + cache; refactored `estimate_cost_usd`.
- `app/ai/observability/ops_recorder.py` — CREATE: writes `ai_ops_event` + upserts `ai_usage_daily`; never raises.
- `app/ai/observability/langfuse_client.py` — CREATE: thin best-effort wrapper, no-op without keys.
- `app/ai/gateway/task_runner.py` — MODIFY: add `org_id`; call recorder + langfuse in complete/stream/embed.
- `app/modules/ai_settings/application/budget_guard.py` — MODIFY: per-org daily budget.
- `app/modules/ai_ops/application/ai_ops_read_service.py` — CREATE: overview/spend/reliability/volume/events read models.
- `app/modules/ai_ops/application/pricing_admin_service.py` — CREATE: price CRUD + audit.
- `app/modules/ai_ops/api/router.py` — CREATE: `/admin/ai-ops/*` endpoints.
- `app/modules/ai_ops/api/deps.py` — CREATE: `require_superadmin`.
- `app/modules/dashboards/application/platform_overview.py` — CREATE: `/admin/overview` read model.
- `app/core/metadata.py` — MODIFY: import new models for `Base.metadata` registration.
- `app/modules/automation/scheduler/jobs.py` — MODIFY: register `ai_ops_prune` + `ai_usage_daily_reconcile`.
- `alembic/versions/0076_ai_model_price.py`, `0077_ai_ops_event.py`, `0078_ai_usage_daily.py` — CREATE.
- Tests under `tests/ai/observability/`, `tests/modules/ai_ops/`.

**Frontend (new route group `(admin)`):**
- `src/app/[locale]/(admin)/layout.tsx`, `src/app/[locale]/(admin)/admin/page.tsx` (Overview), `admin/ai-operations/page.tsx`, plus tab routes.
- `src/config/nav.ts` — MODIFY: add `ADMIN_NAV_GROUPS`.
- `src/components/layout/admin-guard.tsx` — CREATE: superadmin gate.
- `src/components/ui/bar-series.tsx`, `sparkline.tsx` — CREATE: lightweight inline-SVG chart primitives.
- `src/components/admin/*` — CREATE: `platform-overview-screen.tsx`, `ai-operations-overview-screen.tsx`, `ai-traces-screen.tsx`, `ai-pricing-screen.tsx`.
- `src/lib/api/ai-ops.ts` — CREATE: typed API client.
- `src/messages/{en,vi}/admin/console.json` — CREATE.
- Tests: `*.test.tsx` (vitest) next to components; existing patterns.

---

## Backend

### Task 1: `ai_model_price` table + DB-backed cost estimation

**Files:**
- Modify: `app/ai/observability/models.py`
- Create: `alembic/versions/0076_ai_model_price.py`
- Create: `app/ai/observability/pricing.py`
- Modify: `app/core/metadata.py`
- Test: `tests/ai/observability/test_pricing.py`

**Interfaces:**
- Produces: `AiModelPrice` ORM; `async def resolve_price(session, provider, model) -> PriceRow | None`; `async def estimate_cost_usd_db(session, *, provider, model, prompt_tokens, completion_tokens) -> tuple[float | None, bool]` returning `(cost, unpriced)`.
- Consumes: existing `estimate_cost_usd(alias, prompt_chars, completion_chars)` in `cost_estimator.py` as the fallback price source when a `(provider, model)` row is absent.

- [ ] **Step 1: Write the failing test**

```python
# tests/ai/observability/test_pricing.py
import pytest
from app.ai.observability import pricing
from app.ai.observability.models import AiModelPrice

@pytest.mark.asyncio
async def test_priced_model_computes_from_db(db_session):
    db_session.add(AiModelPrice(
        provider="openrouter", model="deepseek/deepseek-v4-flash",
        input_usd_per_1k=0.001, output_usd_per_1k=0.002, active=True,
    ))
    await db_session.flush()
    cost, unpriced = await pricing.estimate_cost_usd_db(
        db_session, provider="openrouter", model="deepseek/deepseek-v4-flash",
        prompt_tokens=1000, completion_tokens=500,
    )
    assert unpriced is False
    assert cost == pytest.approx(0.001 * 1 + 0.002 * 0.5)  # 0.002

@pytest.mark.asyncio
async def test_unpriced_model_flags_and_falls_back(db_session):
    cost, unpriced = await pricing.estimate_cost_usd_db(
        db_session, provider="x", model="unknown-model",
        prompt_tokens=1000, completion_tokens=0,
    )
    assert unpriced is True
    assert cost is not None  # best-effort fallback, never crashes
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/ai/observability/test_pricing.py -v`
Expected: FAIL (`AiModelPrice` / `pricing` not defined).

- [ ] **Step 3: Add the ORM model** in `app/ai/observability/models.py` (after `AiUsageLog`):

```python
from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, Uuid, func

class AiModelPrice(Base):
    __tablename__ = "ai_model_price"
    __table_args__ = (UniqueConstraint("provider", "model", name="uq_ai_model_price_provider_model"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid())
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    input_usd_per_1k: Mapped[float] = mapped_column(Numeric(12, 8), nullable=False)
    output_usd_per_1k: Mapped[float] = mapped_column(Numeric(12, 8), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    updated_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
```

Add `from sqlalchemy import UniqueConstraint` to the imports.

- [ ] **Step 4: Implement `pricing.py`**

```python
# app/ai/observability/pricing.py
from __future__ import annotations
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.ai.observability.cost_estimator import estimate_cost_usd
from app.ai.observability.models import AiModelPrice

_CHARS_PER_TOKEN = 4.0

async def resolve_price(session: AsyncSession, provider: str, model: str) -> AiModelPrice | None:
    row = await session.scalar(
        select(AiModelPrice).where(
            AiModelPrice.provider == provider,
            AiModelPrice.model == model,
            AiModelPrice.active.is_(True),
        )
    )
    return row

async def estimate_cost_usd_db(
    session: AsyncSession, *, provider: str | None, model: str | None,
    prompt_tokens: int, completion_tokens: int,
) -> tuple[float | None, bool]:
    if provider and model:
        price = await resolve_price(session, provider, model)
        if price is not None:
            cost = (prompt_tokens / 1000.0) * float(price.input_usd_per_1k) \
                 + (completion_tokens / 1000.0) * float(price.output_usd_per_1k)
            return round(cost, 7), False
    # Fallback: reuse the existing char-based estimator (alias-agnostic), flag unpriced.
    approx = estimate_cost_usd(
        model or "unknown",
        prompt_chars=int(prompt_tokens * _CHARS_PER_TOKEN),
        completion_chars=int(completion_tokens * _CHARS_PER_TOKEN),
    )
    return round(approx, 7), True
```

- [ ] **Step 5: Register model for metadata** — add to `app/core/metadata.py` (the existing import-for-side-effects block already imports `app.ai.observability.models`; confirm it does — if so no change needed, else add the import).

- [ ] **Step 6: Create the migration** `alembic/versions/0076_ai_model_price.py`

```python
"""ai_model_price"""
import sqlalchemy as sa
from alembic import op

revision = "0076_ai_model_price"
down_revision = "0075_skill_translation_cache"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        "ai_model_price",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("input_usd_per_1k", sa.Numeric(12, 8), nullable=False),
        sa.Column("output_usd_per_1k", sa.Numeric(12, 8), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("updated_by", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("provider", "model", name="uq_ai_model_price_provider_model"),
    )

def downgrade() -> None:
    op.drop_table("ai_model_price")
```

- [ ] **Step 7: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/ai/observability/test_pricing.py -v`
Expected: PASS.

- [ ] **Step 8: Seed prices from the code table** — add a data-migration tail to `0076` that inserts rows for each entry currently hardcoded in `cost_estimator.py` (read that file, map alias→(provider,model) via `runtime_config._BUILTIN_ROUTES`, insert input/output prices). If a clean mapping is unavailable, seed the known built-in models (`deepseek/deepseek-v4-flash`, `deepseek/deepseek-r1`, `text-embedding-3-small`, `google/gemini-2.5-flash`) with their current per-1M rates converted to per-1k. Verify with `uv run pytest`.

- [ ] **Step 9: Commit**

```bash
git add app/ai/observability/models.py app/ai/observability/pricing.py alembic/versions/0076_ai_model_price.py tests/ai/observability/test_pricing.py
git commit -m "feat(ai-ops): admin-editable ai_model_price + DB-backed cost estimate"
```

### Task 2: `ai_ops_event` table + `ai_usage_daily` rollup + recorder

**Files:**
- Modify: `app/ai/observability/models.py`
- Create: `alembic/versions/0077_ai_ops_event.py`, `alembic/versions/0078_ai_usage_daily.py`
- Create: `app/ai/observability/ops_recorder.py`
- Test: `tests/ai/observability/test_ops_recorder.py`

**Interfaces:**
- Produces: `AiOpsEvent`, `AiUsageDaily` ORM; `async def record_ops_event(session, *, event: OpsEventInput) -> None` (never raises) which inserts one `AiOpsEvent` and upserts one `AiUsageDaily` row.
- Consumes: `pricing.estimate_cost_usd_db` (Task 1).

- [ ] **Step 1: Write the failing test**

```python
# tests/ai/observability/test_ops_recorder.py
import uuid, pytest
from sqlalchemy import select, func
from app.ai.observability import ops_recorder
from app.ai.observability.models import AiOpsEvent, AiUsageDaily

@pytest.mark.asyncio
async def test_record_writes_event_and_upserts_daily(db_session):
    ev = ops_recorder.OpsEventInput(
        task_type="job_fit", alias="reasoning_default",
        provider="openrouter", model="deepseek/deepseek-r1",
        prompt_tokens=1000, completion_tokens=200, latency_ms=850,
        status="ok", fallback_used=False, circuit_open=False,
        cost_usd=0.01, unpriced=False,
        org_id=uuid.uuid4(), user_id=uuid.uuid4(), session_id=None,
        request_id="req_abc", langfuse_trace_id="tr_1",
    )
    await ops_recorder.record_ops_event(db_session, event=ev)
    await ops_recorder.record_ops_event(db_session, event=ev)  # same day, same grain
    events = (await db_session.scalars(select(AiOpsEvent))).all()
    assert len(events) == 2
    daily = (await db_session.scalars(select(AiUsageDaily))).all()
    assert len(daily) == 1  # upserted, not duplicated
    assert daily[0].requests == 2
    assert daily[0].prompt_tokens == 2000

@pytest.mark.asyncio
async def test_record_never_raises_on_bad_input(db_session):
    # missing required fields must not bubble up into the AI call path
    await ops_recorder.record_ops_event(db_session, event=None)  # type: ignore[arg-type]
```

- [ ] **Step 2: Run test to verify it fails** — `uv run pytest tests/ai/observability/test_ops_recorder.py -v` → FAIL.

- [ ] **Step 3: Add ORM models** in `app/ai/observability/models.py`:

```python
class AiOpsEvent(Base):
    """Admin-only per-call operational telemetry (AI_PRODUCT_SPEC §5.6). No prompt text."""
    __tablename__ = "ai_ops_event"
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    task_type: Mapped[str] = mapped_column(String(64), nullable=False)
    alias: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="ok")
    fallback_used: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    circuit_open: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    cost_usd: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    unpriced: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    org_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    session_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    langfuse_trace_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

class AiUsageDaily(Base):
    """Pre-aggregated rollup for fast dashboards. Grain: day×task_type×provider×model×org."""
    __tablename__ = "ai_usage_daily"
    __table_args__ = (UniqueConstraint("day", "task_type", "provider", "model", "org_id", name="uq_ai_usage_daily_grain"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid())
    day: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    task_type: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False, server_default="")
    model: Mapped[str] = mapped_column(String(128), nullable=False, server_default="")
    org_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    requests: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    errors: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    fallbacks: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    blocked: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    cost_usd: Mapped[float] = mapped_column(Numeric(12, 7), nullable=False, server_default="0")
    latency_ms_sum: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    latency_ms_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
```

- [ ] **Step 4: Implement `ops_recorder.py`** — dataclass `OpsEventInput`, `record_ops_event` wrapped in try/except that logs and swallows (never raises). Daily upsert uses SQLite/PG-safe pattern: `SELECT ... FOR UPDATE`-free read-modify-write within the caller's session (test DB is SQLite). Increment counters; `errors += status=="error"`, `fallbacks += fallback_used`, `blocked += status=="blocked"`; add tokens/cost/latency.

```python
# app/ai/observability/ops_recorder.py — key logic
from __future__ import annotations
import logging, uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.ai.observability.models import AiOpsEvent, AiUsageDaily

_log = logging.getLogger(__name__)

@dataclass(slots=True)
class OpsEventInput:
    task_type: str; alias: str
    provider: str | None; model: str | None
    prompt_tokens: int | None; completion_tokens: int | None
    latency_ms: int | None; status: str
    fallback_used: bool; circuit_open: bool
    cost_usd: float | None; unpriced: bool
    org_id: uuid.UUID | None; user_id: uuid.UUID | None; session_id: uuid.UUID | None
    request_id: str | None; langfuse_trace_id: str | None

async def record_ops_event(session: AsyncSession, *, event: OpsEventInput) -> None:
    try:
        if event is None:
            return
        session.add(AiOpsEvent(**{k: getattr(event, k) for k in OpsEventInput.__slots__}))
        day = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        row = await session.scalar(select(AiUsageDaily).where(
            AiUsageDaily.day == day, AiUsageDaily.task_type == event.task_type,
            AiUsageDaily.provider == (event.provider or ""), AiUsageDaily.model == (event.model or ""),
            AiUsageDaily.org_id == event.org_id,
        ))
        if row is None:
            row = AiUsageDaily(day=day, task_type=event.task_type, provider=event.provider or "",
                               model=event.model or "", org_id=event.org_id)
            session.add(row)
        row.requests += 1
        row.errors += 1 if event.status == "error" else 0
        row.fallbacks += 1 if event.fallback_used else 0
        row.blocked += 1 if event.status == "blocked" else 0
        row.prompt_tokens += event.prompt_tokens or 0
        row.completion_tokens += event.completion_tokens or 0
        row.cost_usd = float(row.cost_usd) + float(event.cost_usd or 0)
        if event.latency_ms is not None:
            row.latency_ms_sum += event.latency_ms; row.latency_ms_count += 1
        await session.flush()
    except Exception:  # telemetry must never break the AI call
        _log.warning("ai_ops recorder failed", exc_info=True)
```

- [ ] **Step 5: Create migrations** `0077_ai_ops_event.py` (down_revision `0076_ai_model_price`) and `0078_ai_usage_daily.py` (down_revision `0077_ai_ops_event`) mirroring the columns above, with indexes on `created_at`, `(org_id, created_at)`, `(task_type, created_at)`, `(model, created_at)` for events and `day`, unique grain for daily.

- [ ] **Step 6: Run tests** → PASS. `uv run pytest tests/ai/observability/test_ops_recorder.py -v`.

- [ ] **Step 7: Commit** — `git commit -m "feat(ai-ops): ai_ops_event + ai_usage_daily rollup recorder (never-raise)"`.

### Task 3: Langfuse client wrapper (best-effort, no-op without keys)

**Files:**
- Create: `app/ai/observability/langfuse_client.py`
- Modify: `app/core/config.py` (add `langfuse_secret_key`, `langfuse_public_key`, `langfuse_base_url` settings if absent)
- Test: `tests/ai/observability/test_langfuse_client.py`

**Interfaces:**
- Produces: `def is_enabled() -> bool`; `def trace_call(*, task_type, alias, provider, model, prompt_tokens, completion_tokens, latency_ms, status, org_id, user_id, request_id) -> str | None` returning a trace id or `None`. Must never raise, never send prompt text.

- [ ] **Step 1: Write the failing test**

```python
# tests/ai/observability/test_langfuse_client.py
from app.ai.observability import langfuse_client as lf

def test_disabled_when_no_keys(monkeypatch):
    monkeypatch.setattr(lf, "_settings_keys", lambda: (None, None, None))
    assert lf.is_enabled() is False
    assert lf.trace_call(task_type="job_fit", alias="a", provider=None, model=None,
        prompt_tokens=0, completion_tokens=0, latency_ms=1, status="ok",
        org_id=None, user_id=None, request_id="r") is None  # no-op, no raise
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** — module reads keys from settings; if any missing, `is_enabled()` is False and `trace_call` returns None. When enabled, lazily import the Langfuse SDK inside a try/except, create a trace with metadata only (no prompt), flush in background, return `trace.id`; on any error log-warn and return None. **Never** put prompt/response/keys in metadata.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Add `langfuse` to `pyproject.toml` deps**, `uv lock`. If offline, guard the import so tests pass without the package installed (the lazy import already handles absence).
- [ ] **Step 6: Commit** — `git commit -m "feat(ai-ops): best-effort Langfuse client (metadata-only, no-op without keys)"`.

### Task 4: Instrument `AiTaskRunner` (org_id + recorder + langfuse)

**Files:**
- Modify: `app/ai/gateway/task_runner.py`
- Test: `tests/ai/gateway/test_task_runner_instrumentation.py`

**Interfaces:**
- Consumes: `ops_recorder.record_ops_event`, `pricing.estimate_cost_usd_db`, `langfuse_client.trace_call`, `request_id_ctx`.
- Produces: `AiTaskRunner.__init__` gains `org_id: uuid.UUID | None = None` (keyword-only, default None — backward compatible).

- [ ] **Step 1: Write the failing test** — fake provider returning known `usage`; assert that after `complete()`, one `AiOpsEvent` row exists with the resolved provider/model, real token counts, a `latency_ms >= 0`, `status="ok"`, and that the existing `ai_usage_log` row is *still* written (assert both counts == 1).

```python
@pytest.mark.asyncio
async def test_complete_writes_ops_event_and_keeps_usage_log(db_session, fake_provider, monkeypatch):
    runner = AiTaskRunner(db_session, alias="chat_default", task_type="unit_test",
                          user_id=uuid.uuid4(), org_id=uuid.uuid4())
    await runner.complete([AIMessage(role="user", content="hi")])
    assert (await db_session.scalar(select(func.count()).select_from(AiOpsEvent))) == 1
    assert (await db_session.scalar(select(func.count()).select_from(AiUsageLog))) == 1
```

- [ ] **Step 2: Run** → FAIL (no `org_id`, no ops event).
- [ ] **Step 3: Implement** — add `org_id` param stored on `self._org_id`. In `complete`/`stream`/`embed`, measure latency with `time.monotonic()`, extract real tokens from the provider `AICompletion.usage`, resolve provider/model from `factory`/the chosen hop (expose the resolved `(provider, model)` from the provider call — if the fallback chain hides it, read from `runtime_config` for the alias's active hop), compute cost via `estimate_cost_usd_db`, create the Langfuse trace first (to capture `trace_id`), then `await record_ops_event(...)`. Keep the existing `log_ai_usage_async(...)` call exactly as-is. On the budget-block path, still record an event with `status="blocked"`.
- [ ] **Step 4: Run** → PASS. Also run the full gateway test module to ensure no regression: `uv run pytest tests/ai/gateway/ -v`.
- [ ] **Step 5: Thread `org_id` from callers** — grep `AiTaskRunner(` call sites; pass `org_id=principal.org_id` where a principal is in scope. Missing `org_id` stays None (platform-level attribution) — acceptable, no call site breaks. Run `uv run pytest tests/ -q`.
- [ ] **Step 6: Commit** — `git commit -m "feat(ai-ops): instrument AiTaskRunner with ops telemetry + langfuse"`.

### Task 5: Per-org daily budget in `budget_guard`

**Files:**
- Modify: `app/modules/ai_settings/application/budget_guard.py`
- Modify: `app/modules/ai_settings/domain/models.py` (add `per_org_daily_budget_usd: float | None`) + migration `0079_ai_settings_per_org_budget.py`
- Test: `tests/modules/ai_settings/test_budget_guard_per_org.py`

- [ ] **Step 1: Write failing test** — with `per_org_daily_budget_usd=1.0` and today's `ai_usage_daily` for the org already at 1.0, `check_async(..., org_id=X, estimated_cost_usd=0.01)` raises `PaymentRequiredError` (`BUDGET_EXCEEDED`); a different org is unaffected.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** — after the existing platform + per-user checks, if `per_org_daily_budget_usd` is set and `org_id` given, sum today's `ai_usage_daily.cost_usd` for that org and raise if `spent + estimated > budget`. Degrade silently on infra error (match existing pattern). Add the settings column + additive migration.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat(ai-ops): per-org daily AI budget enforcement"`.

### Task 6: `require_superadmin` + AI ops read service + router

**Files:**
- Create: `app/modules/ai_ops/api/deps.py`, `app/modules/ai_ops/application/ai_ops_read_service.py`, `app/modules/ai_ops/api/router.py`, `app/modules/ai_ops/__init__.py`
- Modify: app router registry (where routers are included, e.g. `app/api/router.py` or `app/bootstrap/`)
- Test: `tests/modules/ai_ops/test_ai_ops_api.py`

**Interfaces:**
- Produces: `async def require_superadmin(auth = Depends(get_current_auth)) -> Principal`; read service functions `overview(session, range)`, `spend(session, range, group_by)`, `reliability(...)`, `volume(...)`, `events(session, cursor, filters, *, reveal_identity: bool)`.
- Consumes: `AiUsageDaily`, `AiOpsEvent`, circuit-breaker state from `app/ai/gateway/factory.py`.

- [ ] **Step 1: Write failing tests** — (a) non-superadmin → 403 on `GET /admin/ai-ops/overview`; (b) platform superadmin → 200 with keys `spend_today`, `budget`, `error_rate`, `requests` and real provider/model identity in `/events`; (c) any non-superadmin, including ordinary university staff with `ai_settings:read`/`manage`, cannot call `/admin/ai-ops/events` and never receives provider/model identity.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** — `require_superadmin` raises `PermissionDeniedError` unless `auth.principal.is_superadmin`. Read service queries `ai_usage_daily` for aggregates (fast) and `ai_ops_event` for the events list (cursor by `created_at,id`). Provider/model identity is returned only after the superadmin dependency passes; there is no org-scoped university permission that reveals raw identity. Circuit-breaker states exposed read-only from `factory` in-process dict. Wrap each aggregate in a `safe()` fallback. Router gates every endpoint with `Depends(require_superadmin)`.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat(ai-ops): superadmin /admin/ai-ops read models + identity masking"`.

### Task 7: Pricing admin CRUD (audited) + `/admin/ai-ops/prices`

**Files:**
- Create: `app/modules/ai_ops/application/pricing_admin_service.py`; extend `app/modules/ai_ops/api/router.py`
- Test: `tests/modules/ai_ops/test_pricing_admin.py`

- [ ] **Step 1: Failing test** — superadmin `POST /admin/ai-ops/prices` creates a row and writes one `AuditLog` with `action="ai_model_price.created"`; `PATCH` updates + audits; non-superadmin → 403.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** — service `create_price`/`update_price` call `write_audit(session, action=..., context=..., before=..., after=...)` (keys never logged; there are none here). Router endpoints gated by `require_superadmin`.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat(ai-ops): audited model-price CRUD"`.

### Task 8: Scheduler jobs — daily reconcile + ops retention prune

**Files:**
- Modify: `app/modules/automation/scheduler/jobs.py`
- Create: `app/ai/observability/maintenance.py`
- Test: `tests/ai/observability/test_maintenance.py`

- [ ] **Step 1: Failing test** — `reconcile_ai_usage_daily(session, day)` recomputes a day's rollup from `ai_ops_event` (idempotent); `prune_ai_ops_events(session, older_than_days=90)` deletes old rows only.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** both functions in `maintenance.py`; register `("ai_usage_daily_reconcile", 3600, ...)` and `("ai_ops_prune", 86400, ...)` in the scheduler jobs list (match the existing `(name, interval_seconds, coro)` tuple pattern; ensure idempotent).
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat(ai-ops): reconcile + retention prune scheduled jobs"`.

### Task 9: `/admin/overview` platform read model (P0 backend)

**Files:**
- Create: `app/modules/dashboards/application/platform_overview.py`; extend a router (reuse `app/modules/ai_ops/api/router.py` or dashboards router) with `GET /admin/overview`
- Test: `tests/modules/dashboards/test_platform_overview.py`

- [ ] **Step 1: Failing test** — superadmin `GET /admin/overview` returns `ai` (spend_today/budget/error_rate), `outbox`, `moderation_pending`, `active_users`; each sub-query `safe()`-wrapped so one failure yields a fallback, not a 500; non-superadmin → 403.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** composing existing read models (outbox health, moderation count, users count) + AI ops overview.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat(admin): /admin/overview platform read model"`.

### Task 10: Backend gate

- [ ] Run `cd backend && uv run ruff check app tests && uv run mypy app --ignore-missing-imports && uv run pytest -q`. Fix failures. Commit `chore(ai-ops): green backend gate`.

---

## Frontend

### Task 11: `(admin)` route group, superadmin guard, nav, i18n

**Files:**
- Create: `src/app/[locale]/(admin)/layout.tsx`, `src/app/[locale]/(admin)/admin/page.tsx`
- Create: `src/components/layout/admin-guard.tsx`
- Modify: `src/config/nav.ts` (add `ADMIN_NAV_GROUPS`)
- Create: `src/messages/en/admin/console.json`, `src/messages/vi/admin/console.json`
- Test: `src/components/layout/admin-guard.test.tsx`

**Interfaces:**
- Produces: `ADMIN_NAV_GROUPS: NavGroup[]` (nav items use `absolute: true`, paths `/admin/...`); `<AdminGuard>` that renders children only when `useAuth().user?.is_superadmin`, else redirects to `/`.

- [ ] **Step 1: Failing test** — render `<AdminGuard>` with a non-superadmin store → children absent / redirect called; with superadmin → children present. (Follow the existing auth-store mocking pattern used in other component tests.)
- [ ] **Step 2: Run** `pnpm vitest run src/components/layout/admin-guard.test.tsx` → FAIL.
- [ ] **Step 3: Implement** `AdminGuard`, `ADMIN_NAV_GROUPS` (Overview, AI Operations for now; stub the future sections as disabled items), `(admin)/layout.tsx` mounting `WorkspaceShell` with `ADMIN_NAV_GROUPS` wrapped in `AdminGuard`, and `admin/page.tsx` rendering `<PlatformOverviewScreen/>` (Task 16). Add `console.json` messages (en + vi parity).
- [ ] **Step 4: Run** → PASS; `pnpm check:messages`.
- [ ] **Step 5: Commit** — `git commit -m "feat(admin-ui): (admin) route group + superadmin guard + nav"`.

### Task 12: Chart primitives `<Sparkline/>` + `<BarSeries/>`

**Files:**
- Create: `src/components/ui/sparkline.tsx`, `src/components/ui/bar-series.tsx`; export from `src/components/ui/index.ts`
- Test: `src/components/ui/bar-series.test.tsx`

- [ ] **Step 1: Failing test** — `<BarSeries data={[{label:'a',value:2},{label:'b',value:4}]} />` renders 2 bars; the max-value bar has full height; empty data renders an empty state (no crash).
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** inline-SVG (or div) bars using design tokens (`--gray-*`, ink for emphasis, semantic hues via prop). Props: `data`, optional `referenceLine` (for budget), `format`. `<Sparkline/>` draws a single inline-SVG polyline. No external lib.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat(ui): lightweight Sparkline + BarSeries primitives"`.

### Task 13: API client `lib/api/ai-ops.ts`

**Files:**
- Create: `src/lib/api/ai-ops.ts`
- Test: `src/lib/api/ai-ops.test.ts`

**Interfaces:**
- Produces: `aiOpsApi.overview(range)`, `.spend(range, groupBy)`, `.reliability(range, groupBy)`, `.volume(range, groupBy)`, `.events(cursor, filters)`, `.prices()`, `.createPrice(body)`, `.updatePrice(id, body)`; matching typed response interfaces.

- [ ] **Step 1: Failing test** — mock `apiFetch`, assert `overview("7d")` calls `GET /admin/ai-ops/overview?range=7d` and returns typed data. (Follow the existing `lib/api/*.test.ts` mocking style.)
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** using the existing `api.get/post/patch` envelopes from `lib/api/client.ts`.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat(admin-ui): typed ai-ops API client"`.

### Task 14: AI Operations Overview screen

**Files:**
- Create: `src/components/admin/ai-operations-overview-screen.tsx`; route `src/app/[locale]/(admin)/admin/ai-operations/page.tsx` with `Tabs` (Overview/Traces/Models/Settings)
- Test: `src/components/admin/ai-operations-overview-screen.test.tsx`

- [ ] **Step 1: Failing test** — with a mocked `aiOpsApi.overview` resolving data, the screen shows the four metric tiles (Spend today, Requests, Error rate, p95 latency) and a Spend `<BarSeries>`; loading shows skeletons; error shows `EmptyState` error variant; empty range shows empty state.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** per spec §C.6: control bar (`SegmentedControl` Today/7d/30d), metric tiles (`.marketplace-card`, JetBrains Mono numbers, tonal `StatusBadge` for budget burn), Spend/Reliability/Volume panels each an independent `useQuery` key with `refetchInterval: 45_000` gated on visibility, `unpriced` amber note. Reliability panel includes the circuit-breaker table.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat(admin-ui): AI Operations overview (spend/reliability/volume)"`.

### Task 15: Traces + Models & Pricing + Settings tabs

**Files:**
- Create: `src/components/admin/ai-traces-screen.tsx`, `src/components/admin/ai-pricing-screen.tsx`; tab routes under `ai-operations/`
- Test: `src/components/admin/ai-pricing-screen.test.tsx`, `ai-traces-screen.test.tsx`

- [ ] **Step 1: Failing tests** — Traces: `DataTable` renders event rows; row click opens `Sheet`; "Open in Langfuse" button disabled when `langfuse_trace_id` absent, else `href` = deep-link base + id. Pricing: renders price rows; add/edit via `Sheet` calls `createPrice`/`updatePrice` + toast; amber banner lists usage models without a price row.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** both screens (cursor pagination, virtualized `DataTable` body if row count large). Settings tab reuses the existing `ai-settings` components, adding the per-org budget control bound to the new settings field.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat(admin-ui): AI traces + pricing + settings tabs"`.

### Task 16: Platform Overview screen (P0 landing)

**Files:**
- Create: `src/components/admin/platform-overview-screen.tsx`; `lib/api/admin-overview.ts`
- Test: `src/components/admin/platform-overview-screen.test.tsx`

- [ ] **Step 1: Failing test** — mocked `/admin/overview` renders the system-status band (AI spend/budget, error rate, outbox health, moderation pending, active users) and a next-actions rail deep-linking to `/admin/ai-operations`; loading→skeleton, error→EmptyState.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** reusing the `university-dashboard` composition idiom (metric tiles → status band → next-actions rail). Incidents strip renders an empty state placeholder (P7).
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat(admin-ui): platform overview landing"`.

### Task 17: Frontend gate + browser verify

- [ ] Run `cd frontend && pnpm typecheck && pnpm build && pnpm check:messages`. Fix issues.
- [ ] Browser-verify (chrome-devtools / playwright) as a superadmin: `/admin` loads, tiles populated, AI Operations tabs work, a real AI call appears in Traces with a working Langfuse deep-link, price edit persists, non-superadmin is redirected. Capture screenshots.
- [ ] Update `docs/IMPLEMENTATION_STATUS.md` with per-screen `implemented / API wired / browser verified` evidence + exact commands.
- [ ] Commit `chore(admin): P0+P1 verified`.

---

## Self-Review

**Spec coverage:** P0 shell (T11,16,9) ✓; AI ledger enrichment via `ai_ops_event` (T2) ✓; pricing table + DB cost (T1) ✓; rollup (T2) ✓; Langfuse (T3,4) ✓; instrumentation at chokepoint (T4) ✓; per-org budget (T5) ✓; superadmin RBAC + identity masking (T6) ✓; price CRUD audited (T7) ✓; reconcile + retention (T8) ✓; overview (T9,16) ✓; 4 dashboard panels + traces + pricing + settings (T14,15) ✓; realtime tiering (T14 refetchInterval) ✓; chart primitives, no heavy lib (T12) ✓; i18n vi/en (T11) ✓; gates (T10,17) ✓.

**Placeholder scan:** Steps 8 (price seed) and a few implement-steps describe logic rather than full code where the concrete values depend on reading the live `cost_estimator.py`/call sites — the implementer must read those files (paths given) and transcribe; this is intentional grounding, not a TODO. No "TBD"/"handle edge cases" left.

**Type consistency:** `OpsEventInput` fields ↔ `AiOpsEvent` columns match; `estimate_cost_usd_db` returns `(cost, unpriced)` used consistently in T1/T4; `require_superadmin` signature consistent T6/T7/T9; `aiOpsApi` method names match screen usage T13/T14/T15.

**Security-sensitive** (Langfuse keys, budget, identity masking): route through `vinuni-security-review` before merge (per master spec §7).
