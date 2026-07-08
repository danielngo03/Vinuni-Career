# Student AI — Phase 1: Energy Metering Backbone + Resilience — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Meter every value-affecting student LLM call against a masked, cost-weighted "AI energy" budget (weekly hard block + 3h soft warn, no daily), backed by a per-user account and the existing idempotent ledger, and make every AI entry point degrade safely when AI is disabled or the model errors — never fabricating, never charging on failure.

**Architecture:** The existing `ai_billable_usage` ledger (`app/ai/observability/billable_usage.py`) stays the append-only, idempotent, charge-on-success record. A NEW per-user `ai_energy_account` (O(1) read) holds the weekly window counter + non-resetting wallet balance; a NEW `energy_service` is the single choke point that (a) preflight-enforces the weekly hard cap and (b) on a successful, user-visible result decrements the account in the same transaction as the ledger write. `AiTaskRunner._record_billable` routes through `energy_service` so any op given a `UsageContext` meters automatically; ops that currently bypass the gateway (`cv/llm.py`, vision `httpx`) are wrapped with `enforce`/`charge` (and vision is moved onto the gateway provider). Daily enforcement (request-count + student USD) is removed. Energy is exposed to the student as a masked `%` via `GET /ai/energy/me`; tokens/USD stay superadmin-only.

**Tech Stack:** Python 3.12, FastAPI async, SQLAlchemy 2.x async, Alembic, Pydantic v2, PostgreSQL 16, pytest (offline/fake AI provider by default), Next.js 15 App Router + react-query (frontend meter).

> **CONVERGENCE UPDATE (2026-07-08):** The shared AI energy foundation was found already built & committed on `feat/partner-ai-overhaul` (module `app/ai/energy/` + migration `0084_ai_energy_accounts_and_usage_org` + shared `cv/llm.py` metering + frontend meter `e83b325`). This student work now lives on worktree `feat/student-ai-overhaul` based on that foundation. Therefore Tasks 1–5 below (build energy account/service/weights/migration, wire gateway, remove daily) are **SUPERSEDED by the shared foundation** — do not rebuild them. The REAL remaining Phase-1 work reduced to: consume the foundation at the STUDENT call sites (Task 6 — DONE: cover_letter/cv_ai/fit-explanation/interview_sim/chatbot metered, 223 tests green), the student header energy meter (Task 7 frontend — DONE), CV **vision** metering (Task 6a — in progress), resilience/no-fabrication (Task 8 — in progress), and the `0005 is_premium` migration fix (in progress). Consume the foundation via `app.ai.energy.service.enforce_energy` / `build_usage_context` / `charge_units` and `app.ai.energy.constants.unit_cost`.

## Global Constraints

- No AI provider/model/token/USD/latency/raw-confidence internals in any student-facing response, notification, export, or log outside the superadmin boundary (`.claude/rules/ai.md`, `.claude/rules/backend.md`). Student unit is masked **energy %** only.
- RBAC enforced in the service/application layer, not routers. Every write action creates audit data. No business logic in routers. No direct cross-module implementation imports — use interfaces/events/read models.
- Charge credits ONLY on a successful, user-visible result; `blocked`/`provider_failed`/`validation_failed`/`cached` record with `units_charged=0` and never bill (`billable_usage.py:12-15`). Idempotent via `make_idempotency_key`.
- Windows: **weekly = hard block**, **3h rolling = soft warn**, **NO daily** (remove both the request-count daily window and the student USD-daily budget). Keep platform/org USD budget as a superadmin safety net.
- All LLM calls go through the AI gateway (`AiTaskRunner`) — no direct provider SDK/`httpx` calls in domain modules. Unit tests use offline/fake providers; real calls opt-in, capped, cheap aliases only (`AI_REAL_CALLS_ENABLED`, `AI_MAX_REAL_CALLS_PER_TEST_RUN`).
- Every migration has upgrade + downgrade. Errors follow `docs/API_CONTRACTS.md`. Celery/idempotent-safe.
- Shared substrate with the partner AI overhaul: scope via `billing_scope`/`actor_persona`; do not fork the ledger.

---

## File Structure

