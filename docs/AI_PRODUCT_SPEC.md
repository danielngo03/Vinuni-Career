# AI Product Spec — VinUni Career Platform

> Phiên bản: 2.3 | Cập nhật: 08/07/2026 (product-owner operating-model reconciliation — §5.4 now matches the shipped `ai_usage_log`/`ai_ops_event` split and adds billable AI usage rules; see `docs/PRODUCT_OPERATING_MODEL.md`)  
> Source of truth for AI task design, agentic architecture, tool registry, safety, evaluation, and rollout.

---

## 1. Principles

- AI must solve real workflow pain, not decorate the UI.
- AI is advisory by default; consequential decisions require human confirmation.
- AI write actions require explicit user confirmation and audit logging.
- End users never see provider names, model names, token counts, latency, raw confidence, prompt text, OCR internals, embedding internals, chunk IDs, similarity scores, or internal status codes. This is absolute for guests, students, partners/employers, and ordinary university staff. Only platform superadmins may view or manage the real provider/model registry, and only inside superadmin AI operations/settings surfaces. API keys and base URLs are never returned by any API.
- AI must degrade gracefully when unavailable.
- Human has final say on moderation, fraud, approvals, and all consequential decisions — AI is advisory only.
- Internal prompt templates, system/developer/task instructions, eval rubrics, and guardrail text are written in English for maintainability. User-facing output language is controlled separately by `target_language`, detected CV/document language, or explicit user locale.

---

## 2. Permission Classes

| Class | Meaning | Examples | Requirement |
|---|---|---|---|
| `read_only` | Reads permitted data, returns advice | search jobs, analyze CV, explain JD, RAG query | RBAC + privacy filter |
| `confirmation_required` | Mutates data after explicit confirmation | apply job, withdraw, set primary CV, register event | confirmation card + audit |
| `restricted_admin` | University/admin-only operational AI | provider health, moderation suggestion, fraud review | admin RBAC + audit |
| `human_review` | AI suggests, human decides, no auto-final | moderation, fraud, partner/event/ad approval | no auto-final decision |

---

## 3. AI Task Matrix

| Feature | Persona | Data Sources | Tool/Task | Permission | Eval Dataset | Fallback | Rollback |
|---|---|---|---|---|---|---|---|
| CV extraction | Student | uploaded CV, OCR text | `cv_extraction` | `read_only` | CV fixture set by layout/language | manual review queue / local parser | disable parser version |
| CV template fill | Student | uploaded CV extraction, existing builder CV, raw notes, confirmed profile facts | `fill_cv_template_from_sources` | `confirmation_required` | source-to-template fixtures | manual template import | disable tool, keep manual builder |
| CV first draft | Student | raw notes, selected template, uploaded extraction, short questionnaire, confirmed profile facts | `draft_cv_from_sources` | `confirmation_required` | first-CV rubric set | guided blank template | disable draft generation |
| CV bullet generation | Student | user raw notes, selected section | `generate_cv_bullets` | `confirmation_required` | bullet quality + factuality set | bullet examples | disable generation |
| CV section rewrite | Student | selected section, user instruction | `rewrite_cv_section` | `confirmation_required` | rewrite rubric set | manual editor | disable rewrite |
| Natural-language CV canvas edit | Student | current CV version, selected canvas element/section, user instruction, allowed source facts | `natural_language_cv_canvas_edit` | `confirmation_required` | command-to-patch fixtures | manual canvas edit | disable command bar, keep manual editor |
| CV job tailoring | Student | CV, target job, JD, skills taxonomy | `optimize_cv_for_job` | `confirmation_required` | CV-JD tailoring set | deterministic skill diff | disable tailor action |
| CV recommendation for job | Student | active CV library, target job, JD, skills taxonomy, stale-CV rules | `recommend_cv_for_job` | `read_only` | CV-JD ranking set | deterministic category score | hide AI explanation, keep score bands |
| ATS keyword suggestions | Student | CV, JD | `ats_keyword_suggestions` | `read_only` | CV-JD keyword set | deterministic keyword overlap | hide AI suggestions |
| CV fabrication check | Student/University | CV claims, profile evidence, uploaded extraction | `cv_fabrication_check` | `human_review` if high risk | claim-evidence fixtures | rule-based warnings | disable high-risk flagging |
| CV quality analysis | Student | confirmed CV content and template metadata | `analyze_cv` | `read_only` | scored CV examples | rules-based checklist | hide AI narrative, keep checklist |
| CV per job advice | Student | CV, JD, skills taxonomy | `analyze_cv_for_job` | `read_only` | CV-JD pairs | deterministic skill diff | disable detailed explanation |
| Semantic job search | Student | jobs, profile, search query | `search_jobs` | `read_only` | query relevance set | keyword search | switch ranking to keyword |
| Match explanation | Student/Partner | CV, JD, match score inputs | `get_match_explanation` | `read_only` | labeled explanations | show deterministic skill overlap | hide explanation |
| Talent pool semantic search | Partner | consented candidate CV embeddings (pgvector), skill/experience filters, posted job OR pasted/uploaded external JD | `talent_pool_search` | `read_only` + `talent_pool:search` | candidate↔JD ranking + external-JD fixtures + privacy set | deterministic keyword + structured-filter search | disable semantic rank, keep filters |
| Talent pool match reasons | Partner | top-ranked candidates, JD/brief, skills taxonomy | `talent_pool_rerank_reasons` | `read_only` + `talent_pool:search` | match-reason quality + no-leak set | hide reasons, keep ranked list | disable LLM rerank |
| Student job competition intelligence | Student | target job, hiring target/seats, deadline, application volume buckets, source mix, aggregate applicant quality distribution, student's selected CV fit | `student_job_competition_intelligence` | `read_only` | privacy-safe job pool scenarios | hide competition widget, keep CV fit | disable AI narrative, keep deterministic buckets |
| JD writer | Partner | partner inputs, templates | `jd_generation` | `confirmation_required` | JD quality set | template builder | disable generation |
| JD bias checker | Partner/University | JD text, policy rules | `bias_detection` | `human_review` | bias phrase set (28 cases, 5 categories, implemented) | deterministic policy scanner | require manual review |
| AI assistant chat | Student | profile, CVs, jobs, apps | `chat` | mixed by tool | conversation eval set | canned guidance + search links | disable tool calls |
| Apply via assistant | Student | job, selected CV, answers | `apply_job` | `confirmation_required` | tool confirmation tests | route to apply form | disable tool |
| Interview simulator | Student | JD, Q&A bank, profile | `interview_sim` | `read_only` | interview rubrics | static question bank | disable feedback scoring |
| Scorecard assistant | Partner | interview notes, criteria | `scorecard_suggest` | `human_review` | note-score examples | blank scorecard | disable suggestion |
| Moderation suggestion | University | job/ad/review/event content | `content_moderation` | `human_review` | policy violation set | manual moderation queue | disable auto-flag |
| Fraud detection | University | profile/docs/activity signals | `fraud_detection` | `human_review` | fraud signal fixtures | rule-based risk flags | remove AI signal |
| Market intelligence | University | JDs, outcomes, trends | `market_intelligence` | `restricted_admin` | aggregate trend fixtures | scheduled SQL reports | hide AI summary |
| Platform KB query | All auth users | platform knowledge_base_chunks | `knowledge_base_query` | `read_only` | 10 FAQ + 5 adversarial + 5 no-result | static fallback message | disable RAG |
| Partner KB query | Student (with access) | partner knowledge_base_chunks | `knowledge_base_query` | `read_only` + partner access | 10 company-doc Q&A + 5 out-of-scope | "contact partner directly" | disable per-partner KB |
| Per-job KB query | Student (active applicant) | job knowledge_base_chunks | `knowledge_base_query` | `read_only` + active application | 5 job-guide Q&A + 3 unauthorized | "contact recruiter directly" | disable per-job KB |
| Document embedding | System (Celery) | uploaded file text chunks | `knowledge_base_ingest` | `restricted_admin` | — | retry 3× then FAILED | roll back to previous doc version |

