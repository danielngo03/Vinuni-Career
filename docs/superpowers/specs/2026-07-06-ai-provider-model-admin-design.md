# AI Provider & Model Admin — Design Spec

- **Date:** 2026-07-06
- **Owner decision source:** brainstorming session (this repo)
- **Module:** `ai_settings` + `app/ai/gateway`, frontend `components/ai-settings`
- **Status:** approved for implementation

## 1. Goal

Make the admin-facing AI configuration behave like a real production system:

1. **Direct model binding, no alias catalog.** Admin (and `.env`) bind each AI
   *function* directly to a concrete provider + real model id. Drop the
   `chat_cheap` / `chat_standard` named-alias catalog entirely.
2. **Strong-but-cheap default models** seeded from `.env`, overridable by admin.
3. **Encryption-at-rest fit for a large system**: dedicated key, key rotation
   (versioned, no downtime), decoupled from the JWT secret, masked hints.
4. **Multi-provider rotation**: per-function ordered provider+model list with a
   `priority` (failover) ↔ `round_robin` strategy toggle, health-aware.
5. **Health probes**: admin can test that a provider key works and a model
   responds, with stored last-status.
6. **Frontend redesign (v9 Monochrome)**: drag/drop ordering, health pills,
   "Test" actions, folded routing view. Remove current gradient/multi-color UI.

Non-goal for this spec: end-user visibility of any model/provider — that stays
forbidden (see §7).

## 2. Current state (verified)

- `app/ai/gateway/factory.py` already implements a per-provider **circuit
  breaker** (3 fails → open 60s) and returns a `FallbackChainProvider` when an
  alias has >1 healthy hop — i.e. **priority-failover already works**.
- `fallback_chain.py` sequences ordered hops, advancing only on
  `AIUnavailableError`.
- `provider_registry.py` seeds built-in providers + a **named-alias catalog**
  and does CRUD; keys are Fernet-encrypted (`provider_key_crypto.py`).
- `runtime_config.py` holds the immutable published snapshot
  (`provider_routes`, `provider_route_chains`, `provider_key_ciphertexts`).
- `ai_settings` singleton (`domain/models.py`) stores 5 `*_model_alias` columns
  + flags + budget; `resolver.py` publishes the snapshot on startup / PATCH.
- Frontend `ai-provider-manager.tsx` (882 lines) does provider+alias CRUD but
  uses gradients + emerald/violet/sky — **violates v9 Monochrome**.
- **Gaps:** no active health/test probe; no round-robin; alias catalog is the
  confusing double-indirection the owner wants gone; encryption key falls back
  to `JWT_SECRET_KEY` (coupling) with no rotation/versioning.

`chat_cheap` and friends appear in **~152 references across ~19 app files + 20
test files** — a hard rename is high-risk, so we keep them as hidden resolvable
synonyms (see §6.5).

## 3. Key decisions (owner-approved)

| # | Decision |
|---|---|
| D1 | No alias catalog. Six fixed **function slots** bind directly to real models. |
| D2 | Slot handle names: `chat_default`, `reasoning_default`, `embedding_default`, `rerank_default`, `eval_default`, `vision_default`. Internal only — never shown to end users; act as a leak-safe label if a model id ever slips into a log/response. |
| D3 | Default models (all via OpenRouter, one key): see table below. |
| D4 | Encryption: `MultiFernet` + `key_version` + masked `last4`; dedicated key required in prod (fail-fast), JWT-derived key only as a warned local-dev fallback. |
| D5 | Rotation configurable per slot: `priority` (default) or `round_robin`; both health-aware (skip circuit-open hops). |
| D6 | Health probe endpoints for providers and slot models; store last status. |
| D7 | Full frontend redesign in v9 Monochrome with drag/drop ordering + Test actions; fold the routing canvas into one screen. |

### Default model table (seeded from `.env`)

| Slot | Provider | Model id |
|---|---|---|
| `chat_default` | openrouter | `deepseek/deepseek-v4-flash` |
| `reasoning_default` | openrouter | `deepseek/deepseek-r1` |
| `embedding_default` | openrouter | `text-embedding-3-small` |
| `rerank_default` | openrouter | `deepseek/deepseek-v4-flash` |
| `eval_default` | openrouter | `deepseek/deepseek-v4-flash` |
| `vision_default` | openrouter | `google/gemini-2.5-flash` |

