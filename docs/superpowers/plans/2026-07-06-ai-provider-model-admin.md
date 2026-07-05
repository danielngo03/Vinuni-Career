# AI Provider & Model Admin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the AI named-alias catalog with direct provider+model binding per function slot, harden key encryption with rotation, add configurable rotation + health probes, and redesign the admin UI in v9 Monochrome.

**Architecture:** Six fixed function slots (`chat_default`, `reasoning_default`, `embedding_default`, `rerank_default`, `eval_default`, `vision_default`) are the leak-safe handles passed through the gateway; each binds directly to a concrete `(provider, model_id)` seeded from `.env` and editable by admin. Legacy `*_cheap` names remain resolvable synonyms (removed from the allowlist/UI) so the ~152 existing references keep working.

**Tech Stack:** FastAPI async, SQLAlchemy 2.x async, Alembic, Pydantic v2, `cryptography` (Fernet/MultiFernet), Next.js App Router + React Query + dnd-kit, Phosphor icons.

## Global Constraints

- Model ids / provider names / keys / tokens NEVER exposed to students/partners/guests (`.claude/rules/ai.md`). Slot handles are the only labels allowed to travel.
- All LLM access goes through `app/ai/gateway` factory — no direct SDK calls in modules.
- RBAC enforced in service layer; every write audited; health probes are real calls gated by `AI_REAL_CALLS_ENABLED` + budget.
- Gateway (`app/ai/gateway/*`) stays ORM-free and sync; `ai_settings` publishes snapshots one-way via `runtime_config.publish`.
- Migrations have upgrade + downgrade. Backend gate: `uv run ruff check app tests` + `uv run mypy app --ignore-missing-imports` + `uv run pytest` must pass. Run pytest with `DEBUG=false`.
- Frontend v9 Monochrome: ink + green(healthy)/amber(degraded)/red(down) only. No gradients, no emerald/violet/sky/blue accent surfaces. i18n vi/en.
- Never touch or print real key values in `backend/.env`; edit only non-secret alias/default lines and add the new encryption-key var placeholder.

---

## Phase 1 — Backend foundation: direct model binding (FULLY DETAILED)

Deliverable: the six `*_default` slots seed from `.env` concrete models, resolve through the gateway, and are the allowlisted defaults; legacy `*_cheap` still resolve; full test gate green.

### Task 1.1: Config — concrete per-slot model env

**Files:**
- Modify: `backend/app/core/config.py:69-77,232`
- Test: `backend/tests/unit/ai/test_config_model_slots.py`

**Interfaces:**
- Produces: `Settings.ai_default_provider: str`, `Settings.ai_chat_model: str`, `ai_reasoning_model`, `ai_embedding_model`, `ai_rerank_model`, `ai_eval_model`, `ai_vision_model: str`. Keeps existing `ai_default_model_alias` etc. as deprecated (still read for back-compat) but defaulting to `chat_default` … .

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/ai/test_config_model_slots.py
from app.core.config import get_settings

def test_default_slot_models_are_concrete():
    s = get_settings()
    assert s.ai_default_provider == "openrouter"
    assert s.ai_chat_model == "deepseek/deepseek-v4-flash"
    assert s.ai_reasoning_model == "deepseek/deepseek-r1"
    assert s.ai_embedding_model == "text-embedding-3-small"
    assert s.ai_rerank_model == "deepseek/deepseek-v4-flash"
    assert s.ai_eval_model == "deepseek/deepseek-v4-flash"
    assert s.ai_vision_model == "google/gemini-2.5-flash"

