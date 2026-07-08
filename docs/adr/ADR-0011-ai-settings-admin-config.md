# ADR-0011: `ai_settings` — Admin-Managed AI Provider/Model Config, Budget & Feature Flags

**Status:** Accepted (Proposed for implementation in the next backend slice)
**Date:** 2026-06-28
**Owner:** system-architect

> **Amendment — 2026-07-08 (ADR-0011.2):** provider/model registry identity and
> CRUD are platform-superadmin-only. Earlier ADR-0011 wording that says
> "University Admin" manages providers/models now means platform superadmin. Ordinary
> university staff may manage masked AI governance controls only: feature flags,
> budgets, alias handles, derived health, and limit requests. The grant
> `ai_settings:view_provider_identity` is not sufficient to reveal raw provider or
> concrete model identity unless the principal is also a platform superadmin. API
> keys and base URLs are never stored in responses or returned by any API.

**Related:** CLAUDE.md (Greenfield Naming Defaults: "Use `ai_settings` for admin-managed
provider/model settings"; "Do not expose AI provider names, model names, token counts…");
`docs/AI_PRODUCT_SPEC.md` §5.1 (legacy wording amended above: provider/model
registry is platform-superadmin-only; ordinary university staff see masked AI
governance controls), §5.2 (circuit-breaker "thresholds configurable in ai_settings"),
§5.4 + §11.2 (cost tracking / budget check / `402 BUDGET_EXCEEDED`), §16 (Rollout Defaults),
§17 (Rollback Criteria per feature); `docs/PRODUCT_REQUIREMENTS.md` (University AI governance
scope); `docs/SECURITY_PRIVACY.md` §AI Safety (lines 79–81: provider names / model names /
API keys never exposed); `docs/ENVIRONMENT.md` (lines 123–146: `OPENROUTER_API_KEY`,
`AI_REAL_CALLS_ENABLED`, alias names `chat_cheap`/`reasoning_cheap`/`eval_cheap`/
`embedding_cheap`, secret policy "never write the concrete key/provider/model"); `docs/API_CONTRACTS.md`
(admin endpoint + error envelope conventions). Builds on the **shipped AI gateway**
(`backend/app/ai/gateway/{factory,offline,output_guard}.py`), the **shipped CV-LLM runner**
(`app/ai/cv/llm.py`), the **shipped CV-ingestion structuring adapter seam**
(`app/ai/extraction/adapters/structuring.py` — `set_llm_structuring_adapter` injection
pattern), the **shipped job-fit enrichment** (`modules/documents/application/job_fit_service.py`,
gated on `real_provider_active()`), the **shipped config** (`app/core/config.py`: `ai_*`
aliases + `ai_real_calls_enabled` + `ai_daily_cost_limit_usd` + `openrouter_api_key` +
`openai_compatible_base_url` + `cv_llm_structuring_enabled`), and the **shipped RBAC/audit
facade pattern** of advertising (`advertising/application/moderation_service.py`
`_require_advertising_moderator` + `write_audit`; `opportunities.sponsorship_facade` one-way
seam). **ADR-0009 / ADR-0010** are the structural templates (university oversight surface +
load-bearing resolution facade).

## Context

The AI runtime is **already shipped and works offline by default**. Provider selection lives
entirely in **process env** today: `gateway.factory.real_provider_active()` and `get_provider()`
read `get_settings()` (`ai_real_calls_enabled` AND `openrouter_api_key not in PLACEHOLDERS`);
`cv/llm.py` reads `ai_default_model_alias`; the structuring adapter is gated on
`cv_llm_structuring_enabled`; job-fit enrichment short-circuits on `real_provider_active()`.
The `output_guard` already scrubs provider/model/key/token signals from every **end-user**
path. What does **not** exist is any **admin governance surface**: there is no way for a
platform superadmin to select provider/model bindings, flip a feature flag, set a
budget, or pull a kill switch **without editing `.env` and restarting**. Ordinary
university staff may only receive masked AI governance controls. Earlier
`AI_PRODUCT_SPEC` wording that named "University Admin → AI Settings" is amended by
ADR-0011.2: real provider/model registry ownership is platform-superadmin-only.

Constraints that bound the decision:

- **CLAUDE.md scope:** `ai_settings` = admin-managed provider/model settings; local-first;
  lightweight; small reversible first slice; no business logic in routers; RBAC at the service
  layer; every write audited; **no provider/model/token/key internals to end users**.
- **Secret law (ENVIRONMENT + SECURITY_PRIVACY):** real API keys live **only** in env
  (`OPENROUTER_API_KEY`), encrypted at rest / git-ignored; **never** in DB columns, docs,
  responses, logs, or migrations. The settings table references **alias names only**.
- **Env is the hard ceiling (ENVIRONMENT lines 139–145):** "Do not run a real model call just
  because `OPENROUTER_API_KEY` exists." An admin must be able to **disable** AI, but must
  **never** be able to enable real calls beyond what `AI_REAL_CALLS_ENABLED` + a present key
  already permit.
- **The shipped gateway is the only render path.** `ai_settings` decides *what* the gateway
  selects; the gateway/`output_guard` keep deciding *how nothing leaks* to end users.
- **Cross-module law (ARCHITECTURE §8):** the gateway (`app/ai/`) is shared infra and must not
  import a domain module's ORM. The `ai_settings` module reads its own DB row and **pushes** a
  resolved snapshot **into** the gateway (one-way), exactly like
  `structuring.set_llm_structuring_adapter` and `advertising → sponsorship_facade`.

`AI_PRODUCT_SPEC` §5.1/§5.4/§11.2 describe a **large end-state**: a multi-row
`ai_task_model_configs` table (per-alias provider+model mapping, per-tenant monthly **token**
budgets, circuit-breaker thresholds) plus an `ai_usage_log` metered ledger driving
`402 BUDGET_EXCEEDED`. Shipping that now would be a brittle mega-slice on a single-tenant
(VinUni-only) platform and would duplicate the alias→model mapping that already lives in
`config.py`. This ADR designs the **foundational governance core only** — a single
platform-scoped settings row + a resolution facade + an admin surface — with a named seam so
the ledger/metered-billing system attaches later without rework.

## Decision

### 1. New `ai_settings` module; **single platform-scoped** `ai_settings` row (not per-tenant for V1)

**Decision: new module `backend/app/modules/ai_settings/`** (DDD shape:
`api / application / domain / infrastructure`). The entity is **`ai_settings`**, a **single
row** scoped `scope = 'platform'` (VinUni is the only tenant — DATA_MODEL tenancy is
single-org for V1). Per-university rows are the **deferred** shape: the `scope` column + a
nullable `org_id` are reserved so a future ADR can add `scope = 'university'` rows resolved by
org without a table rewrite. **No raw keys, no concrete provider/model strings, no base URL**
live in this table — it stores **alias names + toggles + budget** only.

`ai_settings` columns (migration `0022_ai_settings`):

| column | type | note |
| --- | --- | --- |
| `id` | uuid pk | |
| `scope` | text not null default `'platform'` | **unique** — enforces the singleton; future `'university'` rows relax this |
| `org_id` | uuid fk organizations, null | reserved for deferred per-university scope; null for `'platform'` |
| `real_calls_enabled` | boolean not null default `false` | **DB toggle**, ANDed under the env+key ceiling (§2) |
| `rollout_state` | text not null default `'enabled'` | CHECK in (`enabled`,`paused`,`offline`); `offline`/`paused` force real calls off (§5 rollback) |
| `chat_model_alias` | text not null default `'chat_cheap'` | task family: chat/default |
| `reasoning_model_alias` | text not null default `'reasoning_cheap'` | task family: reasoning |
| `embedding_model_alias` | text not null default `'embedding_cheap'` | task family: embedding |
| `eval_model_alias` | text not null default `'eval_cheap'` | task family: eval/judge |
| `cv_llm_structuring_enabled` | boolean not null default `false` | feature flag → structuring adapter |
| `job_fit_ai_explanation_enabled` | boolean not null default `true` | feature flag → job-fit enrichment |
| `daily_budget_usd` | numeric(10,2) not null default `1.00` | per-day USD ceiling; seeds from `ai_daily_cost_limit_usd` |
| `notes` | text null | admin change rationale |
| `updated_by` | uuid fk users, null | last editor |
| `updated_at` | timestamptz not null default now() | |
| `created_at` | timestamptz not null default now() | |

**Alias values are validated against an allowlist at the service layer**, never free text — an
admin may select only from `{chat_cheap, chat_default, reasoning_cheap, embedding_cheap,
eval_cheap, …}` as defined in `config.py`. This blocks an admin from injecting a raw
`vendor/model-path` (which `output_guard` would otherwise have to scrub) and keeps the
alias→concrete-model mapping in env/config (the deferred `ai_task_model_configs` job).

Migration `0022` **seeds exactly one `'platform'` row** whose defaults mirror the current
`config.py` values, so behaviour is **byte-identical to today** the moment it ships
(real calls off, offline provider, structuring off, job-fit explanation on).

### 2. Resolution facade — the load-bearing seam (`EffectiveAiConfig` + gateway snapshot)

The gateway is sync, hot-path, and ORM-free. So `ai_settings` does **not** make the gateway
query the DB; instead it **publishes a resolved snapshot into a pure in-memory holder the
gateway already owns**, mirroring `structuring.set_llm_structuring_adapter`.

- **`app/ai/gateway/runtime_config.py`** (new, pure, no ORM): an immutable
  `EffectiveAiConfig` dataclass + a module-global holder.
  ```
  @dataclass(frozen=True, slots=True)
  class EffectiveAiConfig:
      real_calls_active: bool          # FINAL, post-precedence
      chat_model_alias: str
      reasoning_model_alias: str
      embedding_model_alias: str
      eval_model_alias: str
      cv_llm_structuring_enabled: bool
      job_fit_ai_explanation_enabled: bool
      daily_budget_usd: float

  def current() -> EffectiveAiConfig: ...      # never None — bootstrapped from env
  def publish(cfg: EffectiveAiConfig) -> None: # one-way write, called by the module
  ```
  The holder is **bootstrapped from `get_settings()` (env) at import**, so the gateway works
  before the module ever loads (offline, real calls off). `publish()` is the only writer.

- **`app/modules/ai_settings/application/resolver.py`** (the merge logic + precedence):
  reads the DB row **and** `get_settings()` (env + key presence), builds `EffectiveAiConfig`,
  and calls `runtime_config.publish(...)`. Invoked **on app startup** and **after every PATCH**.
  Precedence (env+key is the **hard ceiling**; DB can only restrict/select within it):
  ```
  key_present = settings.openrouter_api_key not in _PLACEHOLDER_KEYS
  env_real    = settings.ai_real_calls_enabled            # env hard-gate
  db_real     = row.real_calls_enabled and row.rollout_state == "enabled"
  real_calls_active = env_real AND key_present AND db_real    # AND, never OR
  ```
  → If **no key**, `real_calls_active` is **forced false** regardless of the DB row. If env
  gate is false, DB cannot enable. The DB toggle can only **turn off** what env permits or
  **select** aliases/flags/budget within the permitted envelope. This is the seam that makes a
  future `OPENROUTER_API_KEY` + `AI_REAL_CALLS_ENABLED=true` usable **with zero code change** —
  the admin just flips `real_calls_enabled` on and the next `publish()` lights it up.

**Exact consumers (one-way reads of `runtime_config.current()`):**

| Consumer | Today (env) | After this ADR |
| --- | --- | --- |
| `gateway.factory.real_provider_active()` | `settings.ai_real_calls_enabled and key…` | `return runtime_config.current().real_calls_active` |
| `gateway.factory.get_provider()` | reads `settings` directly | gate on `current().real_calls_active`; still constructs `OpenAICompatibleProvider` from **env** key/base_url (keys never travel through the snapshot) |
| `ai/cv/llm.py` (`generate_note`) | `settings.ai_default_model_alias` | `current().chat_model_alias` |
| `ai/extraction/adapters/structuring.py` | `cv_llm_structuring_enabled` | adapter availability gated on `current().cv_llm_structuring_enabled` |
| `documents/application/job_fit_service.py` | `real_provider_active()` + (new) flag | unchanged call + `current().job_fit_ai_explanation_enabled` AND-guard |

The **API key and base URL never enter `EffectiveAiConfig`** — `get_provider()` still pulls
them from env at construction time. The snapshot carries only **aliases + booleans + budget**.

### 3. Secrecy — NON-NEGOTIABLE (admin governance surface, not end-user)

`output_guard` already protects **end-user** paths. `ai_settings` adds an **admin-only**
governance surface and must itself never leak secrets:

- Responses expose **alias names + feature flags + budget** and **derived status only**:
  - `key_configured: bool` (computed from key-presence, never the key)
  - `real_calls: "offline" | "available" | "enabled"` where
    `offline` = env gate off **or** no key; `available` = env+key OK but DB toggle/rollout off;
    `enabled` = `real_calls_active == true`.
- **Never returned, ever:** `openrouter_api_key`, `openai_compatible_base_url`,
  `ai_default_provider` concrete value, model paths, token counts, latency. The DB has no key
  column to leak; the API layer never echoes env secrets.
- The `derived status` lets an admin understand *why* AI is off (env-blocked vs admin-disabled)
  **without** revealing the provider, model, or key.

### 4. Budget / cost — V1 field + check seam, ledger deferred

`daily_budget_usd` is stored and surfaced now. Enforcement is a **named seam, not a full
ledger**: `gateway` gains a thin `budget_guard.check(estimated_cost_usd)` called **before a
real call** that reads `current().daily_budget_usd` against a pluggable accumulator. **V1
default accumulator is a no-op** (offline calls cost nothing, so nothing trips). The
integration point for the deferred metered system is explicit: when **`ai_usage_log`**
(AI_PRODUCT_SPEC §5.4) ships, its daily-spend aggregate becomes the accumulator and
`budget_guard` raises `AIBudgetExceededError` → `402 BUDGET_EXCEEDED` (§11.2). No ledger, no
metering, no per-tenant token budget is built in this ADR — only the field + the seam.

### 5. RBAC + audit + rollback

- **RBAC (service layer, mirrors `_require_advertising_moderator`):** `superadmin` **OR** a
  member of a `university`-type org holding permission `ai_settings:manage` (read needs
  `ai_settings:read`). Resource string `ai_settings`. End users and partners get **404/403**
  — the surface is invisible to them. No hardcoded staff role; the permission is granted via
  the org/RBAC tables.
- **Audit:** every PATCH and the kill switch call `write_audit` with `before`/`after`
  diffs (alias/flag/budget/toggle changes), actor, and `RequestContext` — same `AuditContext`
  helper advertising uses. Keys are never in the diff (no key column).
- **Rollback (AI_PRODUCT_SPEC §16/§17):** two paths.
  1. `rollout_state` → `paused`/`offline` (PATCH) forces `real_calls_active=false` at the next
     `publish()` while preserving aliases/flags for a clean re-enable.
  2. **Kill switch** `POST /api/v1/admin/ai-settings/disable-ai` sets `real_calls_enabled=false`
     **and** `rollout_state='offline'`, publishes immediately, audited — the fast path for the
     §17 triggers (provider leakage, confirmed hallucination, cost anomaly). Re-enable is a
     normal PATCH back to `enabled` + `real_calls_enabled=true`.

### 6. API surface

University/superadmin only; all under `/api/v1/admin/ai-settings`:

- **`GET /api/v1/admin/ai-settings`** → effective settings: per-task-family aliases, feature
  flags, `daily_budget_usd`, `rollout_state`, and derived `key_configured` + `real_calls`
  status. Alias-only; no key/provider/base_url.
- **`PATCH /api/v1/admin/ai-settings`** → partial update of aliases (allowlist-validated),
  feature flags, `daily_budget_usd`, `real_calls_enabled`, `rollout_state`. Persisting
  `real_calls_enabled=true` while env/key are absent is allowed but **inert** — the response
  shows `real_calls: "available"` is *not* reached and stays `"offline"`, so the admin sees the
  env block. Audited; republishes the snapshot.
- **`POST /api/v1/admin/ai-settings/disable-ai`** → kill switch (§5).

Frontend: a **University Admin → AI Settings** surface renders alias selectors (from the
allowlist), feature-flag toggles, a budget input, a `real_calls` status badge
(offline/available/enabled), a `key_configured` indicator, and the kill switch. **No provider
name, model name, key, base URL, or token count is ever rendered.** Students and partners have
no entry point.

### 7. Scope boundary & first implementation slice

**This ADR covers (V1):** the `ai_settings` entity + singleton seed (migration `0022`); the
`EffectiveAiConfig` snapshot + `runtime_config` holder; the `resolver` with the env-ceiling /
DB-toggle precedence; rewiring the **four** consumers in §2 to read the snapshot; the
admin GET/PATCH/kill-switch endpoints with RBAC + audit + alias allowlist + masked responses;
and the `budget_guard` seam (no-op accumulator).

**Deferred (named, not built):** the metered `ai_usage_log` ledger + `402 BUDGET_EXCEEDED`
enforcement + per-tenant **token** budgets (AI_PRODUCT_SPEC §5.4/§11.2); the multi-row
`ai_task_model_configs` alias→concrete-model mapping in DB (stays in env/config for V1);
per-university `ai_settings` rows; circuit-breaker thresholds in DB (§5.2); A/B prompt testing
(§8.3); automated eval-gated rollout (§10); and any real-provider smoke run.

**First backend slice (for `backend-developer`):**
1. `0022_ai_settings` migration + `domain/models.py` `AiSettings` + singleton seed (defaults =
   current `config.py` values).
2. `app/ai/gateway/runtime_config.py`: `EffectiveAiConfig` + env-bootstrapped `current()` /
   `publish()`.
3. `app/modules/ai_settings/application/resolver.py`: build + publish with the §2 precedence;
   startup hook wired in app lifespan.
4. Rewire `gateway.factory.real_provider_active()` / `get_provider()`, `ai/cv/llm.py`,
   `extraction/adapters/structuring.py`, `documents/job_fit_service.py` to read
   `runtime_config.current()` (behaviour-preserving — the seeded snapshot equals today's env).
5. `application/settings_service.py` (get/update/kill-switch, RBAC + audit + allowlist),
   `application/budget_guard.py` (no-op seam), `api/router.py` + `api/schemas.py` (masked),
   mount under `/api/v1/admin/ai-settings`.
6. Tests (§Required tests).

**Then frontend (`frontend-developer`):** the University Admin → AI Settings surface (§6),
`API wired` → `browser verified`.

## Required tests

- **Precedence:** key absent ⇒ `real_calls_active=false` even with env+DB true; env gate false
  ⇒ false even with key+DB true; `rollout_state!='enabled'` ⇒ false; all-true ⇒ true.
- **Snapshot consumption:** `resolver.publish()` updates `runtime_config.current()` and
  `factory.real_provider_active()` reflects it; `cv/llm.generate_note` uses
  `current().chat_model_alias`; structuring/job-fit honour their flags.
- **Secrecy:** GET/PATCH responses never contain `openrouter_api_key`,
  `openai_compatible_base_url`, provider/model strings, or token counts; `key_configured` +
  `real_calls` derived fields present.
- **RBAC:** partner / student / unauthenticated ⇒ 403/404; non-university staff ⇒ 403;
  superadmin + university `ai_settings:manage` ⇒ 200.
- **Validation:** PATCH alias outside the allowlist ⇒ 422 (no model-path injection).
- **Rollback:** kill switch sets `real_calls_enabled=false` + `rollout_state='offline'`,
  republishes (next `real_provider_active()` false), and writes an audit row with diff.
- **Budget seam:** `budget_guard.check` reads `daily_budget_usd`; no-op accumulator never trips
  under offline provider.

## Consequences

- A future real key + `AI_REAL_CALLS_ENABLED=true` is activated by **one admin PATCH**, no code
  change — the resolution facade is the single seam.
- The gateway stays sync/ORM-free; `ai_settings` owns the only DB read and pushes a snapshot,
  preserving the one-way module→infra dependency.
- Admins gain governance (aliases, flags, budget, kill switch) and visibility (derived status)
  **without** ever seeing a provider, model, key, or token — secrecy is structurally enforced
  (no key column exists to leak).
- The deferred ledger/metering attaches at the named `budget_guard` accumulator + `ai_usage_log`
  point without reworking this entity.
- **Staleness window:** the snapshot is refreshed on startup + PATCH; a multi-process
  deployment would need a publish broadcast (Redis pubsub) — out of scope for the single-process
  local-first V1, flagged for the production scaling ADR.

## Doc conflicts resolved (precedence: product > business > security > arch > API/data)

1. **`ai_task_model_configs` multi-row table (AI_PRODUCT_SPEC §5.1) vs single `ai_settings`
   row (CLAUDE.md naming default).** The spec's per-alias DB-stored provider+model mapping is
   the **end-state**. Resolution (arch > API/data): V1 keeps the alias→concrete-model mapping
   in **env/config** and stores **only the selected alias name** in `ai_settings`. `ai_task_model_configs`
   is **deferred**. **Flag:** AI_PRODUCT_SPEC §5.1 should note the V1 mapping lives in config,
   not DB.
2. **Per-tenant monthly *token* budgets (§5.4/§11.2) vs single-tenant platform.** Platform is
   VinUni-only (DATA_MODEL tenancy). Resolution: V1 ships one **per-day USD** budget field +
   check seam; per-tenant token budgets + `ai_usage_log` enforcement are **deferred**. **Flag:**
   §11.2 "per tenant" reads as multi-tenant; clarify single-tenant V1.
3. **"Configurable in ai_settings" for circuit-breaker thresholds (§5.2).** Deferred; the table
   does not carry thresholds in V1. **Flag:** §5.2 to mark thresholds as a later `ai_settings`
   extension.
4. **No conflict on secrecy** — CLAUDE.md, SECURITY_PRIVACY §AI Safety, and ENVIRONMENT secret
   policy agree: alias-only, keys in env, nothing leaked. This ADR is strictly conformant.

## Implementation checklist (next backend slice)

- [ ] `0022_ai_settings` migration + singleton `'platform'` seed (defaults = current config).
- [ ] `modules/ai_settings/domain/models.py` `AiSettings`.
- [ ] `ai/gateway/runtime_config.py` `EffectiveAiConfig` + env-bootstrapped holder.
- [ ] `modules/ai_settings/application/resolver.py` (precedence + publish) + startup wiring.
- [ ] Rewire 4 consumers to `runtime_config.current()` (behaviour-preserving).
- [ ] `application/settings_service.py` (RBAC + audit + allowlist) + `application/budget_guard.py`.
- [ ] `api/router.py` + `api/schemas.py` (masked) under `/api/v1/admin/ai-settings` (GET/PATCH/disable-ai).
- [ ] Tests per §Required tests; OpenAPI contract check; alias-allowlist check.