**Create:**
- `backend/app/modules/billing/domain/energy_models.py` — `AiEnergyAccount`, `AiEnergyTransaction` ORM.
- `backend/app/modules/billing/application/energy_weights.py` — `FEATURE_* → base energy units` table (cost-calibrated) + `base_units_for(feature_key)`.
- `backend/app/modules/billing/application/energy_service.py` — `resolve_weekly_allowance`, `get_meter`, `enforce`, `charge`, `soft_warn_state`, exceptions.
- `backend/app/modules/billing/api/energy_router.py` — `GET /ai/energy/me`, `POST /ai/energy/topup`.
- `backend/alembic/versions/0084_ai_energy_account.py` — new tables + `(actor_user_id, created_at)` index on `ai_billable_usage` + `weekly_energy_units` plan-limit seed.
- `backend/app/ai/resilience.py` — `ai_capabilities()` / `AiCapability` degradation contract used by ops + frontend.
- Tests: `backend/tests/unit/test_energy_service.py`, `test_energy_weights.py`, `test_ai_resilience.py`; `backend/tests/integration/test_energy_api.py`, `test_ai_metering_wiring.py`, `test_daily_removed.py`.
- Frontend: `frontend/src/components/ai/energy-meter.tsx`, `frontend/src/lib/api/energy.ts`.

**Modify:**
- `backend/app/ai/gateway/task_runner.py:77-103` — route `_record_billable` through `energy_service.charge`.
- `backend/app/modules/ai_assistant/application/usage_service.py` — remove the daily window; keep weekly only as a legacy safety net or delete once energy covers chat (see Task 5).
- `backend/app/modules/ai_settings/application/budget_guard.py` + `backend/app/modules/billing/application/limit_facade.py` — remove student USD-daily quota; add `resolve_user_weekly_energy_units`.
- `backend/app/ai/extraction/adapters/vision.py:239` — move off raw `httpx` onto the gateway provider + meter.
- `backend/app/modules/opportunities/application/cover_letter_service.py`, `backend/app/modules/documents/application/cv_ai_service.py`, `backend/app/ai/cv/semantic_scorer.py` callers, `backend/app/ai/extraction/jd/cascade.py`, `backend/app/ai/cv/skill_translation.py`, interview-sim service — wrap with `enforce`/`charge`.
- `frontend/src/components/layout/public-auth-actions.tsx` — mount the energy meter in the header.

---

### Task 1: Energy data model + migration

**Files:**
- Create: `backend/app/modules/billing/domain/energy_models.py`
- Create: `backend/alembic/versions/0084_ai_energy_account.py`
- Test: `backend/tests/integration/test_energy_api.py` (schema smoke at end of file; model import + create_all)

**Interfaces:**
- Produces: `AiEnergyAccount(user_id: UUID pk, plan_weekly_units: int, week_window_start: datetime, week_units_used: int, wallet_balance_units: int, updated_at: datetime, version: int)`; `AiEnergyTransaction(id: UUID pk, user_id: UUID, kind: str['weekly_refill'|'purchase'|'charge'], units: int (signed), feature_key: str|None, billable_usage_id: UUID|None, created_at: datetime)`.

- [ ] **Step 1: Write the failing test** — `backend/tests/integration/test_energy_api.py`

```python
import uuid
import pytest
from datetime import datetime, timezone
from app.modules.billing.domain.energy_models import AiEnergyAccount, AiEnergyTransaction

@pytest.mark.asyncio
async def test_energy_account_roundtrip(db_session):
    acct = AiEnergyAccount(
        user_id=uuid.uuid4(),
        plan_weekly_units=1000,
        week_window_start=datetime.now(timezone.utc),
        week_units_used=0,
        wallet_balance_units=0,
    )
    db_session.add(acct)
    await db_session.flush()
    loaded = await db_session.get(AiEnergyAccount, acct.user_id)
    assert loaded.plan_weekly_units == 1000
    assert loaded.wallet_balance_units == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/integration/test_energy_api.py::test_energy_account_roundtrip -v`
Expected: FAIL — `ModuleNotFoundError: app.modules.billing.domain.energy_models`.

- [ ] **Step 3: Write the ORM model** — follow the existing `billing/domain/models.py` base-class + mixin conventions (soft-delete/`version` mixins, `Mapped[...]` typing, `__tablename__`).

```python
"""Per-user AI energy account + transaction ledger (student energy meter, WS-1)."""
from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base  # match the Base import used in billing/domain/models.py

class AiEnergyAccount(Base):
    __tablename__ = "ai_energy_account"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    plan_weekly_units: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    week_window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    week_units_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    wallet_balance_units: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

class AiEnergyTransaction(Base):
    __tablename__ = "ai_energy_transaction"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)  # weekly_refill|purchase|charge
    units: Mapped[int] = mapped_column(Integer, nullable=False)     # signed: +grant, -charge
    feature_key: Mapped[str | None] = mapped_column(String(48), nullable=True)
    billable_usage_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
```

> Confirm the exact `Base` import and column mixin style against `backend/app/modules/billing/domain/models.py` before writing — match it verbatim (some models use a shared `TimestampMixin`).