> **Implementation status (2026-07-02):** all rows in the matrix above now
> have real backend implementations with offline eval coverage (21 task
> families in the CI gate).
>
> - `bias_detection` — deterministic MVP (`app/ai/safety/bias_detection.py`),
>   advisory `bias_check` field on JD drafts, and high-risk findings now
>   PERSIST to `human_review_queue` (migration `0052_human_review_queue`,
>   module `app/modules/moderation/`, §9.3).
> - `content_moderation` — deterministic scanner
>   (`app/ai/safety/content_moderation.py`, `check_content`): fee-collection
>   scams, pyramid/MLM, unrealistic-earnings bait, off-platform contact
>   pressure, adult content (vi/en). Advisory `content_check` field on JD
>   drafts; `policy_violation` escalates to `human_review_queue`.
> - `fraud_detection` — deterministic rule engine
>   (`app/ai/safety/fraud_detection.py`, `assess_fraud_signals`) + on-demand
>   scan `POST /api/v1/moderation/fraud-scan/jobs/{id}` collecting real
>   org/posting/content signals via application facades. `risk_score >= 0.85`
>   (§9.3) escalates; raw score never leaves staff surfaces.
> - `market_intelligence` — aggregate-only read model
>   (`dashboards/application/market_intelligence_service.py`,
>   `GET /api/v1/dashboards/university/market-intelligence`) with optional AI
>   narrative (prompt `market_intelligence/v1`); degrades to pure aggregates
>   when the gateway is unavailable or data is low-signal.
> - Human review loop (§9.3): `human_review_queue` table + university-only
>   list/resolve/dismiss API (`/api/v1/moderation/review-queue`). Dismissals
>   feed the §10.4 human-override-rate SLO. **Still open:** moderator
>   notification fan-out on enqueue, agent-loop (`LOOP_EXHAUSTED` /
>   `REPEATED_OUTPUT_BLOCK`) escalation wiring, and the frontend moderator
>   queue UI (`frontend-developer`).
>
> All three formerly-unbuilt features are deterministic/aggregate-first by
> design (§1: prefer rules before model calls); none of them auto-blocks —
> a university human always makes the final call.

### 3.1 CV AI Product Rules

- CV Studio is CV-first. AI must not require a completed profile form before
  upload, template selection, drafting, tailoring, or scoring can work.
- Accepted data sources are uploaded CV extraction, existing builder CVs, raw
  notes, selected template schema, job/JD text, skill taxonomy, and confirmed
  profile facts. Unconfirmed profile text is advisory only.
- Local parsing and deterministic checks run first. Do not call an LLM for blank,
  corrupt, infected, password-protected, rejected-security, or not-CV uploads.
- Multilingual baseline is Vietnamese and English. Language detection may route
  OCR/parser prompts, but provider/model names and OCR internals remain hidden.
- CV content language is not forced by UI locale. If the CV/source material is
  mostly English, default generated CV content to English; if it is mostly
  Vietnamese, default to Vietnamese. The student can explicitly override the
  target language per generation/rewrite/export action.
- CV-to-job `score` is a user-facing product score from 0-100 with categories
  and evidence. It is not raw model confidence, embedding similarity, or a
  hiring decision.
- For job-fit recommendations, show the best CV to apply with, alternative CVs,
  stale-CV warnings, true evidence gaps, and "if true, add evidence" suggestions.
- AI must never invent education, employer, GPA, awards, certifications, dates,
  visa/work authorization, quantified outcomes, or language proficiency.
- Mutating CV actions produce pending diffs/drafts only. The student explicitly
  accepts, edits, or rejects changes.

### 3.2 Student Job Intelligence Rules

Logged-in student job detail should be useful before the student applies. It
should not show decorative "match" or "competition" badges without evidence.

Required outputs when sufficient data exists:

- best CV to apply with and alternative CVs;
- CV-JD fit score with category bands and evidence;
- missing evidence and truthful CV improvement suggestions;
- learning gaps mapped to skills/role families when available;
- deadline/application context and apply readiness;
- competition intelligence that helps the student decide whether to improve the
  CV, apply now, or find adjacent roles.

Competition intelligence is a privacy-safe product signal. It may use:

- hiring target/seats or a derived hiring-intent bucket;
- application count bucket and recent velocity;
- applicant pool quality distribution in aggregate buckets only;
- the student's CV fit score and percentile/bucket within the visible pool;
- recency/deadline, location/work-mode constraints, and source mix;
- historical funnel conversion for comparable jobs only when aggregate sample
  size is high enough.

Rules:

- Guests never see personalized fit or competition intelligence.
- Do not expose other candidates, raw CV text, exact applicant rankings, raw
  model confidence, embeddings, provider/model names, prompts, or token/cost
  internals.
- If data is low-signal, show what is known and hide/soft-disable the
  competition widget instead of inventing a precise score.
- AI may explain the deterministic signal in student-friendly language, but the
  deterministic service owns the core score/buckets.
- The UI must phrase this as guidance, never as a hiring probability guarantee.

### 3.3 Talent Pool Semantic Search Rules (owner decision 2026-07-10)

Talent Pool is AI semantic candidate search, not a masked "blind-search" card
wall. Full RBAC/audit/consent contract lives in
`docs/PARTNER_RBAC_ANALYTICS_SPEC.md`; the AI-specific rules are:

- Retrieval = pgvector dense search over **consented** candidate CV embeddings,
  intersected with deterministic structured filters (skills, experience,
  major/faculty, cohort, location/work-mode, availability, tier). Filters run
  before and after semantic ranking.
- The query may be a recruiter brief, an existing posted job, OR a pasted /
  uploaded **external JD that is not yet a posted job**. External JDs run through
  the same extraction/embedding path as posted jobs.
- An LLM rerank pass returns **human-readable match reasons** and evidence gaps
  per candidate. It never returns or surfaces a raw similarity/confidence number.
- Candidates are shown **identified** to authorized recruiters. There is no
  anonymized display, deterministic anonymous id, or reveal step (that flow is
  removed product-wide, owner decision 2026-07-10).
- Never expose provider/model names, embedding vectors, similarity scores,
  chunk ids, token counts, prompts, or any AI internals to partners.
- Fallback when the gateway/embeddings are unavailable: deterministic keyword +
  structured-filter search with an honest "AI ranking unavailable" state; never
  fabricated candidates, matches, or reasons.
- External-JD searches are quota-metered like other AI recruiting actions and
  audited (actor, org/department, JD reference/hash, result count).

---

## 4. Agentic Architecture

### 4.1 ReAct Tool-Calling Loop

The `ai_assistant` module implements a ReAct (Reason → Act → Observe) agent loop. Every chat turn follows this sequence:

```
User message
    │
    ▼
[1] Safety screening (input guard — see §9)
    │
    ▼
[2] Context injection
    │   - system prompt (static prefix, cache-eligible)
    │   - relevant conversation history (trimmed to budget)
    │   - retrieved KB chunks if query detected (RAG path)
    │   - current user profile summary
    │
    ▼
[3] LLM call → AI Gateway (see §5)
    │
    ├── [4a] text response → output guard → stream to client
    │
    └── [4b] tool_call detected
            │
            ▼
         [5] permission check (tool permission_class vs. user role)
            │
            ├── confirmation_required?
            │       │
            │       ▼
            │    pause loop → send confirmation_pending event to frontend
            │    wait for user_confirm / user_cancel
            │    on cancel: stop loop, acknowledge to user
            │    on confirm: proceed to [6]
            │
            └── read_only: proceed directly to [6]
            │
            ▼
         [6] tool executor (resolve inputs, call service, get tool_result)
            │
            ▼
         [7] append tool_call + tool_result to context
            │
            ▼
         [8] iteration_count += 1
            │
            ├── iteration_count >= MAX_ITERATIONS (default: 8)?
            │       → force-stop loop, return "I need to stop here" message
            │
            └── loop back to [3]
```

**Hard limits:**
- `MAX_ITERATIONS = 8` per turn — no infinite loops.
- `MAX_TOOL_CALLS_PER_TURN = 12` across all iterations.
- Each tool call has its own timeout (default 15s, configurable per tool).
- If any tool call times out, the loop stops and returns the partial result.

**State within a turn:** held in memory for the loop duration. Not persisted beyond the final response.

**State across turns:** `conversation_id` references `ai_sessions` table; history is fetched and trimmed on each new turn (see §12).

### 4.2 Multi-Agent / Workforce Pattern