def test_slot_alias_defaults_renamed():
    s = get_settings()
    assert s.ai_default_model_alias == "chat_default"
    assert s.ai_reasoning_model_alias == "reasoning_default"
    assert s.ai_embedding_model_alias == "embedding_default"
    assert s.ai_rerank_model_alias == "rerank_default"
    assert s.ai_eval_model_alias == "eval_default"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && DEBUG=false uv run pytest tests/unit/ai/test_config_model_slots.py -v`
Expected: FAIL (AttributeError / wrong defaults).

- [ ] **Step 3: Implement**

In `config.py`, change the alias defaults and add concrete-model fields:

```python
    ai_default_provider: str = "openrouter"
    ai_chat_model: str = "deepseek/deepseek-v4-flash"
    ai_reasoning_model: str = "deepseek/deepseek-r1"
    ai_embedding_model: str = "text-embedding-3-small"
    ai_rerank_model: str = "deepseek/deepseek-v4-flash"
    ai_eval_model: str = "deepseek/deepseek-v4-flash"
    ai_vision_model: str = "google/gemini-2.5-flash"

    ai_default_model_alias: str = "chat_default"
    ai_reasoning_model_alias: str = "reasoning_default"
    ai_embedding_model_alias: str = "embedding_default"
    ai_rerank_model_alias: str = "rerank_default"
    ai_eval_model_alias: str = "eval_default"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && DEBUG=false uv run pytest tests/unit/ai/test_config_model_slots.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/config.py backend/tests/unit/ai/test_config_model_slots.py
git commit -m "feat(ai): concrete per-slot model config + *_default slot aliases"
```

### Task 1.2: Gateway builtin maps — add `*_default` slots from config

**Files:**
- Modify: `backend/app/ai/gateway/openai_compatible.py:31-52` (`_BUILTIN_MODEL_MAP`)
- Modify: `backend/app/ai/gateway/runtime_config.py:44-67` (`_BUILTIN_ROUTES`) and `_bootstrap_from_env`
- Test: `backend/tests/unit/ai/test_default_slot_routes.py`

**Interfaces:**
- Produces: `known_aliases()` contains the six `*_default` names; `_bootstrap_from_env()` builds `*_default` routes from `Settings.ai_*_model` + `ai_default_provider`. Legacy `*_cheap` remain present.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/ai/test_default_slot_routes.py
from app.ai.gateway import runtime_config
from app.ai.gateway.openai_compatible import known_aliases

def test_default_slots_resolvable():
    resolvable = known_aliases()
    for slot in ("chat_default","reasoning_default","embedding_default","rerank_default","eval_default","vision_default"):
        assert slot in resolvable

def test_bootstrap_binds_chat_default_to_config_model():
    cfg = runtime_config._bootstrap_from_env()
    provider, base_url, model_id = cfg.provider_routes["chat_default"]
    assert provider == "openrouter"
    assert model_id == "deepseek/deepseek-v4-flash"

def test_legacy_alias_still_resolvable():
    assert "chat_cheap" in known_aliases()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && DEBUG=false uv run pytest tests/unit/ai/test_default_slot_routes.py -v`
Expected: FAIL (KeyError / missing slots).

- [ ] **Step 3: Implement**

In `openai_compatible.py` `_BUILTIN_MODEL_MAP`, add the six default slots (values are only fallbacks; real values come from config-driven routes):

```python
    "chat_default": "deepseek/deepseek-v4-flash",
    "reasoning_default": "deepseek/deepseek-r1",
    "embedding_default": "text-embedding-3-small",
    "rerank_default": "deepseek/deepseek-v4-flash",
    "eval_default": "deepseek/deepseek-v4-flash",
    "vision_default": "google/gemini-2.5-flash",
```

In `runtime_config.py`, replace the hardcoded `_BUILTIN_ROUTES` chat/reasoning/etc. entries by building the default-slot routes from config inside `_bootstrap_from_env` (keep the legacy `*_cheap` entries in `_BUILTIN_ROUTES` as-is for back-compat). Add after the existing `routes = dict(_BUILTIN_ROUTES)` line:

```python
    prov = s.ai_default_provider
    base = openrouter_url if prov == "openrouter" else routes.get("chat_cheap", (prov, "", ""))[1]
    routes["chat_default"] = (prov, base, s.ai_chat_model)
    routes["reasoning_default"] = (prov, base, s.ai_reasoning_model)
    routes["embedding_default"] = (prov, base, s.ai_embedding_model)
    routes["rerank_default"] = (prov, base, s.ai_rerank_model)
    routes["eval_default"] = (prov, base, s.ai_eval_model)
    routes["vision_default"] = (prov, base, s.ai_vision_model)
```

