# AI Usage Governance — Usage-Aware Path, Ledger Idempotency, Identity Masking

Status: **partial slice shipped 2026-07-08** on branch `feat/ai-layer-gov`.
Owner: ai-engineer + backend. Source rules: `CLAUDE.md` (AI usage accounting),
`.claude/rules/ai.md`, `docs/AI_PRODUCT_SPEC.md` §5.4/§11, `docs/API_CONTRACTS.md`
ADR-0011.1.

This doc records what changed, the contract additions, and the exact remaining
backlog so the rest can be finished without re-discovery.

## 1. Problem (from the AI-layer review)

`AiTaskRunner` (`backend/app/ai/gateway/task_runner.py`) is the intended single
governed entry point (budget → input-guard → provider → output-guard → durable
`ai_usage_log` ledger → Langfuse/`ai_ops_event` telemetry). It was used by only 4
call-sites. The majority of AI features funnelled through the
`backend/app/ai/cv/llm.py` `generate_note` / `generate_json_note` hub and through
the extraction vision/structuring adapters, which emitted a **metadata log line
only** — no budget check, no DB ledger row, no telemetry. Two provider/model
registry LIST endpoints also leaked real provider identity + `base_url` to
non-superadmin `ai_settings:read` university staff.

## 2. What shipped in this slice

### 2.1 `AiUsageContext` — the attribution + accounting carrier
`backend/app/ai/gateway/usage_context.py`. Threaded from the service layer into
the gateway. Fields: `db`, `user_id`, `session_id`, `org_id`, `tool_class`,
`billing_scope`, `idempotency_key`. Degrades safely: `db is None` → metadata log
line only (legacy behaviour), so adopting it at a call-site is never breaking.

`billing_scope` ∈ `{student, partner_org, university_budget, platform, system}`;
`billing_scope_for_persona()` maps an auth persona to its default scope. Per
`CLAUDE.md`: student/partner exhaustion may route to a plan/credit upgrade;
university-staff exhaustion routes to an admin limit/request workflow (never a
billing upsell); platform/system are internal scopes on the platform budget.

### 2.2 Reusable governance wrapper
`backend/app/ai/gateway/governance.py` — `precheck_budget()` + `record_usage()`.
Gives call-sites that must keep their own provider/message handling (e.g.
`cv/llm`, whose `get_provider()` is the offline-eval patch point, and the raw-httpx
extraction adapters) the same three governance steps as `AiTaskRunner` — budget
pre-check, durable ledger, ops telemetry — **without** changing the provider call
or offline determinism.

### 2.3 `cv/llm` hub is now governed
`generate_note` / `generate_json_note` accept an optional `usage`. With a context
they budget-check (real provider only), write a real-cost `ai_usage_log` row, and
emit an `ai_ops_event`/Langfuse span. Without one, behaviour is byte-identical to
before (the offline eval datasets are unaffected — verified via the eval gate).

### 2.4 Ledger idempotency (no double-charge)
`ai_usage_log.idempotency_key` (nullable, UNIQUE) + migration
`0083_ai_usage_idempotency_key`. `log_ai_usage_async()` now returns whether it
inserted; a duplicate key skips the insert **and** the telemetry span, so a
retried logical operation never double-charges the ledger or double-counts
telemetry. Multiple NULLs are allowed (calls opt out by passing no key).

### 2.5 Provider/model identity masking (leakage fix)
`GET /admin/ai-settings/providers` and `/model-aliases` now mask real identity for
callers without `ai_settings:view_provider_identity` (superadmin bypasses),
returning a curated `vendor_label` + status only; reveals are audited. `base_url`
is now **never** returned at any privilege level (removed from `_serialize_provider`
entirely). Single source of truth: `settings_service.can_view_provider_identity()`.

### 2.6 Callers wired this slice
- Student CV AI tasks (rewrite / bullets / draft / fill / optimize) via
  `CvAiContext.usage`, set in `documents.cv_ai_service._gather_context` — scope
  `student`.