- [ ] **Step 4: Write the migration** `0084_ai_energy_account.py`

Model it on `backend/alembic/versions/0083_ai_billable_usage.py`. `upgrade()` creates both tables, adds `op.create_index("ix_ai_billable_usage_user_created", "ai_billable_usage", ["actor_user_id", "created_at"])`, and back-fills nothing. `downgrade()` drops the index + both tables. Set `down_revision = "0083"`.

- [ ] **Step 5: Run migration + test to verify pass**

Run: `cd backend && uv run alembic upgrade head && uv run pytest tests/integration/test_energy_api.py::test_energy_account_roundtrip -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/modules/billing/domain/energy_models.py backend/alembic/versions/0084_ai_energy_account.py backend/tests/integration/test_energy_api.py
git commit -m "feat(billing): ai_energy_account + transaction models and migration"
```

---

### Task 2: Energy weights (cost-calibrated per feature)

**Files:**
- Create: `backend/app/modules/billing/application/energy_weights.py`
- Test: `backend/tests/unit/test_energy_weights.py`

**Interfaces:**
- Produces: `BASE_ENERGY: dict[str, int]` keyed by the `FEATURE_*` constants from `app/ai/observability/billable_usage.py`; `base_units_for(feature_key: str) -> int` (defaults to `DEFAULT_UNITS` for unknown keys).

- [ ] **Step 1: Write the failing test**

```python
from app.ai.observability import billable_usage as F
from app.modules.billing.application.energy_weights import base_units_for, BASE_ENERGY

def test_vision_costs_more_than_text_edit():
    assert base_units_for(F.FEATURE_CV_EXTRACTION) > base_units_for(F.FEATURE_CV_EDIT_COMMAND)

def test_every_student_feature_has_a_weight():
    for key in [F.FEATURE_CHATBOT, F.FEATURE_CV_EXTRACTION, F.FEATURE_CV_EDIT_COMMAND,
                F.FEATURE_CV_FIT_EXPLANATION, F.FEATURE_COVER_LETTER, F.FEATURE_INTERVIEW_SIM,
                F.FEATURE_JD_EXTRACTION]:
        assert key in BASE_ENERGY and BASE_ENERGY[key] >= 1

def test_unknown_feature_defaults():
    assert base_units_for("nonexistent") >= 1
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && uv run pytest tests/unit/test_energy_weights.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement** — weights are relative, cost-calibrated (vision ≫ text). These are Phase-1 defaults; superadmin-tunable later.

```python
"""Per-feature base energy weights (cost-calibrated; masked from students)."""
from app.ai.observability import billable_usage as F

DEFAULT_UNITS = 10
BASE_ENERGY: dict[str, int] = {
    F.FEATURE_CHATBOT: 5,
    F.FEATURE_CV_EDIT_COMMAND: 8,
    F.FEATURE_CV_SUGGESTION: 8,
    F.FEATURE_CV_FIT_EXPLANATION: 6,
    F.FEATURE_COVER_LETTER: 10,
    F.FEATURE_INTERVIEW_SIM: 6,
    F.FEATURE_LEARNING_PLAN: 6,
    F.FEATURE_CV_EXTRACTION: 40,   # paid multimodal — most expensive
    F.FEATURE_JD_EXTRACTION: 30,
    F.FEATURE_JD_WRITER: 12,
    F.FEATURE_SCREENING_BRIEF: 20,
    F.FEATURE_SCORECARD_SUGGESTION: 10,
    F.FEATURE_EMBEDDINGS: 1,
    F.FEATURE_RERANK: 2,
}

def base_units_for(feature_key: str) -> int:
    return BASE_ENERGY.get(feature_key, DEFAULT_UNITS)
```

- [ ] **Step 4: Run to verify pass** — `cd backend && uv run pytest tests/unit/test_energy_weights.py -v` → PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat(billing): per-feature AI energy weights"`.

---

### Task 3: Energy service (allowance, meter, enforce, charge, soft-warn)

**Files:**
- Create: `backend/app/modules/billing/application/energy_service.py`
- Modify: `backend/app/modules/billing/application/limit_facade.py` (add `resolve_user_weekly_energy_units`)
- Test: `backend/tests/unit/test_energy_service.py`