> **Implementation status (2026-07-02): IMPLEMENTED for one real consumer.**
> `backend/app/ai/agents/{coordinator,workforce,worker_tasks,models,api}.py`
> is real: `bulk_screening_brief` (a partner screening every — capped at
> `MAX_SUBTASKS_PER_RUN=25` — applicant on one job in parallel) is fully
> wired end to end: `POST /api/v1/ai/workforce/screening-briefs` plans +
> dispatches, `GET /api/v1/ai/workforce/runs/{run_id}` polls status/results.
> Idempotent by design (`SubtaskSpec.key` dedup before any AI call — a
> Celery at-least-once redelivery can never double-charge or double-write),
> RBAC-checked at plan time and reused for the worker's own subtask
> execution (`Principal` is serialized into `context_json` and reconstructed
> inside the separate Celery process). Tests:
> `tests/unit/test_ai_workforce.py`, `tests/integration/test_ai_workforce_bulk_screening.py`.
>
> **Two documented deviations from this section's illustrative shape** (not
> silent — see the module docstrings for the full reasoning): (1) per-subtask
> results are persisted in a durable `ai_workforce_runs` Postgres JSONB row
> (migration `0050_ai_workforce_runs`), not "Redis with TTL 1 hour" — this
> codebase has no existing Redis-backed application-state abstraction and
> the rest of the platform already stores this exact shape of bounded state
> in Postgres JSONB; (2) the poll path is `GET /api/v1/ai/workforce/runs/{run_id}`,
> not `GET /api/v1/ai/jobs/{job_id}`, since `/jobs` is already the
> `opportunities` module's path.
>
> **Known, explicitly-scoped-out gap:** no real Celery worker process is
> started for the `ai` queue in any deployment yet
> (`app.ai.agents.worker_tasks` must be added to a worker's `--include` list —
> see that module's docstring for the exact command). Without it, a
> dispatched run's subtasks never execute outside of tests (which force
> `task_always_eager=True`). Adding that worker process/deployment config is
> an infra task, not an AI-code task — flag to `system-architect`/deployment
> owner before this feature is relied upon in production.
>
> A second workforce consumer (e.g. deep interview-question generation, a
> market-intelligence aggregate) should extend this framework — new
> `decompose_*`/`aggregate_*` functions in `coordinator.py` + a new
> `EXECUTORS` entry in `worker_tasks.py` — not fork a parallel pattern.

Some AI tasks are too long or too complex for a single LLM call in the ReAct loop. These use a **workforce pattern**: a coordinator agent plans subtasks and dispatches to specialized worker agents via Celery.

```
Coordinator Agent (main LLM call)
    │
    │  task_plan = [subtask_A, subtask_B, subtask_C]
    │
    ├── dispatch subtask_A → Worker: cv_pipeline_agent (Celery)
    ├── dispatch subtask_B → Worker: jd_analysis_agent (Celery)
    └── dispatch subtask_C → Worker: skill_match_agent (Celery)
            │
            ▼  (all workers complete → results stored in Redis)
            │
    Coordinator collects results → final synthesis LLM call → response
```

**When to use workforce pattern:**
- CV batch analysis (>1 CV)
- Deep interview simulator (generate 10+ questions with scoring rubrics)
- Market intelligence report (multi-domain aggregate)
- Any task estimate > 30s wall-clock time

**Module location:** `backend/app/ai/agents/workforce.py`

**Contract:**
- Coordinator returns `job_id` immediately to the API layer.
- Frontend polls `GET /api/v1/ai/jobs/{job_id}` or listens on WebSocket for job events.
- Worker results are stored per-subtask in Redis with TTL 1 hour.
- Final synthesis runs only after all subtasks complete (or with explicit partial-result handling).
- All subtasks are idempotent — safe to retry on Celery failure.

### 4.3 Tool Confirmation Protocol (Technical)

For `confirmation_required` tools, the agent pauses mid-loop and the frontend must handle a two-phase flow:

**Phase 1 — Pending (agent → frontend):**
```json
{
  "event": "tool_confirmation_required",
  "confirmation_id": "conf_abc123",
  "tool_name": "apply_job",
  "display_summary": {
    "title": "Nộp đơn vào vị trí này?",
    "body": "Bạn sẽ ứng tuyển vào [Job Title] tại [Company] bằng CV [CV Name].",
    "cta_confirm": "Xác nhận nộp đơn",
    "cta_cancel": "Huỷ"
  },
  "expires_at": "2026-06-26T12:01:00Z"
}
```

**Phase 2 — User response (frontend → backend):**
```
POST /api/v1/ai/sessions/{session_id}/confirm
{ "confirmation_id": "conf_abc123", "decision": "confirm" | "cancel" }
```

**Agent resumes:**
- `confirm` → tool executes → audit logged → result appended to loop context.
- `cancel` → loop stops → sends "Đã huỷ" acknowledgement message.
- `expires_at` exceeded without response → treated as `cancel`.

**Security:** `confirmation_id` is a signed token encoding `{session_id, tool_name, input_hash, user_id, expires_at}`. Backend re-validates all fields before executing.

### 4.4 Agent State and Session Management

```sql
-- ai_sessions table
CREATE TABLE ai_sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id),
  tenant_id UUID NOT NULL,
  context_type VARCHAR NOT NULL,   -- 'general' | 'job' | 'application' | 'kb'
  context_id UUID,                 -- job_id, application_id, or kb_id
  title VARCHAR(255),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  last_active_at TIMESTAMPTZ DEFAULT NOW(),
  is_archived BOOLEAN DEFAULT FALSE
);

-- ai_messages table
CREATE TABLE ai_messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id UUID NOT NULL REFERENCES ai_sessions(id),
  role VARCHAR NOT NULL,           -- 'user' | 'assistant' | 'tool_call' | 'tool_result'
  content TEXT,
  tool_name VARCHAR,
  tool_call_id VARCHAR,
  token_count INT,
  model_alias VARCHAR,             -- internal alias only, never exposed
  created_at TIMESTAMPTZ DEFAULT NOW()
);
```

**Session ownership:** sessions are user-scoped, never cross-tenant. A student cannot access another student's session.

---

## 5. AI Gateway

### 5.1 Provider Adapter Interface

All AI calls go through the gateway — no module calls a provider SDK directly.

```python
# backend/app/ai/gateway/base.py
class ProviderAdapter(Protocol):
    async def chat(
        self,
        messages: list[Message],
        model_alias: str,
        stream: bool,
        max_tokens: int,
        tools: list[ToolDef] | None,
    ) -> ChatResponse | AsyncIterator[ChatChunk]: ...

    async def embed(
        self,
        texts: list[str],
        model_alias: str,
    ) -> list[list[float]]: ...

    async def health(self) -> ProviderHealth: ...
```

**Provider adapters:** `openai_compatible.py` (OpenAI-compatible surface — covers OpenAI, Azure, Ollama, OpenRouter, and any campus-hosted OpenAI-compatible endpoint) and `offline.py` (deterministic, no network — used by CI/eval and as the default fallback). `gemini_native.py` is **not implemented** (2026-07-01) — there is no native Gemini adapter today; a Gemini-family model can only be reached if it exposes an OpenAI-compatible endpoint. Add a native adapter only when a concrete provider requires it, and register it in `provider_registry.py`.

**Model alias:** the gateway maps `"chat_default"` → provider + model from
`ai_task_model_configs`. The real provider/model registry is managed by
platform superadmins only; non-superadmin modules and admin surfaces know only
the alias/slot handle.

### 5.2 Circuit Breaker

```
Per-provider circuit state machine:
  CLOSED → (failure_count >= threshold) → OPEN
  OPEN   → (timeout elapsed)           → HALF_OPEN
  HALF_OPEN → (probe success)          → CLOSED
  HALF_OPEN → (probe failure)          → OPEN

Thresholds (configurable in ai_settings):
  failure_threshold:     5 consecutive errors
  open_timeout:          60 seconds
  probe_request_count:   1
```

**Fallback chain:** configured per `task_type` in `ai_task_model_configs`:
```
task_type=chat → [provider_a, provider_b, provider_c]
```
On failure, gateway tries next provider in chain before returning an error.

**When all providers fail:** return `503` with `fallback_triggered: true` and use the `fallback_behavior` defined in the tool registry.

### 5.3 Streaming (SSE)

AI chat responses are streamed as Server-Sent Events (SSE).

> **Reconciled (2026-07-02):** the contract below (event names `chunk` /
> `tool_confirmation_required` / bare `done` and `error` payloads) was never
> implemented and never adopted by the frontend — it was aspirational only.
> `docs/API_CONTRACTS.md` §"SSE Contract" now documents the real, shipped
> contract as authoritative (confirmed against both
> `ai_assistant.application.chat_service.stream_message` and
> `frontend/src/components/ai-assistant/ai-chat-window.tsx`, which already
> consume it in production). Summary: a single generic SSE `message` per
> line, dispatched by `data.type` — `status`, `tool_call`, `tool_result`,
> `token` (`{"text": "..."}`, word-level, no `index`), `done`
> (`{"message": {...full chat message, incl. `requires_confirmation`...}}`),
> `error` (`{"code": "..."}`). There is no distinct
> `tool_confirmation_required` event type — see `docs/API_CONTRACTS.md` for
> the full example payloads. The illustrative shape immediately below is
> kept only as a historical record of the original design; do not build
> against it.

```
GET /api/v1/ai/sessions/{session_id}/stream
Content-Type: text/event-stream

event: chunk
data: {"token": "Xin ", "index": 0}

event: chunk
data: {"token": "chào!", "index": 1}

event: tool_confirmation_required
data: {"confirmation_id": "...", "tool_name": "...", "display_summary": {...}}

event: done
data: {"message_id": "msg_xyz", "total_tokens": 142}

event: error
data: {"code": "provider_unavailable", "user_message": "Hiện tại không thể xử lý, vui lòng thử lại."}
```