Also add `chat_default`/`reasoning_default` etc. to `_BUILTIN_ROUTES` literal with placeholder models so `known_aliases()` (which reads the published snapshot) always includes them even before bootstrap.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && DEBUG=false uv run pytest tests/unit/ai/test_default_slot_routes.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/ai/gateway/openai_compatible.py backend/app/ai/gateway/runtime_config.py backend/tests/unit/ai/test_default_slot_routes.py
git commit -m "feat(ai): seed *_default slot routes from concrete config models"
```

### Task 1.3: Seed default slot bindings in the provider registry

**Files:**
- Modify: `backend/app/ai/gateway/provider_registry.py:66-188` (`_DEFAULT_ALIASES`) and `ensure_defaults`
- Test: `backend/tests/integration/ai/test_seed_default_slots.py`

**Interfaces:**
- Produces: after `ensure_defaults`, `ai_model_aliases` has rows `chat_default` … `vision_default` bound to config models on `openrouter`, `is_builtin=True`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/integration/ai/test_seed_default_slots.py
import pytest
from sqlalchemy import select
from app.ai.gateway import provider_registry
from app.ai.gateway.provider_models import AiModelAlias

@pytest.mark.asyncio
async def test_seed_creates_default_slots(db_session):
    await provider_registry.ensure_defaults(db_session)
    await db_session.flush()
    rows = (await db_session.execute(select(AiModelAlias))).scalars().all()
    names = {r.alias_name for r in rows}
    assert {"chat_default","reasoning_default","embedding_default","rerank_default","eval_default","vision_default"} <= names
    chat = next(r for r in rows if r.alias_name == "chat_default")
    assert chat.model_id == "deepseek/deepseek-v4-flash"
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && DEBUG=false uv run pytest tests/integration/ai/test_seed_default_slots.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

Prepend six config-driven slot entries to `_DEFAULT_ALIASES` (build them from `get_settings()` inside `ensure_defaults` so the model id tracks `.env`). Add a helper at the top of `ensure_defaults`:

```python
    s = get_settings()
    default_slots = [
        ("chat_default", s.ai_chat_model, "chat", "Default chat model (admin-managed)"),
        ("reasoning_default", s.ai_reasoning_model, "reasoning", "Default reasoning model"),
        ("embedding_default", s.ai_embedding_model, "embedding", "Default embedding model"),
        ("rerank_default", s.ai_rerank_model, "rerank", "Default rerank model"),
        ("eval_default", s.ai_eval_model, "eval", "Default eval model"),
        ("vision_default", s.ai_vision_model, "vision", "Default vision model"),
    ]
```

Then, after seeding `_DEFAULT_ALIASES`, upsert each default slot against `ai_default_provider` (create if the `alias_name` is absent), mirroring the existing alias upsert loop.

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && DEBUG=false uv run pytest tests/integration/ai/test_seed_default_slots.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/ai/gateway/provider_registry.py backend/tests/integration/ai/test_seed_default_slots.py
git commit -m "feat(ai): seed default function-slot bindings from config"
```

### Task 1.4: Allowlist — `*_default` selectable, legacy hidden

**Files:**
- Modify: `backend/app/modules/ai_settings/domain/aliases.py:19-25`
- Modify: `backend/app/modules/ai_settings/domain/models.py:62-76` (ORM defaults → `*_default`)
- Test: `backend/tests/unit/ai/test_alias_allowlist_slots.py`

**Interfaces:**
- Produces: `ALIAS_ALLOWLIST` families list the `*_default` slot as the first/selectable option; `assert_allowlist_resolvable()` passes.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/ai/test_alias_allowlist_slots.py
from app.modules.ai_settings.domain import aliases

def test_default_slots_allowlisted():
    assert "chat_default" in aliases.allowed_aliases("chat_model_alias")
    assert "reasoning_default" in aliases.allowed_aliases("reasoning_model_alias")