**Interfaces:**
- Consumes: `AiEnergyAccount`/`AiEnergyTransaction` (Task 1), `base_units_for` (Task 2), `record_billable_usage`/`UsageContext`/`units_for` (`app/ai/observability/billable_usage.py`).
- Produces:
  - `class EnergyExhaustedError(AppError)` — maps to `402`/`409` with code `AI_ENERGY_EXHAUSTED`, user-safe message, `upgrade_path`.
  - `async resolve_weekly_allowance(db, user_id) -> int`
  - `async get_or_create_account(db, user_id) -> AiEnergyAccount` (rolls the weekly window if `now >= week_window_start + 7d`, resetting `week_units_used=0`)
  - `async get_meter(db, user_id) -> dict` → `{weekly: {used_pct, remaining_pct, resets_at}, wallet_balance_display, warn_soft, blocked, upgrade_path}` (NO raw units to callers that serialize to students; internal callers may read units)
  - `async enforce(db, user_id, feature_key) -> None` — preflight; raises `EnergyExhaustedError` if `weekly_remaining + wallet < base_units_for(feature_key)`
  - `async charge(db, *, ctx: UsageContext, result_status, provider_cost_usd=None) -> None` — writes the ledger row via `record_billable_usage(base_units=base_units_for(ctx.feature_key))`, and on a chargeable user-scope result decrements weekly-then-wallet + writes an `AiEnergyTransaction('charge', -units)`; idempotent (skips the decrement if the ledger row was a pre-existing idempotency hit)
  - `async soft_warn_state(db, user_id) -> bool` — rolling `SUM(units_charged)` over `ai_billable_usage WHERE actor_user_id=? AND created_at >= now-3h` beyond `SOFT_3H_THRESHOLD`

- [ ] **Step 1: Write the failing tests** — cover: fresh account gets plan allowance; enforce blocks when weekly+wallet insufficient; charge decrements weekly first then wallet; charge on `provider_failed` decrements nothing; idempotent charge decrements once; weekly window rolls after 7 days; soft-warn flips past threshold without blocking.

```python
import uuid, pytest
from datetime import datetime, timedelta, timezone
from app.ai.observability import billable_usage as F
from app.ai.observability.billable_usage import UsageContext, SCOPE_USER, PERSONA_STUDENT
from app.modules.billing.application import energy_service as E

def _ctx(uid, key=F.FEATURE_COVER_LETTER, idem=None):
    return UsageContext(actor_persona=PERSONA_STUDENT, feature_key=key,
                        task_type=key, billing_scope=SCOPE_USER,
                        actor_user_id=uid, idempotency_key=idem)

@pytest.mark.asyncio
async def test_enforce_blocks_when_insufficient(db_session, monkeypatch):
    uid = uuid.uuid4()
    monkeypatch.setattr(E, "resolve_weekly_allowance", _const(0))
    with pytest.raises(E.EnergyExhaustedError):
        await E.enforce(db_session, uid, F.FEATURE_CV_EXTRACTION)

@pytest.mark.asyncio
async def test_charge_decrements_weekly_then_wallet(db_session, monkeypatch):
    uid = uuid.uuid4()
    monkeypatch.setattr(E, "resolve_weekly_allowance", _const(15))
    acct = await E.get_or_create_account(db_session, uid)
    acct.wallet_balance_units = 100
    await db_session.flush()
    await E.charge(db_session, ctx=_ctx(uid), result_status=F.RESULT_SUCCESS)  # cover_letter=10
    acct = await E.get_or_create_account(db_session, uid)
    assert acct.week_units_used == 10 and acct.wallet_balance_units == 100
    await E.charge(db_session, ctx=_ctx(uid, idem="x"), result_status=F.RESULT_SUCCESS)  # 5 weekly + 5 wallet
    acct = await E.get_or_create_account(db_session, uid)
    assert acct.week_units_used == 15 and acct.wallet_balance_units == 95

@pytest.mark.asyncio
async def test_charge_on_failure_decrements_nothing(db_session, monkeypatch):
    uid = uuid.uuid4()
    monkeypatch.setattr(E, "resolve_weekly_allowance", _const(100))
    await E.charge(db_session, ctx=_ctx(uid), result_status=F.RESULT_PROVIDER_FAILED)
    acct = await E.get_or_create_account(db_session, uid)
    assert acct.week_units_used == 0

@pytest.mark.asyncio
async def test_idempotent_charge_once(db_session, monkeypatch):
    uid = uuid.uuid4()
    monkeypatch.setattr(E, "resolve_weekly_allowance", _const(100))
    for _ in range(2):
        await E.charge(db_session, ctx=_ctx(uid, idem="same"), result_status=F.RESULT_SUCCESS)
    acct = await E.get_or_create_account(db_session, uid)
    assert acct.week_units_used == 10  # charged once

def _const(v):
    async def _f(db, user_id): return v
    return _f
```