**Rules:**
- Never expose `model`, `provider`, `latency_ms`, or `token_count` in stream events.
- `event: error` uses only user-safe `user_message`; raw error detail goes to server logs only.
- Clients must handle reconnect (exponential backoff, cap at 30s).
- Stream must be cancelled cleanly if client disconnects (backend holds no orphan goroutine/task).

### 5.4 Usage, Cost, And Billable AI Accounting

The shipped implementation deliberately separates three ledgers:

1. **`ai_usage_log`** — PII-safe AI call log used by user-facing request meters
   and legacy daily/weekly quota checks. It stores task type, internal model
   alias, success, character buckets, optional `user_id`/`session_id`, optional
   estimated `cost_usd`, and timestamp. It does **not** store provider name,
   concrete model id, raw token counts, latency, prompt text, response text, raw
   file paths, or PII.
2. **`ai_ops_event` + `ai_usage_daily`** — platform-superadmin operational
   telemetry and rollups for provider cost/reliability dashboards. This may
   include provider/model identity, token counts, latency, status, org/user
   references, and cost, but never prompt/response text, keys, or base URLs.
   Provider/model identity is visible only to platform superadmins inside
   superadmin-only operations/settings surfaces.
3. **Billable AI usage ledger (required next step)** — a product entitlement
   ledger for student credits, partner package AI credits, university/internal
   department budgets, idempotency, and "what feature consumed quota" reporting.
   See `docs/PRODUCT_OPERATING_MODEL.md` §3.

The billable ledger is required because `ai_usage_log` is intentionally too
coarse for plan/package accounting, and `ai_ops_event` is intentionally admin
only. Do not use either table alone as the final source for student/partner
credits.

Minimum billable ledger fields:

```text
actor_user_id
actor_persona
org_id
billing_scope: user | org | department | platform
feature_key
task_type
resource_type/resource_id
session_id
idempotency_key
units_charged
provider_cost_usd
result_status
ai_usage_log_id / ai_ops_event_id
created_at
```

**Current implementation caveat (2026-07-08):** calls routed through
`AiTaskRunner` write DB usage/ops records. Some helper paths that call
`generate_json_note`, `get_provider`, `get_provider_for_alias`, embedding,
translation, or semantic-scoring helpers may only call the sync logger
`log_ai_usage()` and therefore may not create the durable DB rows that
user/org quota reads. Treat this as a P0 accounting gap before enabling paid AI
credits or package-based AI limits.

**Charging rule:** user/partner credits are charged only after a successful,
user-visible AI output or a configured billable background result. Deterministic
scoring/parsing, local OCR, validation failures before a model call, cache hits,
and provider failures that produce no useful output do not consume credits.
Provider cost can still be counted internally when a model call consumed tokens.

### 5.5 Provider/Model Identity And Registry Governance

Product owner decision (2026-07-08): the older ADR-0011.1 idea of a grantable
`ai_settings:view_provider_identity` permission for university staff is
superseded. Raw provider/model identity is **platform-superadmin-only**.

**Default for all non-superadmin surfaces:** AI settings, routing, usage, quota,
assistant, CV/JD, partner, student, and university staff screens show only safe
operational fields: feature status, alias/slot handles, budget/limit state,
health state, fallback/unavailable state, and user-safe labels. They do not show
raw `provider_internal`, concrete `model_id`, base URL, token counts, latency,
prompt text, or provider pricing.

**Superadmin-only:** platform superadmins may view, create, update, delete,
enable/disable, price, and health-check provider/model registry entries and
fallback chains inside superadmin AI operations/settings surfaces. These actions
are audited. Ordinary university staff may request changes or operate masked
rollout/budget controls only if product scope grants that ability; they do not
see or edit the real provider/model registry.

**Still absolute, no exception at any level:**

- Raw API key: never returned by any API. Lives in `backend/.env` only.
- Base URL: never returned by any API.
- Prompt text, response text, raw confidence, user PII, internal status codes,
  and API keys are never stored in or returned from provider/model registry APIs.
- Partner/employer, student, guest, and ordinary university-staff surfaces must
  never include `provider_internal`, `model_id`, concrete model names, provider
  names, pricing rows, or routing-chain internals.

**Audit:** every superadmin read of raw provider/model identity writes
`audit_logs` with `action = "ai_settings.provider_identity_viewed"`. Every
provider/model create/update/delete/price/key-rotation/kill-switch/fallback-chain
change writes a before/after audit event.

### 5.6 Platform Superadmin AI Operations Console (owner decision 2026-07-07)

Product owner override extending §5.4/§5.5 for the **Platform Admin Console**
(superadmin-only control plane; see
`docs/superpowers/specs/2026-07-07-platform-admin-console-design.md`).

**What changes:** the earlier "token counts, latency … never exposed anywhere"
wording (§5.5) is narrowed to "never exposed to end users, partners, students,
or ordinary university staff."
A **platform superadmin** operating the AI Operations console MAY view
**aggregated** operational telemetry — cost, request/error/fallback counts,
token totals, latency percentiles, and circuit-breaker state — for spend,
reliability, and volume dashboards. Concrete provider/model identity in that
console is superadmin-only, exactly as §5.5.

**Storage:** implemented via a **separate admin-only `ai_ops_event` table** plus
a `ai_usage_daily` rollup and an admin-editable `ai_model_price` table. The
existing `ai_usage_log` remains the PII-safe cost aggregate and is unchanged.
`ai_ops_event` realizes the server-side telemetry §5.4 originally specified
(`provider_internal`, tokens, latency, error_code) that the initial
implementation had reduced to buckets.

**Langfuse:** the superadmin-operated Langfuse project MAY receive per-call
metadata including provider/model identity, tokens, latency, and status for
trace/debug/eval.

**Still absolute (no exception at any level):** API keys, base URLs, and **raw
prompt/response/chunk text** are never stored in `ai_ops_event`, never sent to
Langfuse, and never returned by any API. End-user and org-scoped-admin surfaces
are unaffected — provider/model/token/latency/prompt remain fully hidden there.
Every provider-identity read and every price/budget/kill-switch change is
audited (§5.5 audit rules apply).

### 5.7 Billable AI Task Policy

Use `docs/PRODUCT_OPERATING_MODEL.md` §3 as the canonical product policy. The
summary below is binding for implementation:

- **Student:** chat turns, CV AI suggestions, cover letters, interview
  simulation feedback, learning-gap plans, and AI-backed CV/JD explanations may
  consume student credits. Deterministic CV-JD fit scores remain free; only AI
  explanation/improvement text consumes credit, once per `(cv_version,
  job_version)` cache key.
- **Partner:** JD extraction consumes org AI credits only when native/local
  extraction escalates to AI and returns a useful prefill. JD writer, screening
  brief, scorecard suggestion, outreach/ad creative generation, and semantic
  candidate narratives consume partner org/package credits.
- **University:** moderation, fraud, market intelligence, provider probes,
  workflow AI nodes, and internal reports are charged to platform, department,
  org, or user budgets controlled by university admins. They never show a
  student/partner-style upgrade CTA.
- **System/background:** embeddings, rerank, scheduled summaries, and workforce
  subtasks must be attributed to platform/org/department budgets unless a
  specific user action triggered a billable feature.

Implementation requirement: every real provider call that can affect credits,
quota, billing, package limits, or university budget must accept a usage context
(`principal`, `org_id`, `feature_key`, `resource`, `session_id`,
`billing_scope`) and write the durable billable ledger with an idempotency key.
If a helper cannot receive that context, it is not the final production path for
a billable feature.

---

## 6. RAG Pipeline

### 6.1 Chunking Strategies

Two chunking modes, selected per document type:

**Mode A — Paragraph-aware sliding window (default):**
```
target_size:    512 tokens
overlap:        64 tokens
split_boundary: paragraph break > sentence break > word break
max_chunks:     500 per document
```

**Mode B — Semantic chunking (opt-in, for long structured docs):**
```
Embed each paragraph → compute cosine similarity between adjacent paragraphs
Split when similarity < threshold (0.65)
Merge fragments shorter than 128 tokens with neighbor
```

**Choice rule:** use Mode B for documents > 50 pages or documents with clear section headings (detected by heading-pattern regex). Stored in `knowledge_base_documents.chunking_mode`.

**Implementation:** `backend/app/ai/retrieval/chunking.py`

### 6.2 Hybrid Search

Retrieval uses a two-stage hybrid: dense vector search + sparse BM25, combined via Reciprocal Rank Fusion (RRF).

```
Query → [Dense path]  pgvector cosine similarity → top-K dense candidates
      → [Sparse path] PostgreSQL ts_rank (BM25-like) → top-K sparse candidates
      → RRF fusion:   score = Σ 1/(rank_i + 60)
      → top-N merged candidates → reranker
```