`deepseek/deepseek-v4-flash` verified on OpenRouter at ~$0.098/1M in, $0.197/1M
out — cheaper than Gemini 2.5 Flash, adequate for chat/eval/rerank.

## 4. Architecture

### 4.1 Slot model (D1/D2)

- **Function slots** are the six fixed roles above. They are the leak-safe
  identifiers passed through the gateway as the `alias`/`task` parameter today —
  no code path outside `openai_compatible.py` ever needs a concrete model id.
- Each slot binds to `(provider, model_id)` + an ordered fallback list + a
  rotation strategy. The concrete model id is resolved only at the HTTP call.
- The named-alias *catalog CRUD* goes away from the admin surface. `AiModelAlias`
  rows are repurposed as **slot bindings** — one row per active slot (extra
  rows allowed for fallbacks). Admin edits "which model for Chat", not "create
  an alias named X".

### 4.2 Encryption (D4) — `provider_key_crypto.py`

- New env: `AI_PROVIDER_KEY_ENCRYPTION_KEYS` — comma-separated Fernet keys,
  **newest first**. Build a `MultiFernet(keys)`: encrypt with keys[0], decrypt
  with any. This gives **zero-downtime rotation**: add a new key at the front,
  re-encrypt lazily/by routine, then drop the old key.
- `key_version` column on `ai_provider_configs` records which key generation
  encrypted the stored ciphertext (a short fingerprint, not the key).
- **Prod fail-fast:** when `APP_ENV != local` and no real key is configured,
  raise at startup. Local dev may derive from `JWT_SECRET_KEY` but logs a loud
  one-time warning (kept only for developer convenience).
- Store `api_key_last4` on write so the UI can render `sk-…4f2a` without ever
  decrypting or returning plaintext. Plaintext is never logged or serialized.
- Rotation routine `reencrypt_all_provider_keys()` re-wraps ciphertexts with
  keys[0] and updates `key_version` (admin action + optional startup drift
  check).

### 4.3 Rotation (D5)

- `rotation_strategy` column on the slot binding: `priority` | `round_robin`.
- Ordered hops stored as `fallback_bindings` JSON: `[{provider_name, model_id}]`
  (index 0 = primary). Replaces the model-less `fallback_provider_names` so each
  hop can carry its own model id (providers rarely share model ids).
- Snapshot gains `provider_route_strategies: {slot: "priority"|"round_robin"}`.
- Gateway `factory.get_provider_for_alias`:
  - Build healthy hops (skip circuit-open / no-key) — unchanged.
  - `priority`: return `FallbackChainProvider(hops)` in stored order (today's
    behaviour).
  - `round_robin`: rotate the starting index by a per-slot in-process counter,
    then wrap the rotated list in `FallbackChainProvider` so a failed pick still
    falls through to the rest. Health-aware because circuit-open hops are
    already excluded.

### 4.4 Health probe (D6)

- `POST /admin/ai-settings/providers/{id}/test` — minimal auth check against the
  provider endpoint (a cheap `models`/tiny-completion ping). Returns
  `{ reachable, authenticated, latency_ms, checked_at, reason_code }`. Never
  echoes raw upstream error bodies. Persists `last_health_status` +
  `last_health_checked_at`.
- `POST /admin/ai-settings/model-aliases/{id}/test` (slot binding) — a tiny real
  call in the slot's family (chat completion / embedding) to confirm the model
  answers.
- Probes are **real calls**: gated by `AI_REAL_CALLS_ENABLED`, counted against
  budget / `AI_MAX_REAL_CALLS_PER_TEST_RUN`, and require an explicit UI confirm
  ("this performs a real API call"). Admin-only; audit-logged.

### 4.5 Frontend (D7)

One AI Settings screen, three sections, all v9 Monochrome (ink + green/amber/red
semantic only, no gradients):

1. **Runtime & rollout** — real-calls toggle, rollout state, budget, kill switch.
2. **Providers** — mono rows: name, type, base_url, key hint (last4), **health
   pill**, **Test** button, active switch, edit. "Add provider" modal with
   encrypted key field.
3. **Model routing** — one card per function slot. Each shows an **ordered,
   drag-and-drop provider+model list** (dnd-kit), a **Priority ↔ Round-robin**
   toggle, per-hop **Test** + health dot. This replaces the CSV fallback field
   and folds in the old routing canvas concept.

i18n vi/en. Confirm dialogs for real-call tests and kill switch.

## 5. Data model / migrations