- [ ] **Step 2: Run to verify they fail** — `cd backend && uv run pytest tests/unit/test_energy_service.py -v` → FAIL (module missing).

- [ ] **Step 3: Implement `energy_service.py`** — weekly window roll, weekly-then-wallet decrement, idempotency via the ledger row identity, soft-warn rolling sum. Use `func.now()`-free UTC via `datetime.now(timezone.utc)` (match repo convention in `usage_service.py:_day_start`). Key logic:

```python
"""AI energy account service — the single charge/enforce choke point (WS-1)."""
from __future__ import annotations
import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.ai.observability import billable_usage as L
from app.ai.observability.billable_usage import UsageContext, record_billable_usage, units_for
from app.ai.observability.models import AiBillableUsage
from app.modules.billing.application.energy_weights import base_units_for
from app.modules.billing.application.limit_facade import resolve_user_weekly_energy_units
from app.modules.billing.domain.energy_models import AiEnergyAccount, AiEnergyTransaction
from app.shared.exceptions import AppError  # match the base error class actually used

SOFT_3H_THRESHOLD = 200   # tune during shadow period
_WEEK = timedelta(days=7)
_UPGRADE_PATH = "/student/billing"

class EnergyExhaustedError(AppError):
    code = "AI_ENERGY_EXHAUSTED"
    http_status = 402
    def __init__(self) -> None:
        super().__init__("Bạn đã dùng hết năng lượng AI trong tuần này.",
                         details={"upgrade_path": _UPGRADE_PATH})

async def resolve_weekly_allowance(db: AsyncSession, user_id: uuid.UUID) -> int:
    return await resolve_user_weekly_energy_units(db, user_id)

async def get_or_create_account(db, user_id) -> AiEnergyAccount:
    acct = await db.get(AiEnergyAccount, user_id)
    now = datetime.now(timezone.utc)
    allowance = await resolve_weekly_allowance(db, user_id)
    if acct is None:
        acct = AiEnergyAccount(user_id=user_id, plan_weekly_units=allowance,
                               week_window_start=now, week_units_used=0, wallet_balance_units=0)
        db.add(acct); await db.flush([acct]); return acct
    if now >= acct.week_window_start + _WEEK:
        acct.week_window_start = now
        acct.week_units_used = 0
    acct.plan_weekly_units = allowance  # tier changes take effect next check
    return acct

def _weekly_remaining(acct) -> int:
    return max(0, acct.plan_weekly_units - acct.week_units_used)

async def enforce(db, user_id, feature_key) -> None:
    acct = await get_or_create_account(db, user_id)
    need = base_units_for(feature_key)
    if _weekly_remaining(acct) + acct.wallet_balance_units < need:
        raise EnergyExhaustedError()

async def charge(db, *, ctx: UsageContext, result_status, provider_cost_usd=None) -> None:
    base = base_units_for(ctx.feature_key)
    before = None
    if ctx.idempotency_key is not None:
        before = await _ledger_exists(db, ctx.idempotency_key)
    row = await record_billable_usage(db, ctx=ctx, result_status=result_status,
                                      base_units=base, provider_cost_usd=provider_cost_usd)
    charged = units_for(result_status, base)
    if charged <= 0 or ctx.billing_scope != L.SCOPE_USER or ctx.actor_user_id is None:
        return
    if before:  # idempotency hit — already decremented on the first charge
        return
    acct = await get_or_create_account(db, ctx.actor_user_id)
    from_weekly = min(charged, _weekly_remaining(acct))
    acct.week_units_used += from_weekly
    acct.wallet_balance_units = max(0, acct.wallet_balance_units - (charged - from_weekly))
    db.add(AiEnergyTransaction(user_id=ctx.actor_user_id, kind="charge", units=-charged,
                               feature_key=ctx.feature_key, billable_usage_id=row.id))

async def soft_warn_state(db, user_id) -> bool:
    since = datetime.now(timezone.utc) - timedelta(hours=3)
    total = (await db.execute(
        select(func.coalesce(func.sum(AiBillableUsage.units_charged), 0)).where(
            AiBillableUsage.actor_user_id == user_id, AiBillableUsage.created_at >= since))
    ).scalar_one()
    return int(total) >= SOFT_3H_THRESHOLD

async def get_meter(db, user_id) -> dict:
    acct = await get_or_create_account(db, user_id)
    total = acct.plan_weekly_units or 1
    used_pct = min(100, round(100 * acct.week_units_used / total))
    return {
        "weekly": {"used_pct": used_pct, "remaining_pct": 100 - used_pct,
                   "resets_at": (acct.week_window_start + _WEEK).isoformat()},
        "wallet_balance_display": _wallet_bucket(acct.wallet_balance_units),
        "warn_soft": await soft_warn_state(db, user_id),
        "blocked": _weekly_remaining(acct) + acct.wallet_balance_units <= 0,
        "upgrade_path": _UPGRADE_PATH,
    }

async def _ledger_exists(db, key) -> bool:
    return (await db.execute(
        select(AiBillableUsage.id).where(AiBillableUsage.idempotency_key == key))
    ).scalar_one_or_none() is not None

def _wallet_bucket(units: int) -> str:
    # Masked: never a raw number to students; coarse bucket only.
    if units <= 0: return "empty"
    if units < 100: return "low"
    if units < 500: return "medium"
    return "high"
```