**Dense search:**
```sql
SELECT chunk_id, content, section_heading, document_id,
       1 - (embedding <=> $1::vector) AS dense_score
FROM knowledge_base_chunks
WHERE kb_id = ANY($2)   -- scope filter — mandatory
  AND is_deleted = FALSE
ORDER BY embedding <=> $1::vector
LIMIT 20;
```

**Sparse search:**
```sql
SELECT chunk_id, content, section_heading, document_id,
       ts_rank(tsv_content, plainto_tsquery('simple', $1)) AS sparse_score
FROM knowledge_base_chunks
WHERE kb_id = ANY($2)
  AND is_deleted = FALSE
  AND tsv_content @@ plainto_tsquery('simple', $1)
LIMIT 20;
```

**RRF fusion** then takes the top 10 merged candidates into the reranker.

**Schema additions:**
```sql
ALTER TABLE knowledge_base_chunks ADD COLUMN tsv_content TSVECTOR
  GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED;
CREATE INDEX idx_kb_chunks_tsv ON knowledge_base_chunks USING GIN(tsv_content);
```

### 6.3 Reranking

After hybrid retrieval, a cross-encoder reranker re-scores each candidate against the query:

```
Input:  [(query, chunk_1), (query, chunk_2), ..., (query, chunk_10)]
Model:  cross-encoder (deployed locally or via gateway embedding endpoint)
Output: relevance_score per pair
Filter: keep only chunks with relevance_score >= 0.60
Sort:   descending by relevance_score
Cap:    top 5 chunks → pass to context assembly
```

**Reranker options (in priority order):**
1. Cross-encoder via AI gateway (provider-agnostic, uses embedding-style endpoint).
2. Lightweight local reranker for offline/CI/free-tier use.
3. Score-pass-through (no reranking) — absolute last resort if tier 2 itself errors.

**Implementation status (2026-07-01):**
- `backend/app/ai/retrieval/rerank.py` — tier 1, LLM-as-listwise-reranker via
  the gateway (`rerank_jobs`), used for job search when a real provider is
  configured.
- `backend/app/ai/retrieval/local_reranker.py` — tier 2, **now implemented**:
  a pure-Python, zero-dependency BM25-lite lexical reranker (`local_rerank`).
  This is what actually runs for every free/offline rerank today — `rerank_jobs`
  falls back to it (instead of a naive pass-through) whenever no real provider
  is active or the LLM call fails, and `rerank_kb_chunks` uses it as the
  *only* tier for KB chunks (an LLM call to rerank ~10-20 short chunks per
  query would spend real tokens for a step that doesn't need semantic
  reasoning — hybrid dense+BM25 retrieval already did that). Wired into
  `knowledge_base.kb_service.search_chunks` so KB retrieval now has a real
  reranking step (previously: none at all).
- A true transformer cross-encoder (e.g. BGE-reranker-v2-m3 via Ollama) is
  NOT implemented — it would add a multi-GB model dependency
  (`sentence-transformers`/`torch`), which conflicts with this project's
  lightweight-by-default local stack (`docs/LOCAL_DEV_STACK.md`). Add it only
  behind an ADR and an opt-in flag if job-search/KB volume or quality
  genuinely needs it; the lexical tier above is what ships today.

### 6.4 Context Assembly

Top reranked chunks are assembled into the prompt context:

```
MAX_RAG_CONTEXT_TOKENS = 3000

For each chunk (sorted by relevance score, highest first):
  - Add chunk if running_total + chunk.token_count <= MAX_RAG_CONTEXT_TOKENS
  - Stop when budget exhausted

Format:
  [DOC: {document_name} | Phần: {section_heading or "—"}]
  {content}
  ---

If no chunks pass threshold (score >= 0.60):
  → no context injected
  → LLM instructed to say "Tôi không tìm thấy thông tin phù hợp trong tài liệu."
  → NEVER generate an answer from model knowledge
```

### 6.5 Citation Verification (Post-generation)

After the LLM generates an answer, a lightweight post-processing step verifies citations:

1. Extract all `Theo <Doc>` / `According to <Doc>` citation markers from the answer.
2. Check each cited document name exists in the `sources` list returned by retrieval.
3. If a citation references a document NOT in the retrieved set → flag as `hallucination_risk`, log, and strip that citation.
4. Metric: `citation_grounded_rate = verified_citations / total_citations` tracked per KB scope.

**Implementation status (2026-07-01): IMPLEMENTED.**
`backend/app/ai/retrieval/citation_verify.py` — pure, deterministic,
offline (`verify_citations(answer, sources) -> CitationCheckResult`). An
ungrounded citation's document name is replaced with a safe generic phrase
("tài liệu được cung cấp") rather than being echoed back, so a fabricated
source name never reaches the user. Wired into
`ai_assistant.application.chat_service` (`send_message` and `stream_message`)
— whenever a turn calls the `knowledge_base_query` tool, the retrieved
document titles are tracked and the final assistant reply is run through
`verify_citations` before being persisted/streamed. Only logs metadata
(`cited_count`, `grounded_count`, `hallucination_risk`) — never the raw
answer or citation text (§15). Covered by
`tests/unit/test_citation_verify.py` (12 unit tests) and the
`knowledge_base_query` offline eval family (5 categories, 33 cases).

---

## 7. Tool Registry Contract

Every registered tool must define all of the following fields:

```yaml
name:                 string       # snake_case, globally unique
description:          string       # used in LLM tool description — must be task-specific, not generic
permission_class:     read_only | confirmation_required | restricted_admin | human_review
persona:              list[string] # which user types can invoke this tool
required_permissions: list[string] # RBAC permissions checked before execution
input_schema:         object       # JSON Schema for tool inputs
output_schema:        object       # JSON Schema for tool outputs
side_effects:         list | none  # DB writes, notifications, etc.
confirmation_copy:    object | null
  title:              string       # Vietnamese, user-facing
  body:               string       # brief plain-text summary of what will happen
  cta_confirm:        string       # e.g. "Xác nhận nộp đơn"
  cta_cancel:         string       # e.g. "Huỷ"
audit_event_type:     string       # e.g. "TOOL_APPLY_JOB", written to audit_logs
fallback_behavior:    string       # what to do when tool fails or AI is down
max_retries:          int          # default 0 for user-facing, 3 for internal system tools
timeout_seconds:      int          # default 15
```

**Tool registration:** tools are registered in `backend/app/ai/gateway/tool_registry.py`. Not in any per-module file to prevent registration drift.

> **Implementation status (2026-07-01):** the actual registry lives at
> `backend/app/modules/ai_assistant/application/tools/specs.py` (`tool_registry.py`
> re-exports it for backward compatibility) and, as of this note, declares the
> full §7 field set (`persona`, `required_permissions`, `output_schema`,
> `side_effects`, `confirmation_copy`, `audit_event_type`, `max_retries`,
> `timeout_seconds`) with a `__post_init__` invariant enforced by
> `tests/unit/test_ai_governance.py` — a `confirmation_required` tool cannot be
> registered without `confirmation_copy` + `side_effects`, and no tool can be
> registered without `audit_event_type`. Only two permission classes are used
> in this registry today: `read_only` and `confirmation_required`.
> `restricted_admin` and `human_review` tasks (moderation, fraud detection,
> market intelligence) are **not** `ai_assistant` chat tools — they are
> admin-only services invoked directly by university-staff-facing endpoints,
> outside the ReAct tool-calling loop. If a future chat tool needs one of
> those two classes, extend `ToolSpec.permission_class` and the dispatch gate
> in `chat_service.py` (currently it only branches on
> `confirmation_required` vs. everything-else) rather than silently reusing
> `read_only`.

**Tool description quality:** descriptions must be specific enough that the LLM chooses the right tool. Generic descriptions like "performs an action" are rejected in ai-engineer review.

---

## 7.1 CV Studio AI Protocol

CV Studio AI tools operate on structured CV data, never directly on a PDF binary.

Allowed sources:

- confirmed student profile fields,
- reviewed uploaded CV extraction,
- existing builder CV/version owned by the student,
- raw notes typed by the student,
- target job/JD for tailoring.

Output contract:

- AI returns a structured diff or draft, not a direct database mutation.
- The diff must list affected sections, before/after text, source evidence, and `requires_fact_confirmation`.
- Accepting a diff creates a new `cv_versions` row and audit event.
- Rejecting a diff preserves the current CV unchanged.
- AI cannot invent education, employer, award, GPA, certification, employment dates, or quantified outcomes.

`fill_cv_template_from_sources` is used when a student selects a template and asks AI to fill it from available sources. It may reorganize wording and section order, but it must preserve source truth and mark any unverifiable claim as needing confirmation.

High-risk fabrication signals write to `human_review_queue` only when university policy requires review; normal student-facing warnings are advisory.

---

## 8. Prompt Management

### 8.1 Version Format

Prompt templates live in `backend/app/ai/prompts/{task_name}/v{N}.py`:

```python
# backend/app/ai/prompts/chat/v3.py
# Version: 3 | Date: 2026-06-26 | Author: ai-engineer
# Change: added KB citation instruction block
# Previous: v2 — generic assistant without RAG

SYSTEM_PROMPT = """
{static_identity_block}

{static_rules_block}

{kb_citation_instruction}  # only if KB context will be injected
"""
```

**Rules:**
- Version numbers are monotonically increasing integers.
- Old versions are never deleted until the new version passes full eval gate.
- Active version per task is stored in `ai_task_model_configs.prompt_version`.
- Changes require ai-engineer review and updated eval dataset before deploy.
- Prompt templates must be authored in English even when the default product
  locale is Vietnamese. Localized UI copy, email copy, and final AI answers are
  separate output concerns and must be driven by `target_language`/locale inputs.
- Do not hardcode Vietnamese task instructions inside backend prompt templates
  unless the task is explicitly a Vietnamese-language fixture or example.

### 8.2 Caching Strategy (Provider-Side)

Provider-side prompt caching (supported by Anthropic, OpenAI) works on the static prefix. Structure messages to maximize cache hits:

```
Position 1 (STATIC — cache-eligible):
  system prompt (identity + rules + citation instructions)

Position 2 (SEMI-STATIC — cache-eligible if same user):
  user profile summary (changes rarely)

Position 3 (DYNAMIC — not cached):
  retrieved KB chunks (changes per query)

Position 4 (DYNAMIC — not cached):
  conversation history (trimmed to budget)

Position 5 (DYNAMIC — not cached):
  current user message
```

**Never** put the user's query or current turn data before the static system prompt.

### 8.3 A/B Prompt Testing

For prompt improvements, use `ai_task_model_configs.prompt_ab_config`:

```json
{
  "active": true,
  "variants": [
    { "version": 3, "traffic_pct": 80 },
    { "version": 4, "traffic_pct": 20 }
  ],
  "metric": "citation_grounded_rate",
  "min_samples": 100,
  "auto_graduate": false
}
```

The gateway samples a variant on each request, logs `prompt_version` to `ai_usage_log`, and the eval harness aggregates metrics per variant. No auto-graduation without ai-engineer approval.

---

## 9. Safety and Guardrails

### 9.1 Input Guards (PreGeneration)

All user messages pass through `backend/app/ai/safety/input_guard.py` before reaching the LLM:

| Check | Action on Trigger |
|---|---|
| Prompt injection patterns (`ignore previous instructions`, `[SYSTEM]`, `<INST>` etc.) | Reject with `400 UNSAFE_INPUT`; log with sanitized message |
| PII patterns in query (CCCD/passport numbers, phone numbers, full credit card numbers) | Strip PII from query before sending to LLM; add `[PII_REDACTED]` marker; log |
| Message length > `MAX_USER_MESSAGE_TOKENS` (default 2000) | Reject with `400 MESSAGE_TOO_LONG` |
| Detected language not in `[vi, en]` | Pass through (no block), but log for monitoring |
| Rate limit exceeded (configurable per tier) | Reject with `429 RATE_LIMIT_EXCEEDED` |

**Rate limits:**
- Student tier: 30 AI requests / hour / user
- Partner tier: 60 AI requests / hour / user
- University staff: 100 AI requests / hour / user
- System (Celery workers): no limit

### 9.2 Output Guards (PostGeneration)

All LLM responses pass through `backend/app/ai/safety/output_guard.py` before delivery:

| Check | Action on Trigger |
|---|---|
| Provider name leak (`OpenAI`, `GPT`, `Gemini`, `Anthropic`, `Claude`, `Llama` etc.) | Redact + log `PROVIDER_LEAKAGE_DETECTED`; alert ai-engineer |
| API key pattern in output | Hard block; log CRITICAL; alert immediately |
| Model name leak (model identifier patterns) | Redact + log |
| Internal status code leak (`QUEUED`, `FAILED`, `RUNNING` raw in answer) | Redact to user-friendly phrasing |
| Policy violation (hate speech, explicit content) via content classifier | Block; log; alert University Admin |
| Answer starts with "I don't have access to that" but tool result was injected | Flag as `context_confusion`; log for eval |

**Redaction rule:** replace detected patterns with `[unavailable]`. Never acknowledge to the user that redaction occurred.

### 9.3 Human Escalation Triggers

The agent loop automatically escalates to human review when:

- A tool call attempts a `human_review` permission class action.
- The fraud detection tool returns `risk_score >= 0.85`.
- The content moderation tool returns `policy_violation = true`.
- The agent loop hits `MAX_ITERATIONS` without completing the task (log `LOOP_EXHAUSTED`).
- Output guard blocks a response 3 times in a row for the same session (log `REPEATED_OUTPUT_BLOCK`).

Escalation writes to `human_review_queue` table and notifies the appropriate University Admin role via the notification system.

---

## 10. Evaluation Harness

### 10.1 Offline Evaluation (CI Gate)

Before any AI feature ships, it must pass an offline eval run:

```
backend/app/ai/evaluation/
  datasets/
    {task_name}/
      happy_path.jsonl       # ≥10 examples: {input, expected_output, eval_criteria}
      adversarial.jsonl      # ≥5 examples: prompt injection, jailbreak attempts
      privacy_boundary.jsonl # ≥5 examples: cross-user, cross-tenant leakage attempts
      low_quality_input.jsonl # ≥5 examples: missing data, malformed input
      fallback.jsonl         # ≥3 examples: provider down, no result cases
  run_eval.py                # CLI: python run_eval.py --task=cv_extraction --model=eval
```

**CI gate:** `run_eval.py` is called in the CI pipeline for every AI-touching PR. PR blocks if:
- Any privacy boundary test passes (data leakage = block immediately).
- Any adversarial test reveals provider name, API key, or prompt text.
- Happy-path pass rate < 80%.

> **Coverage status (2026-07-01, updated):** `run_eval.py` currently covers
> **18 task families** with full 5-category datasets, wired into
> `run_eval.py`'s `TASK_FAMILIES` via the `app.ai.evaluation.runners` package
> (one module per family — see `backend/app/ai/evaluation/EVAL_NOTES.md` for
> the full list and what each covers): `cv_ai_suggestions`,
> `recommend_cv_for_job`, `interview_sim`, `ai_assistant_chat`,
> `jd_generation`, `jd_extraction`, `jd_translation`, `knowledge_base_query`,
> `bias_detection`, `cover_letter`, `scorecard_suggest`, `screening_brief`,
> `interview_prep`, `answer_feedback`, `skill_suggest`, `career_snapshot`,
> `profile_summary`, `competition_signal_explanation`. Every real,
> code-backed AI task in the platform now has offline eval coverage.
>
> Building out this coverage found and fixed several real production bugs
> along the way (not just added tests) — see `docs/IMPLEMENTATION_STATUS.md`
> BATCH AI-POWER-UP2/3 for the full list, including one critical one:
> `profile_service.get_ai_summary_draft` called a non-existent
> `user_service.get_user_by_id` (the real function is `get_by_id`) — this
> endpoint crashed on **every single call** in production, unconditionally,
> outside the AI-fallback try/except entirely. Found only because building
> the eval required mocking the exact function the code called.
>
> Remaining gap in the §3 AI Task Matrix — **not implemented at all, no
> dataset possible yet:** `content_moderation` and `fraud_detection`
> (`human_review`) and `market_intelligence` (`restricted_admin`) have **zero
> backend code** (no service, no prompt file, no route) as of this note.
> Writing an eval dataset for these would test nothing real. Do not add a
> dataset for these until the feature itself is built and approved via
> `product-owner-system-planner` (scope) and `system-architect`
> (human-review-queue integration, §9.3) — building the eval before the
> feature would be eval-theater, not real coverage. `bias_detection` is the
> reference pattern to follow (deterministic rule-based module in
> `app.ai.safety`, advisory-only, no LLM call) for whichever of the
> remaining three is prioritized next.
>
> See `docs/IMPLEMENTATION_STATUS.md` for the burst batches that close each
> family.

### 10.2 Online Monitoring (Production)

1% of production AI responses are sampled and stored in `ai_eval_samples` for async review:

```sql
CREATE TABLE ai_eval_samples (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  task_type VARCHAR NOT NULL,
  session_id UUID NOT NULL,
  message_id UUID NOT NULL,
  input_summary TEXT,           -- query length and type only, no raw PII
  output_summary TEXT,          -- answer length and citation count only
  model_alias VARCHAR NOT NULL,
  prompt_version INT NOT NULL,
  guard_flags JSONB,            -- any output guard triggers
  human_score SMALLINT,         -- 1-5, filled by reviewer
  reviewed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
```

University Admin (AI Operations role) reviews sampled responses weekly.

### 10.3 LLM-as-Judge