- Cover letter (`opportunities.cover_letter_service`) — scope `student`.
- Partner JD generation (`opportunities.jd_ai_service`, both call-sites) — scope
  `partner_org`.

### 2.7 Tests
- `tests/ai/gateway/test_usage_governance.py` — context validation, ledger+ops
  written with a context / not without, idempotency no-double-charge (unit +
  through `generate_note`), 402 propagation with no billable row, provider-failure
  → `AI_UNAVAILABLE` still ledgered.
- `tests/integration/test_ai_provider_identity_masking.py` — provider/alias list
  masking for read-only holders, reveal for identity holders, `base_url` never
  present, permission gating.

## 3. Backlog — remaining bypasses (ranked)

All of these currently emit the metadata log line only (or, for raw-httpx paths,
nothing) and should adopt `AiUsageContext` via `governance.record_usage` /
`precheck_budget`, or route through `AiTaskRunner` where input-policy is desired.

| # | Call-site | Notes / effort |
|---|-----------|----------------|
| 1 | `ai/extraction/adapters/vision.py`, `ai/extraction/jd/vision.py` | **Paid vision calls** over raw httpx. Highest cost priority. Thread `AiUsageContext` through the ingestion cascade. |
| 2 | `ai/extraction/adapters/structuring.py` | Raw httpx, **no usage record at all**. Gated off by default (`cv_llm_structuring_enabled`). |
| 3 | `ai/cv/semantic_scorer.py` | Uses `generate_json_note`; high-volume fit pipeline. Thread `usage` from `documents.job_fit_service` / `opportunities.job_search_service`. |
| 4 | `ai/cv/skill_translation.py` | `get_provider_for_alias` direct; fit pipeline. |
| 5 | `opportunities.interview_sim_service`, `competition_service`, `dashboards.market_intelligence_service` | `generate_(json_)note`; have db+principal. |
| 6 | `recruitment.scorecard_ai_service`, `screening_brief_service` | Partner scope. |
| 7 | `ai/cv/edit_command.py` | Natural-language CV edit; student scope. |
| 8 | `ai_assistant.session_history._summarize_history` | **Full bypass** (no budget/ledger/log). |
| 9 | `ai_assistant.tool_loop._llm_complete` | Budget+ledger done manually; only missing ops telemetry — add `_record_telemetry`. |
| 10 | `ai/retrieval/embeddings.py` | Ledger when `db` passed; missing budget + ops telemetry. Thread `usage`. |
| 11 | `ai/agents/worker_tasks.py` | Dispatches to `cv.llm.generate_json_note`; pass a `system_context(db)`. |

Already fully governed (reference): `retrieval/rerank.rerank_jobs`,
`opportunities.translation_service`, `ai_assistant.tools.cv_ai` (interview tool),
`ai_assistant.tool_loop` final stream.

## 4. Backlog — deeper work

- **billing_scope → budget routing.** `billing_scope` is currently attribution +
  future-UX only. Make `budget_guard.check_async` select the budget by scope
  (student → per-user cost quota; partner_org → per-org budget; university_budget
  → university internal budget with admin-request UX on exhaustion; platform/system
  → platform budget). Needs product limits per scope (some exist in
  `billing.limit_facade`). Persist `billing_scope` on `ai_usage_log`/`ai_ops_event`
  for per-scope reporting.
- **Idempotency key derivation.** Standardise stable keys per logical op
  (e.g. `cv_rewrite:{cv_version}:{section}`) at each caller so provider-level
  retries dedup, not just exact replays.
- **RBAC tightening.** Registry CRUD (`POST/PATCH /providers`, `/model-aliases`)
  is still reachable by `ai_settings:manage` university staff; `CLAUDE.md` intent
  is superadmin-only for the *real* registry. Decide + gate (out of scope here to
  avoid breaking the existing `manage`-based tests).
- **Real-token cost.** `ai_usage_log.cost_usd` uses the char-estimate even when the
  provider returned exact token counts; only the admin-only `ai_ops_event` uses
  real tokens. Unify on real tokens when available.