> Verify the real base error class + how HTTP status/code are wired (grep `class .*Error` in `app/shared/exceptions.py` and how `usage_service` raises `QUOTA_EXCEEDED`) and match it exactly. Add `resolve_user_weekly_energy_units` to `limit_facade.py` mirroring `resolve_user_ai_daily_cost_quota` (VinUni vs external tiers; read `subscription_plans.limits.weekly_energy_units`, default e.g. Free=1000 / Premium=5000 — placeholders, calibrated in the shadow period).

- [ ] **Step 4: Run to verify pass** — `cd backend && uv run pytest tests/unit/test_energy_service.py -v` → PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat(billing): AI energy service (enforce/charge/meter, weekly+wallet+3h-soft)"`.

---

### Task 4: Route the gateway runner through energy_service

**Files:**
- Modify: `backend/app/ai/gateway/task_runner.py:77-103` (`_record_billable`)
- Test: `backend/tests/integration/test_ai_metering_wiring.py`

**Interfaces:**
- Consumes: `energy_service.charge` (Task 3). Produces: any `AiTaskRunner` call given a `UsageContext` with `billing_scope=user` now decrements the student's energy on success.

- [ ] **Step 1: Write the failing test** — build an `AiTaskRunner` with `usage_context` (student, cover_letter) over the OFFLINE provider, call `.complete(...)`, assert an `AiEnergyAccount` row exists with `week_units_used == base_units_for(cover_letter)` and one `ai_billable_usage` success row.

- [ ] **Step 2: Run to verify it fails** — the account is not decremented yet.

- [ ] **Step 3: Implement** — change `_record_billable` to delegate to `energy_service.charge` (keeping the best-effort try/except and the `usage_context is None` short-circuit):

```python
    async def _record_billable(self, result_status: str, *, provider_cost_usd=None) -> None:
        if self._usage_context is None or self._db is None:
            return
        try:
            from app.modules.billing.application.energy_service import charge
            await charge(self._db, ctx=self._usage_context,
                         result_status=result_status, provider_cost_usd=provider_cost_usd)
        except Exception:  # noqa: BLE001
            import logging
            logging.getLogger("ai.task_runner").warning(
                "ai_billable_ledger_write_failed", exc_info=True)
```

> `charge` internally calls `record_billable_usage` with the correct `base_units`, so `AiTaskRunner`'s `charge_units` constructor arg is now redundant for energy — leave it in place (partner code may still read it) but energy uses the weight table, keeping student/partner consistent.

- [ ] **Step 4: Run to verify pass** — PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat(ai): route gateway billable through energy_service"`.

---

### Task 5: Remove daily enforcement (both mechanisms)

**Files:**
- Modify: `backend/app/modules/ai_assistant/application/usage_service.py` (drop the day window from `my_usage`/`enforce_quota`; keep weekly only as a legacy chat safety net OR delete once energy meters chat — prefer: have chat call `energy_service.enforce`/rely on energy, and delete the request-count daily path)
- Modify: `backend/app/modules/ai_settings/application/budget_guard.py` + `backend/app/modules/billing/application/limit_facade.py` (remove the per-user student USD-daily quota gate; keep platform/org USD budget)
- Modify: `backend/app/core/config.py` (remove/retire `ai_daily_request_limit`, `ai_daily_cost_limit_usd` student usage; keep platform)
- Test: `backend/tests/integration/test_daily_removed.py`

- [ ] **Step 1: Write the failing test** — a student exceeding the old 50/day request count is NOT blocked on the day axis (only weekly/energy governs), and `budget_guard.check_async` no longer raises on the per-user student daily USD path.
- [ ] **Step 2: Run to verify it fails** — daily still enforced.
- [ ] **Step 3: Implement** — delete the `_day_start`/day-window branches in `usage_service`; delete the per-user daily USD quota layer in `budget_guard.check_async` + its `limit_facade` resolver; retire the config keys. Keep the platform/org daily USD safety net (superadmin).
- [ ] **Step 4: Run to verify pass** + run the existing `test_ai_governance`/usage tests to confirm no regressions (`cd backend && uv run pytest tests/unit/test_ai_governance.py tests/integration -k usage -v`).
- [ ] **Step 5: Commit** — `git commit -m "refactor(ai): remove daily AI windows (request-count + student USD)"`.