For tasks where human scoring is expensive (e.g., CV quality analysis, JD bias detection), use an LLM judge:

```python
# backend/app/ai/evaluation/judge.py
async def judge_response(
    task_type: str,
    input_context: dict,
    model_response: str,
    rubric: str,
) -> JudgeResult:
    """
    Calls a separate judge model (always uses 'eval_judge' alias, separate from production provider).
    Returns: { score: 1-5, reasoning: str, flags: list[str] }
    """
```

**Judge rubric per task:**
- `cv_extraction`: factual accuracy vs. ground truth CV.
- `fill_cv_template_from_sources`: source faithfulness, section completeness, no invented claims.
- `generate_cv_bullets`: action-impact clarity, factual grounding, no unsupported quantified outcomes.
- `rewrite_cv_section`: preserves original meaning while improving clarity/tone.
- `optimize_cv_for_job`: tailoring relevance, source faithfulness, JD keyword grounding.
- `search_jobs`: semantic relevance of top-5 results.
- `knowledge_base_query`: citation grounded + no hallucination.
- `bias_detection`: precision/recall vs. human-labeled bias phrases.

**Judge model isolation:** the judge model MUST be a different alias from the production model to prevent self-evaluation bias.

> **Implementation status (2026-07-02):** `backend/app/ai/evaluation/judge.py`
> is implemented — verdict parsing with 1-5 clamping, per-task rubrics,
> `eval_model_alias` isolation (tested), output-guard scrubbing, and
> `JudgeParseError` on unparseable verdicts (never a fabricated score).
> It is NOT part of the offline CI gate (by design); real judge runs are
> opt-in under `AI_REAL_CALLS_ENABLED=true` with a cheap eval alias (§18).

### 10.4 Metrics and SLOs

| Metric | Target | Alert Threshold | Measured By |
|---|---|---|---|
| Happy-path pass rate | ≥ 90% | < 80% | Offline eval per release |
| Provider leakage rate | 0% | Any detection | Output guard + online monitoring |
| Hallucination rate (RAG) | 0% | Any confirmed | Citation verification + human review |
| Citation grounded rate (RAG) | ≥ 90% | < 80% | Automated citation verification |
| Confirmation cancellation rate | Monitor | > 40% (UX signal) | ai_usage_log |
| Human override rate | Monitor | > 30% (accuracy signal) | human_review_queue |
| Tool call success rate | ≥ 99% | < 95% | ai_usage_log |
| P95 first-token latency | ≤ 3s | > 5s | ai_usage_log.latency_ms |
| P95 total response latency | ≤ 15s | > 30s | ai_usage_log.latency_ms |

---

## 11. Observability

### 11.1 Trace Structure

> **Implementation status (2026-07-01): PARTIAL.** There is no `ai_traces`
> span table today. `backend/app/ai/observability/usage.py` writes one flat
> row per gateway call to `ai_usage_log` (`task_type`, `model_alias`,
> `success`, bucketed prompt/completion char-length, optional `cost_usd`,
> `user_id`, `session_id`) — no per-span breakdown of guard/RAG/tool timings.
> `ai_eval_samples` (§10.2) covers sampled review, separately. If a task needs
> real span-level debugging (e.g. diagnosing slow RAG stages), add a real
> `ai_traces` table and span emitters rather than assuming one already exists;
> until then, treat the span tree below as the **target design**, not current
> behavior.

Each AI request generates a trace with spans:

```
[trace] session_turn
  ├── [span] input_guard           (check_ms)
  ├── [span] context_injection     (token_count, sources_count)
  ├── [span] rag_retrieval         (if applicable)
  │     ├── [span] dense_search    (candidates_count, top_score)
  │     ├── [span] sparse_search   (candidates_count)
  │     ├── [span] rrf_fusion      (merged_count)
  │     └── [span] reranking       (final_count, reranker_skipped)
  ├── [span] gateway_call          (model_alias, iteration=N)
  │     ├── [span] provider_call   (latency_ms, input_tokens, output_tokens)
  │     └── [span] tool_execution  (tool_name, success)
  ├── [span] output_guard          (flags_triggered)
  └── [span] stream_delivery       (total_tokens_streamed)
```

**What is never logged in traces:** raw prompt text, raw chunk content, user PII, provider name, model name, API keys.

**What is always logged:** span durations, token counts, alias names, success/failure, flag types (not flag content).

**Trace storage:** `ai_traces` table, TTL 30 days (configurable per university data policy).

### 11.2 Cost Attribution

Monthly cost report per `(tenant_id, task_type, model_alias)` from
`ai_usage_log`. Ordinary university views are masked to aliases/status/budget
only; provider/model-level drilldowns belong to the superadmin AI Operations
console.

University Admin sets monthly token budgets per tier. Gateway checks budget before each request and rejects with `402 BUDGET_EXCEEDED` when limit is hit.

### 11.3 Alerts

| Condition | Severity | Notify |
|---|---|---|
| Provider leakage detected in output | CRITICAL | ai-engineer on-call |
| API key pattern in LLM output | CRITICAL | ai-engineer + Security |
| All providers in fallback chain fail | HIGH | University Admin + ai-engineer |
| Circuit breaker OPEN on primary provider | MEDIUM | ai-engineer |
| Token budget > 80% for a tenant | LOW | University Admin |
| Token budget 100% (requests blocked) | HIGH | University Admin |
| Hallucination confirmed by human reviewer | HIGH | ai-engineer |
| `LOOP_EXHAUSTED` rate > 5% over 1h | MEDIUM | ai-engineer |

---

## 12. Context Window Management

### 12.1 Token Budgets Per Feature

| Feature | System Prompt | User Profile | RAG Chunks | History | User Message | Max Output |
|---|---|---|---|---|---|---|
| AI assistant chat | 800 | 300 | 3000 | 2000 | 2000 | 1500 |
| Interview simulator | 1200 | 400 | 0 | 3000 | 500 | 2000 |
| CV extraction | 600 | 0 | 0 | 0 | (CV text) | 2000 |
| CV Studio fill/rewrite | 900 | 500 | 0 | 500 | selected CV/source notes | 1800 |
| KB query | 500 | 200 | 3000 | 500 | 500 | 1000 |

All totals capped at model context limit (default 128k). Token budgets are enforced before the gateway call; if history exceeds budget, it is trimmed from oldest-first.

### 12.2 History Trimming Strategy

```
1. Always keep: system prompt + user profile + RAG chunks + current user message.
2. History budget = model_context_limit - sum(above reserved tokens) - max_output_tokens.
3. Fill from most-recent message backwards until history budget exhausted.
4. If even the previous single turn exceeds budget:
     - Summarize the oldest 50% of history using a short summarization LLM call.
     - Replace with summary message: role=assistant, content="[Tóm tắt cuộc hội thoại: ...]"
     - Cache the summary in ai_sessions.history_summary.
```

### 12.3 Session Lifecycle

- **Active:** last_active_at within 4 hours — keep in warm state.
- **Idle:** last_active_at 4–24 hours — history summary computed lazily on next access.
- **Archived:** user manually archives, or 90 days of inactivity — session data retained for audit but not loaded in context.
- **Deleted:** never; sessions are soft-deleted only (audit requirement).

---

## 13. Document Knowledge Base — Tool Specs

### `knowledge_base_query`

```yaml
name: knowledge_base_query
description: >
  Retrieve relevant information from permitted knowledge base documents
  to answer the user's question. Automatically determines which knowledge
  bases to search based on conversation context (platform, partner, per-job).
  Always cite the source document name and section in the answer.
permission_class: read_only
persona: [student, partner_user, university_staff]
required_permissions: [authenticated, kb_scope_resolved]
input_schema:
  query: string
  context:
    org_id: UUID | null
    job_id: UUID | null
output_schema:
  answer: string
  sources:
    - document_name: string
      section_heading: string | null
      similarity_score: float   # NEVER in API response — internal only
  kb_ids_searched: list[UUID]   # audit log only
side_effects: none
confirmation_copy: null
audit_event_type: KB_QUERY
fallback_behavior: >
  AI down → static message directing user to contact org directly.
  No result (all scores < 0.60) → "Tôi không tìm thấy thông tin phù hợp trong tài liệu được chia sẻ."
max_retries: 1
timeout_seconds: 20
```

### `knowledge_base_ingest` (internal, Celery only)

```yaml
name: knowledge_base_ingest
description: >
  Embed a document chunk and store in pgvector. Internal Celery worker only.
  Not exposed as a user-facing tool.
permission_class: restricted_admin
persona: [system]
required_permissions: [system_internal]
input_schema:
  document_id: UUID
  chunk_index: int
  content: string
  section_heading: string | null
  token_count: int
output_schema:
  chunk_id: UUID
  embedding_dim: int
side_effects:
  - INSERT knowledge_base_chunks
  - UPDATE knowledge_base_documents.chunk_count
audit_event_type: KB_CHUNK_EMBEDDED
fallback_behavior: retry 3× exponential backoff, then mark document FAILED
max_retries: 3
timeout_seconds: 30
```