def test_legacy_not_allowlisted():
    assert "chat_cheap" not in aliases.allowed_aliases("chat_model_alias")

def test_allowlist_resolvable():
    aliases.assert_allowlist_resolvable()  # must not raise
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && DEBUG=false uv run pytest tests/unit/ai/test_alias_allowlist_slots.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

```python
ALIAS_ALLOWLIST: dict[str, tuple[str, ...]] = {
    "chat": ("chat_default", "chat_openai_fast", "chat_openai_best", "chat_local"),
    "reasoning": ("reasoning_default", "reasoning_local"),
    "embedding": ("embedding_default", "embedding_openai", "embedding_local"),
    "rerank": ("rerank_default", "rerank_openai_fast", "rerank_local"),
    "eval": ("eval_default", "eval_local"),
}
```

In `domain/models.py` change the five `*_model_alias` column defaults to `"chat_default"`, `"reasoning_default"`, `"embedding_default"`, `"rerank_default"`, `"eval_default"`.

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && DEBUG=false uv run pytest tests/unit/ai/test_alias_allowlist_slots.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/ai_settings/domain/aliases.py backend/app/modules/ai_settings/domain/models.py backend/tests/unit/ai/test_alias_allowlist_slots.py
git commit -m "feat(ai): allowlist *_default slots, retire legacy aliases from UI"
```

### Task 1.5: Sweep hardcoded internal call sites `*_cheap` → `*_default`

**Files:**
- Modify: `backend/app/ai/extraction/adapters/policy.py`, `backend/app/ai/extraction/adapters/vision.py`, `backend/app/ai/extraction/jd/vision.py`, `backend/app/ai/retrieval/embeddings.py`, `backend/app/modules/opportunities/api/router.py`, `backend/app/ai/prompts/jd_translation/v1.py` (only where an alias literal is passed)
- Modify: `backend/.env.example`, `backend/.env` (non-secret lines only)
- Test: existing suites (regression)

**Interfaces:** consumes slots from 1.2/1.3. No new public interface.

- [ ] **Step 1: Find the literals**

Run: `cd backend && grep -rn -E "vision_cheap|chat_cheap|reasoning_cheap|embedding_cheap|rerank_cheap|eval_cheap" app --include='*.py' | grep -v "gateway/openai_compatible.py\|gateway/runtime_config.py\|gateway/provider_registry.py\|gateway/provider_models.py"`

- [ ] **Step 2: Replace call-site literals** with the matching `*_default` slot (`vision_cheap`→`vision_default`, `chat_cheap`→`chat_default`, etc.). Do NOT touch the builtin-map/seed/synonym definitions.

- [ ] **Step 3: Update env files**

In `backend/.env.example` replace the AI alias block with:

```
AI_DEFAULT_PROVIDER=openrouter
AI_CHAT_MODEL=deepseek/deepseek-v4-flash
AI_REASONING_MODEL=deepseek/deepseek-r1
AI_EMBEDDING_MODEL=text-embedding-3-small
AI_RERANK_MODEL=deepseek/deepseek-v4-flash
AI_EVAL_MODEL=deepseek/deepseek-v4-flash
AI_VISION_MODEL=google/gemini-2.5-flash
AI_DEFAULT_MODEL_ALIAS=chat_default
AI_REASONING_MODEL_ALIAS=reasoning_default
AI_EMBEDDING_MODEL_ALIAS=embedding_default
AI_EVAL_MODEL_ALIAS=eval_default
```

Also set `CV_VISION_PROVIDER_ALIAS=vision_default` and `CV_LLM_STRUCTURING_PROVIDER_ALIAS=chat_default`. Apply the same non-secret line edits to `backend/.env` without altering `OPENROUTER_API_KEY` or any secret value. Add commented `# AI_PROVIDER_KEY_ENCRYPTION_KEYS=` (used in Phase 2).

- [ ] **Step 4: Full backend gate**

Run: `cd backend && DEBUG=false uv run ruff check app tests && DEBUG=false uv run mypy app --ignore-missing-imports && DEBUG=false uv run pytest -q`
Expected: PASS (fix regressions from the sweep; legacy synonyms should keep older tests green).