---

### Task 6: Route the bypassing ops through metering

Each sub-task: at the service entry, call `await energy_service.enforce(db, user_id, FEATURE_X)`; on a successful user-visible result, ensure the op runs through `AiTaskRunner` with a `UsageContext(billing_scope=user, actor_persona=student, feature_key=FEATURE_X, actor_user_id=user_id, idempotency_key=make_idempotency_key(FEATURE_X, <stable result id>))` OR wrap with `energy_service.charge(...)` around the existing call. Add a per-op integration test over the OFFLINE provider asserting exactly one success charge + account decrement, and zero charge when AI is disabled/errors.

- [ ] **6a — Vision CV/JD extraction (priority 1):** rewrite `app/ai/extraction/adapters/vision.py:239` to call the gateway provider (via `AiTaskRunner`/`get_provider_for_alias`) instead of raw `httpx`; feature `FEATURE_CV_EXTRACTION`/`FEATURE_JD_EXTRACTION`; idempotency keyed by `(ingestion_id)`. Test: `tests/integration/test_ai_metering_wiring.py::test_vision_metered`. Commit.
- [ ] **6b — Cover letter:** `cover_letter_service.py:120`; `FEATURE_COVER_LETTER`; idempotency `(job_id, cv_id)`. Commit.
- [ ] **6c — CV AI tasks + edit-command:** `cv_ai_service.py:218,318` → `tasks.py`/`edit_command.py`; `FEATURE_CV_SUGGESTION`/`FEATURE_CV_EDIT_COMMAND`; idempotency `(cv_id, suggestion_id)`. Consume the already-computed `CvAiResult.credits` only for display, not billing (energy uses the weight table). Commit.
- [ ] **6d — CV-JD fit explanation:** `semantic_scorer.py:277` via `job_fit_service.py:180`; `FEATURE_CV_FIT_EXPLANATION`; idempotency `(cv_version, job_version)` (matches the fit cache key). Commit.
- [ ] **6e — JD extraction structuring:** `jd/cascade.py`/`structuring.py`; `FEATURE_JD_EXTRACTION`. Commit.
- [ ] **6f — Skill translation:** `skill_translation.py:247` (only bills on the fit-recompute real-provider path); `FEATURE_EMBEDDINGS`-class low weight or a dedicated key. Commit.
- [ ] **6g — Interview sim question + feedback:** interview-sim service; `FEATURE_INTERVIEW_SIM`. Commit.

After 6a–6g: `git grep -n "get_provider().complete\|httpx.post" backend/app/ai backend/app/modules` returns no value-affecting call outside the gateway (add a guard test `test_no_direct_provider_calls`).

---

### Task 7: Energy API + frontend meter

**Files:**
- Create: `backend/app/modules/billing/api/energy_router.py` (`GET /ai/energy/me`, `POST /ai/energy/topup`), register in the API router aggregator.
- Create: `frontend/src/lib/api/energy.ts`, `frontend/src/components/ai/energy-meter.tsx`
- Modify: `frontend/src/components/layout/public-auth-actions.tsx:79-87` (mount `<EnergyMeter/>` for students)
- Test: `backend/tests/integration/test_energy_api.py` (endpoint), plus a frontend render test if the harness supports it.

**Interfaces:**
- Produces: `GET /ai/energy/me` → `energy_service.get_meter(...)` shape (no tokens/USD). `POST /ai/energy/topup` → creates a pending manual/bank-transfer top-up (reuse the billing manual-payment adapter); superadmin/billing confirmation grants wallet energy via an `AiEnergyTransaction('purchase', +units)`.

- [ ] **Step 1: Write the failing endpoint test** — authenticated student `GET /ai/energy/me` returns 200 with `weekly.remaining_pct` and NO `tokens`/`usd`/`units` raw fields; guest gets 401.
- [ ] **Step 2: Run to verify it fails.**
- [ ] **Step 3: Implement** the router (HTTP only; delegate to `energy_service`), register it, and the frontend `EnergyMeter` (masked %, warn at ≤20% remaining, block state links to `/student/billing`). Adapt the existing `SidebarUsageCard` pattern; do not show numbers.
- [ ] **Step 4: Run to verify pass.**
- [ ] **Step 5: Commit** — `git commit -m "feat(billing): /ai/energy/me + student header energy meter"`.