New Alembic migration (upgrade + downgrade):

- `ai_provider_configs`: add `api_key_last4 VARCHAR(8) NULL`,
  `key_version VARCHAR(32) NULL`, `last_health_status VARCHAR(20) NULL`,
  `last_health_checked_at TIMESTAMPTZ NULL`.
- `ai_model_aliases`: add `rotation_strategy VARCHAR(20) NOT NULL DEFAULT
  'priority'`, `fallback_bindings JSON NULL`, `last_health_status VARCHAR(20)
  NULL`, `last_health_checked_at TIMESTAMPTZ NULL`. Keep `fallback_provider_names`
  nullable for back-compat; new writes use `fallback_bindings`.
- Data migration: seed the six `*_default` slot bindings from `.env`/config if
  absent; leave legacy `*_cheap` rows in place as hidden synonyms.

## 6. Backward compatibility & migration strategy

1. **Slots are additive.** Seed `chat_default` … `vision_default` and point the
   six `AiSettings.*_model_alias` columns + config defaults at them.
2. **Legacy names stay resolvable.** `*_cheap/*_free/*_mini` remain in
   `_BUILTIN_MODEL_MAP` + `known_aliases()` + seeded rows, but are **removed
   from the allowlist/UI**. Nothing that still passes `chat_cheap` breaks.
3. **Sweep the ~6 hardcoded internal call sites** (extraction/embeddings/jd) from
   `*_cheap` to the matching `*_default` slot.
4. **Tests** that assert the exact default alias name get updated to the new
   slot; tests that merely call a legacy alias keep passing via the synonym.
5. `.env` / `.env.example`: replace `AI_DEFAULT_MODEL_ALIAS=chat_cheap` (+ the
   reasoning/embedding/eval/rerank alias vars) with concrete
   `AI_CHAT_MODEL` / `AI_CHAT_PROVIDER` / `AI_REASONING_MODEL` / … pairs, and add
   `AI_PROVIDER_KEY_ENCRYPTION_KEYS`. The real `backend/.env` gets the same
   non-secret edits; existing real key values are never touched or printed.

## 7. Security & privacy

- Model ids / provider names remain **admin-only**. No student/partner/guest
  response, log, or error may contain them. Slot handles (`chat_default`) are the
  only labels allowed to travel — and they carry no vendor/model information.
- API keys: encrypted at rest, write-only over the API, `has_api_key` + `last4`
  hint only in responses. Never logged.
- Health probe + provider-identity views are audit-logged and RBAC-gated
  (`ai_settings` admin; raw identity behind `view_provider_identity`).
- Real-call gating (`AI_REAL_CALLS_ENABLED`, budget) applies to probes.

## 8. Testing

- Unit: encryption round-trip + rotation (decrypt old ciphertext after key
  rotation), last4 masking, prod fail-fast.
- Unit: round-robin distribution + failover skip-on-circuit-open; priority
  unchanged.
- Integration: provider/slot CRUD, health-probe endpoints (mocked upstream),
  RBAC 403 for non-admin, audit rows on writes.
- Contract: no model id / provider name in any non-admin serializer; leakage
  test in adversarial eval set.
- Regression: full `ruff` + `mypy` + `pytest` after the alias→slot sweep.
- Frontend: routing drag/drop reorder persists; Test action confirm dialog;
  monochrome (no gradient classes); vi/en; 375/768/1024/1440 + dark theme.

## 9. Phasing

- **P1 — Backend foundation:** slot model + direct binding, `.env`/config/seed,
  drop alias catalog from allowlist (keep synonyms), sweep call sites.
- **P2 — Encryption:** MultiFernet + `key_version` + `last4` + fail-fast +
  migration + rotation routine.
- **P3 — Rotation + health:** `rotation_strategy` + `fallback_bindings`,
  round-robin in gateway, two Test endpoints, stored health status.
- **P4 — UI:** Monochrome redesign, provider/key/health, drag/drop routing,
  fold canvas, i18n, browser QA.

## 10. Risks / open questions

- Alias→slot sweep must be verified by the full test gate; synonyms reduce but
  don't eliminate risk.
- `text-embedding-3-small` via OpenRouter routing is inherited from current
  defaults; if OpenRouter doesn't serve embeddings, admin can rebind embedding
  to the `openai` provider — the UI supports this.
- Round-robin in-process counter is per-worker (not globally fair across
  workers); acceptable for V1 (cost-spreading, not strict balancing).