- [ ] **Step 5: Commit**

```bash
git add backend/app backend/.env.example
git commit -m "refactor(ai): route internal call sites through *_default slots; concrete model env"
```

---

## Phase 2 — Encryption hardening (TASK OUTLINE — detail before executing)

- **2.1** `provider_key_crypto.py`: parse `AI_PROVIDER_KEY_ENCRYPTION_KEYS` (CSV, newest first) → `MultiFernet`; keep JWT-derived key as warned local-only fallback; prod (`APP_ENV != local`) with no real key → raise at startup. Tests: encrypt→decrypt round trip; decrypt a ciphertext made with an old key after prepending a new key; prod fail-fast.
- **2.2** Migration: add `api_key_last4`, `key_version` to `ai_provider_configs` (upgrade+downgrade).
- **2.3** `create_provider`/`update_provider`: store `api_key_last4` + `key_version` on write; serializer returns `has_api_key` + `api_key_last4` (never plaintext).
- **2.4** `reencrypt_all_provider_keys(session)` rotation routine + admin endpoint `POST /admin/ai-settings/keys/rotate`; audit-logged.
- **2.5** Full backend gate.

## Phase 3 — Rotation + health probes (TASK OUTLINE)

- **3.1** Migration: add `rotation_strategy` (default `priority`), `fallback_bindings` JSON, `last_health_status`, `last_health_checked_at` to `ai_model_aliases`.
- **3.2** Snapshot: add `provider_route_strategies` to `EffectiveAiConfig`; resolver populates it; `provider_route_chains` hops read from `fallback_bindings`.
- **3.3** Gateway `factory.get_provider_for_alias`: `round_robin` rotates start index among healthy hops (per-slot in-process counter), then `FallbackChainProvider`. Tests: distribution + circuit-open skip; `priority` unchanged.
- **3.4** Health probe service `app/ai/gateway/health_probe.py`: `probe_provider(...)`, `probe_slot(...)` → `{reachable, authenticated, latency_ms, reason_code}`; gated by real-calls + budget; no raw upstream error.
- **3.5** Endpoints `POST /providers/{id}/test`, `POST /model-aliases/{id}/test`; persist `last_health_*`; audit. Contract test: no model/provider leak to non-admin.
- **3.6** Full backend gate + eval leakage test.

## Phase 4 — UI Monochrome redesign (TASK OUTLINE)

- **4.1** `lib/api`: add `test`/health + rotation + last4 fields to `aiProvidersApi`/`aiAliasesApi`; add slot-routing types.
- **4.2** Rewrite `ai-provider-manager.tsx` in v9 Monochrome (remove gradient/emerald/violet/sky): provider rows with health pill + Test + last4.
- **4.3** New `slot-routing-editor.tsx`: per-slot dnd-kit ordered provider+model list, Priority↔Round-robin toggle, per-hop Test + health dot; fold routing canvas.
- **4.4** Unify `ai-settings-screen.tsx` sections: Runtime & rollout · Providers · Model routing. Real-call confirm dialogs.
- **4.5** i18n vi/en messages. Browser QA 375/768/1024/1440 + dark theme; `pnpm typecheck && pnpm build`.

---

## Self-review notes

- Spec §4.1 (slots) → Tasks 1.1–1.5. §4.2 (encryption) → Phase 2. §4.3 (rotation) → 3.1–3.3. §4.4 (health) → 3.4–3.5. §4.5 (UI) → Phase 4. §5 migrations → 2.2, 3.1. §6 back-compat → 1.2/1.4/1.5 (synonyms + sweep). §7 security → global constraints + 3.5 contract test.
- Legacy synonyms are retained in `_BUILTIN_MODEL_MAP`, `_BUILTIN_ROUTES`, and seed rows — only removed from `ALIAS_ALLOWLIST`, so old references resolve.
- Slot names are consistent across tasks: `chat_default`, `reasoning_default`, `embedding_default`, `rerank_default`, `eval_default`, `vision_default`.