---

### Task 8: Resilience / degradation contract (WS-9)

**Files:**
- Create: `backend/app/ai/resilience.py` — `AiCapability` enum + `ai_capabilities(db) -> dict` (per-op: `available` | `degraded_offline` | `unavailable`) derived from `real_provider_active()` + the AI-enabled flag + energy state.
- Modify: each op from Task 6 to consult the contract and return a user-safe state (never a provider/model/error code) when AI-required and unavailable; AI-optional ops return their deterministic result with an `ai_unavailable` marker.
- Test: `backend/tests/unit/test_ai_resilience.py`, `backend/tests/integration/test_ai_disabled_degradation.py`

- [ ] **Step 1: Write the failing tests** — with the provider forced offline/disabled: (a) native-text CV upload still extracts (offline), (b) a scanned/image CV returns a clear `extraction_pending`/`ai_unavailable` status and is NOT fabricated, (c) deterministic fit score + competition bands still return, (d) cover letter / CV AI edit / chatbot return a user-safe `ai_unavailable` state, (e) NO energy is charged in any degraded/failed path.
- [ ] **Step 2: Run to verify they fail.**
- [ ] **Step 3: Implement** `ai_capabilities` + wire each op's branch (reuse each tool's existing `fallback_behavior` string). Ensure the cascade tries native/OCR before vision and never fabricates.
- [ ] **Step 4: Run to verify pass** — include the CV-ingestion matrix (`text/vietnamese/two-column/scanned/blank/not-cv/password/corrupt/duplicate/OCR-unavailable/LLM-disabled`) per `.claude/rules/backend.md`.
- [ ] **Step 5: Commit** — `git commit -m "feat(ai): resilience/degradation contract — offline-safe, no-fabrication, no-charge-on-failure"`.

---

### Task 9: Phase-1 gate + status

- [ ] **Step 1:** Run full backend gates: `cd backend && uv run ruff check app && uv run mypy app && uv run pytest -q`. Record pass/fail counts vs the known baseline.
- [ ] **Step 2:** Offline AI eval green for changed tasks; then ONE capped real-model smoke on a cheap alias (`AI_REAL_CALLS_ENABLED=true AI_MAX_REAL_CALLS_PER_TEST_RUN=…`) for vision extraction + cover letter → fix any issue → retest. Report count/alias/cost without leaking provider/model.
- [ ] **Step 3:** Frontend: `cd frontend && pnpm typecheck && pnpm build`; verify the energy meter renders and the block/warn states behave.
- [ ] **Step 4:** Update `docs/IMPLEMENTATION_STATUS.md` with exact commands + `implemented`/`API wired`/`browser verified` status for Phase 1.
- [ ] **Step 5: Commit** — `git commit -m "chore: Phase 1 energy metering + resilience gate + status"`.

---

## Self-Review

- **Spec coverage (Phase 1 = WS-1, WS-2, WS-9 + core WS-7):** WS-1 → Tasks 1–5,7. WS-2 (route all ops) → Task 6. WS-9 (resilience) → Task 8. WS-7 core migrations → Task 1. Weekly-hard/3h-soft/no-daily → Tasks 3,5. Tiered allowance + wallet → Tasks 1,3,7. Masked energy % → Tasks 3,7. Charge-on-success/idempotent → Tasks 3,4. Shared substrate with partner overhaul → Tasks 1,3 (scope-aware). Covered.
- **Placeholder scan:** allowance numbers (Free=1000/Premium=5000) and `SOFT_3H_THRESHOLD=200` are explicitly flagged as shadow-period-calibrated defaults, not TBDs. Base-error-class + `Base` import are called out to verify-against-repo before writing (not left vague in the deliverable).
- **Type consistency:** `UsageContext`, `record_billable_usage`, `units_for`, `SCOPE_USER`, `FEATURE_*`, `RESULT_SUCCESS/PROVIDER_FAILED` are used exactly as defined in `app/ai/observability/billable_usage.py`. `energy_service.charge`/`enforce`/`get_meter` signatures are consistent across Tasks 3,4,6,7,8.

## Notes for later phases

Phases 2–4 get their own plans (`docs/superpowers/plans/`): Phase 2 job-intelligence (WS-3/4/5 + job-detail WS-14 slice + WS-15 job-detail slice), Phase 3 discovery + chatbot + multi-agent (WS-12/10/11 + WS-15 orchestration), Phase 4 polish + gaps + ads (WS-14 remainder, WS-6, WS-15 remainder, WS-13).