---

## 14. Prompt Requirements

### Chat / KB-Augmented Answer Structure

```
[POSITION 1 — STATIC, cache-eligible]
System identity + tone + behavioral rules

[POSITION 2 — STATIC, cache-eligible if same user]
User profile summary (name, role, current applications)

[POSITION 3 — DYNAMIC, not cached]
Retrieved KB chunks (if RAG path):
  [DOC: {document_name} | Phần: {section_heading}]
  {content}
  ---

[POSITION 4 — DYNAMIC, not cached]
Conversation history (trimmed to budget)

[POSITION 5 — DYNAMIC, not cached]
Current user message
```

**Citation instruction (mandatory in KB system prompt):**
```
Bạn PHẢI trích dẫn tên tài liệu và phần tương ứng cho mỗi thông tin bạn cung cấp.
Định dạng: "Theo [Tên tài liệu] — [Phần X]: ..."
Nếu bạn không tìm thấy thông tin phù hợp trong tài liệu được cung cấp,
hãy nói rõ điều đó và KHÔNG tự suy đoán thêm.
```

**Never include in any prompt sent to provider:**
- Storage keys or file paths.
- Embedding model names or dimensions.
- Similarity scores or chunk IDs.
- Internal document IDs.
- AI provider names or API keys.

---

## 15. Privacy Rules (AI-Specific)

- AI usage logs must NOT contain raw prompt content if it includes user PII.
- Log only: `user_id`, `session_id`, `task_type`, `query_length`, `answer_length`, `token_count`, `model_alias`, `tool_name`.
- KB chunk content must NOT be logged anywhere (chunk IDs only).
- Partner KB chunks must NOT appear in Platform KB queries — scope filter is mandatory, not advisory.
- Per-job KB chunks must NOT be accessible after application status becomes REJECTED or WITHDRAWN.
- Cross-session data must never be mixed — session history is strictly user-scoped.

---

## 16. Rollout Defaults

1. Start disabled behind university feature flag per `ai_task_model_configs.enabled`.
2. Enable for university staff pilot first where applicable.
3. Enable for a small student/partner cohort (configurable % by University Admin).
4. Monitor: error rate, provider leakage events, confirmation cancellation rate, human override rate, cost/day.
5. Roll back immediately if: any provider leakage, any confirmed hallucination, unsafe automation detected, cost anomaly (> 3× baseline in 1 hour).

---

## 17. Rollback Criteria (Per Feature)

| Trigger | Action |
|---|---|
| Any confirmed provider leakage | Disable feature immediately, audit all recent responses |
| Any confirmed hallucination (RAG) | Disable KB for that scope, audit last 100 responses |
| Citation accuracy < 80% over 100 queries | Investigate chunking/reranking before re-enable |
| Unauthorized cross-tenant chunk access | Disable all RAG immediately, full audit |
| Provider embedding failure rate > 10% / 1h | Switch to fallback message mode |
| Confirmation cancellation rate > 40% | UX review before re-enable |
| Human override rate > 30% | Accuracy review before re-enable |
| `LOOP_EXHAUSTED` rate > 10% / 1h | Reduce MAX_ITERATIONS or fix tool resolution |
| Any API key pattern in LLM output | Disable feature + rotate keys immediately |

---

## 18. Provider, Cost, And Test-Key Policy

Real API keys are local-only secrets. They must never be written into docs, code, tests, prompts, migrations, fixtures, browser bundles, or tracked config.

### Local Env Names

```bash
OPENROUTER_API_KEY=replace-with-local-key
AI_DEFAULT_PROVIDER=openrouter
AI_DEFAULT_MODEL_ALIAS=chat_cheap
AI_EMBEDDING_MODEL_ALIAS=embedding_cheap
AI_EVAL_MODEL_ALIAS=eval_cheap
AI_REAL_CALLS_ENABLED=false
AI_MAX_REAL_CALLS_PER_TEST_RUN=3
```

### Default Local Test Policy

- Unit tests and CI use the offline/fake provider.
- Integration tests may use OpenRouter/DeepSeek-compatible low-cost aliases only when `AI_REAL_CALLS_ENABLED=true`.
- Do not run real model calls merely because a local key exists. Run them only
  after prompt/tool contracts and offline tests pass, and only when the current
  task explicitly asks for a real-provider smoke test.
- Cap real smoke tests to the smallest useful sample: usually 1 call for a
  single slice and never above `AI_MAX_REAL_CALLS_PER_TEST_RUN`.
- Log only task type, alias, success/failure, and approximate cost bucket. Do not log raw prompt, response containing PII, provider key, provider name, or model name.
- If a key is pasted into chat, logs, or output, rotate it and treat it as compromised.
- Real-call smoke reports must say which internal alias was used, not the
  concrete provider/model/API key.

### Alias Defaults

| Alias | Intended Use | Default Cost Posture |
|---|---|---|
| `chat_cheap` | Local manual smoke tests and non-critical drafts | Free/low-cost OpenRouter-compatible model |
| `reasoning_cheap` | Small planning/classification checks | Low-cost reasoning model |
| `embedding_cheap` | Local retrieval smoke tests | Low-cost embedding model |
| `eval_cheap` | Small judge/eval smoke tests | Low-cost judge model, separate from production alias |
| `offline` | Unit tests, CI, deterministic snapshots | No network calls |

---

## 19. Lightweight Multilingual Extraction Policy

> **UPDATE 2026-07-05 (owner decisions):** (1) The uploaded-CV flow is
> upload → confirm file → name the CV → done, with NO manual field-review step —
> backend extraction is authoritative and creates the versioned draft directly and
> must be accurate because it feeds CV-JD matching. (2) The cascade adds a cheap
> **vision-LLM** tier that MAY receive DOWNSCALED document images for images and
> styled/scanned PDFs; the text-LLM structuring tier still receives extracted text
> only. Non-CV/blank/corrupt uploads are rejected, never fabricated. Read the
> "present to user for review" and "text-only LLM" wording below as historical.

The system supports Vietnamese and English first. Other languages may pass through, but v1 quality gates focus on `vi` and `en`.

### CV And Document Extraction Flow

1. Detect file type.
2. Extract native text when possible:
   - PDF: PyMuPDF/PyMuPDF4LLM adapter when available, `pdfplumber` fallback
   - DOCX: `python-docx`
   - TXT: UTF-8
3. If native text is disordered, sparse, multi-column, or canvas/vector-heavy,
   run a layout-aware adapter (`pymupdf4llm` preferred local lightweight option;
   `docling` optional for broader document/OCR capability; `marker` only after
   an ADR because it is heavier).
4. If readable text is empty or low quality, render selected pages and run OCR
   with `vie+eng`.
4b. If native text + local OCR are still insufficient (images, styled/scanned
   PDFs), escalate to a cheap vision-LLM tier. (Updated 2026-07-05: this tier MAY
   receive DOWNSCALED document images; the text-LLM tier below still receives text
   only.)
5. Normalize Unicode, bullets, dates, phone/email/link patterns.
6. Run deterministic section classifier.
7. Optionally call the text-LLM to structure ambiguous fields using `chat_cheap`
   only after local extraction passes; it receives extracted text/markdown only.
8. Store the structured extraction directly as the versioned draft. (Updated
   2026-07-05: backend-authoritative — no manual user field-review step; import
   must never silently overwrite an already-accepted CV.)

Failure gates before LLM structuring:

- `UNSUPPORTED_FILE_TYPE`
- `FILE_REJECTED_SECURITY`
- `PASSWORD_PROTECTED_FILE`
- `CORRUPT_FILE`
- `BLANK_DOCUMENT`
- `LOW_QUALITY_SCAN`
- `NOT_A_CV`
- `INSUFFICIENT_CV_CONTENT`

For these gates, do not call the LLM by default. Return a safe failure state and deterministic next actions.

### Local Cost And Performance Limits

- CV extraction default max pages: 6.
- OCR default timeout: 25 seconds.
- Heavy OCR is disabled unless `PADDLE_OCR_ENABLED=true`.
- Text-LLM structuring never receives raw binary files. The vision-LLM tier MAY
  receive DOWNSCALED document images (owner decision 2026-07-05) for the
  image/styled/scanned-PDF path only; it never receives raw un-downscaled bytes.
- Low-confidence extraction is resolved backend-side into the best draft.
  (Updated 2026-07-05: `needs_review` is an internal quality marker, not a
  student field-review gate — backend-authoritative extraction feeds CV-JD
  matching.)
- Non-CV or blank documents are not treated as model failures; they are product validation outcomes with friendly recovery paths and are never fabricated into a CV.
