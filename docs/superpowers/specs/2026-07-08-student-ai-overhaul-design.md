# Student AI Overhaul — Design Spec

- Date: 2026-07-08
- Owner decision-maker: danielngo0302 (product owner)
- Status: Approved for detailed planning (design gate passed)
- Related memory: `student-ai-overhaul`, `cv-jd-matching-rebuild`, `platform-admin-console`, `cv-studio-rebuild`, `jd-ingestion-cascade`
- Source docs: `docs/AI_PRODUCT_SPEC.md`, `docs/PRODUCT_OPERATING_MODEL.md`, `docs/BUSINESS_LOGIC.md`, `docs/CV_INGESTION_EXTRACTION_SPEC.md`, `docs/DISCOVERY_RECOMMENDATION_ADS_SPEC.md`, `docs/SCREEN_SPECS.md`, `docs/SECURITY_PRIVACY.md`, `docs/EDGE_CASES_FAILURE_MODES.md`, `.claude/rules/ai.md`, `.claude/rules/backend.md`, `.claude/rules/frontend.md`

## 1. Goal

Make the **student end-to-end experience** (guest → logged-in) correct, metered, resilient, and world-class. Every value-affecting LLM call is metered against a masked "AI energy" budget; the job-detail page becomes an on-demand analysis surface; competition intelligence becomes quality-adjusted and grounded in real applicants; AI degrades safely when the model is off or erroring (offline where no AI is needed, clear user-safe errors where it is, never fabrication); the student assistant is a system-internal, chat-only agentic helper; the **guest/public** funnel gets progressive, privacy-safe personalization; **advertising** becomes campaign-grade and relevance-targeted without eroding trust; and the **frontend** is consolidated to one clean, consistent, low-noise system. Accuracy is non-negotiable — no fabricated CVs, scores, competition claims, or "recommended"/"AI" labels without a real backend signal.

## 2. Locked owner decisions (2026-07-08)

1. **Student-facing AI unit = "AI energy %"**, internally weighted by real provider cost (a vision CV extraction costs materially more than a one-line text edit). Tokens/USD/provider/model stay superadmin-only and are never shown to students.
2. **Allowance = tiered by subscription plan** (Free low, Premium higher) **+ a non-resetting top-up "wallet"** of purchased energy, consumed after the weekly allowance.
3. **Windows:** weekly = **hard block** (exhaustion → upgrade/top-up for students; university staff route to admin limit-request, not upsell). 3h rolling = **soft warning only** (burst protection). **Daily removed entirely** — both the request-count daily window and the student USD-daily budget.
4. **Full package:** implement all student workstreams below, phased. Test AI paths economically — offline/fake provider for the bulk; a small number of real-model smoke runs on cheap aliases, run once when confident → fix → retest, not every run.
5. **Resilience:** if AI is disabled or the model errors, run offline for parts that do not need AI (native-text CV parsing, deterministic fit score, deterministic competition bands, DB job search, saved/applications reads); for parts that need AI, return a clear user-safe unavailable state. Never fabricate.
6. **Student chatbot:** separate from partner/university assistants; student-serving tools only; **chat only, no file upload**; all tools operate **strictly within the platform** (no external web search).

## 3. Ground-truth current state (verified in code, 2026-07-08 audit)

- The credit ledger (`ai_billable_usage` + `UsageContext` + `record_billable_usage`, migration `0083`) is fully built but **DEAD — zero callers**. Wiring it is the primary task, not building anew.
- Only AI chat is metered (`ai_assistant/application/chat_service.py:173,382` → `usage_service.enforce_quota`). ~90% of student AI (cover letter, CV edit, CV Studio draft/fill/bullets/rewrite/optimize, matching explanation, JD extraction, **vision CV/JD extraction**) bypasses metering via `app/ai/cv/llm.py` (`generate_note`/`generate_json_note`) or a raw `httpx.post` (`app/ai/extraction/adapters/vision.py:239`), using the **sync** `log_ai_usage` that writes no DB row, no user_id, no cost, no quota.
- Weekly window already exists (200/week) but counts only chat → appears broken. Daily exists in two places: request-count daily + USD-daily (`budget_guard` + `billing/limit_facade`; VinUni $0.20/day, external $0.02/day).
- Deterministic CV-JD fit score is solid and free (`app/ai/cv/job_fit.py`, `SCORER_VERSION` stamped; persisted in `cv_job_fit_scores`). `semantic_scorer` already parses per-requirement suggestions/evidence but `job_fit_service.py` keeps only the summary.
- Competition intelligence substantially exists (`opportunities/application/competition_service.py`) but the headline level is count-driven (not quality-adjusted), and the "applicant quality" pool reads `cv_job_fit_scores` (anyone who viewed a fit = browsers), never joined to actual applicants. No fit snapshot at apply time.
- Job detail (`frontend/src/app/[locale]/(public)/jobs/[jobId]/page.tsx` → `public-job-detail.tsx` → `student-job-intelligence-panel.tsx`) auto-fires 3 overlapping queries on mount; no "Analyze CV" / "Competition" triggers; `components/ui/sheet.tsx` drawer exists but is unwired. No AI energy meter in the student marketplace header.
- Degradation partially exists: `real_provider_active()` (`app/ai/gateway/factory.py`), `OfflineProvider`, cascade `ocr_unavailable`, interview-sim eval cases asserting `degrades_to_deterministic`. Multi-agent infra exists: `app/ai/agents/workforce.py` (+ `coordinator.py`, `worker_tasks.py`) currently for bulk screening briefs (partner).
- Student assistant tools are already persona-scoped (`ai_assistant/application/tools/specs.py`, `persona=[STUDENT]`), read-only or confirmation-gated, with **no file-upload tool** and a `fallback_behavior` on every tool. i18n gap: `ConfirmationCopy` is hardcoded Vietnamese.

## 4. Cross-cutting principles

- **Multi-tier AI (cost cascade):** (1) deterministic first (free, authoritative) → (2) cheap cached AI, only on explicit user action → (3) stronger model only when the cheaper tier is low-confidence/insufficient. Charge energy only for the paid tier that actually ran. Applies to extraction, matching explanation, competition narrative, chatbot.
- **Metering is one path:** all value-affecting LLM calls route through `AiTaskRunner` + `UsageContext` + `record_billable_usage`. No direct `get_provider().complete()` or raw `httpx` for value-affecting calls.
- **Charge-on-success, idempotent:** student energy is charged only when a validated, user-visible result is produced, keyed by an idempotency key. Cache hits charge 0. Real provider USD cost is always recorded to the superadmin ledger regardless of success (cost visibility), but student energy is not charged for a failed user-visible output.
- **Never fabricate:** blank/not-CV/corrupt uploads, AI-unavailable, and below-min-signal states return clear statuses — never a fake CV, score, explanation, or competition claim.
- **Privacy & leakage:** never expose provider/model/token/USD/latency/raw confidence/prompt/embedding internals or raw applicant counts/identities/exact ranks to students. Student unit is masked energy %; competition is coarse bands only.
- **RBAC & audit:** enforce in the service layer; every write audited; confirmation-gated AI writes produce a visible diff/confirmation + audit trail.

## 5. Workstreams

### WS-1 — AI Energy metering backbone

**Goal:** one metered path; masked energy %; weekly hard + 3h soft; tiered allowance + wallet; daily removed.

**Design:**
- **Energy unit:** a per-feature energy weight table (`FEATURE_* → base_energy`), calibrated to observed real provider cost so relative cost is honored (e.g. vision extraction ≫ text tweak), with optional output-size multipliers for high-variance ops. Charge is deterministic and predictable per successful op. Real USD cost recorded to `ai_billable_usage.provider_cost_usd` (superadmin); energy recorded to `ai_billable_usage.units_charged`. Weights live in config/`ai_settings`, tunable by superadmin, never shown to students.
- **Account state (`ai_energy_account`, one row per user, O(1) read):** `plan_weekly_units`, `week_window_start`, `week_units_used`, `wallet_balance_units`, `updated_at`. On charge (same transaction as the op result): roll the weekly window if `now >= week_window_start + 7d`; consume weekly allowance first, then wallet; if both insufficient → block (`ENERGY_EXHAUSTED`). 3h soft: rolling `COUNT`/`SUM` over the charge ledger within 3h (backed by new `(user_id, created_at)` index); over the soft threshold → attach a soft-warning flag, do not block.
- **Windows:** remove the daily request-count window (`usage_service`) and student USD-daily budget (`budget_guard` + `billing/limit_facade`). Keep platform/org USD budget as a superadmin safety net (re-scoped — see WS-6 platform-budget fix). Weekly hard block; 3h soft warn.
- **Tiering:** `subscription_plans.limits.weekly_energy_units` per tier; `limit_facade` resolves the student's weekly allowance; grants (weekly refill, purchases) recorded to `ai_energy_transaction`.
- **API:** `GET /ai/energy/me` → `{ weekly: {used_pct, remaining_pct, resets_at}, wallet_balance_display, warn_soft: bool, blocked: bool, upgrade_path }`. No tokens/USD. `POST /ai/energy/topup` (manual/bank-transfer adapter per V1 payment default) creates a pending top-up; superadmin/billing confirmation grants wallet energy.
- **UX:** energy meter in the student marketplace header quick actions (adapt `SidebarUsageCard` → `HeaderAiButton` area); at the point of action (Analyze CV, CV Studio, chatbot) show remaining % + the op's energy cost before charging an AI write; 80% warn; block state shows upgrade/top-up, never a raw number.

**Shared foundation:** the same `ai_billable_usage` + `UsageContext` ledger and gateway path underpin the parallel **partner AI overhaul** (org + department/user quota + top-up). Keep the energy model scope-aware via `billing_scope`/`actor_persona` so student (per-user) and partner (per-org/dept/user) metering share one substrate; do not fork the ledger.

**Acceptance:** every student AI op decrements energy exactly once on success (idempotent under retry); cache hit charges 0; weekly exhaustion blocks with upgrade UX; 3h over-threshold warns without blocking; no daily enforcement remains; no token/USD leaks to student surfaces; energy meter visible in header and at points of action.

### WS-2 — Route ALL value-affecting LLM ops through the metered path

**Call sites to convert (each gets a `FEATURE_*` key + energy weight + `UsageContext`):**
- `app/ai/extraction/adapters/vision.py:239` (vision CV extract) — **priority 1, worst leak**; move onto the gateway provider + metering (stop raw `httpx`).
- JD extraction vision + text structuring (`app/ai/extraction/jd/cascade.py`, `jd/structuring.py`).
- `cover_letter_service.py`, `cv/edit_command.py`, `cv/tasks.py` (draft/fill/bullets/rewrite/optimize), `semantic_scorer.py` (fit explanation), `skill_translation.py`, `interview_sim_service` (question + answer feedback).
- Thread `UsageContext` through `app/ai/cv/llm.py` `generate_note`/`generate_json_note`, or route them via `AiTaskRunner`.
- Fix `CvAiResult.credits`/`edit_command` credits that are computed but never consumed.
- Deterministic ops (`job_fit` score, `term_expansion`, `grounding`) stay free (correct).
- Cost-tier cascades charge only the paid tier that ran (native text/local OCR free).

**Acceptance:** grep shows no value-affecting `get_provider().complete()`/raw `httpx` outside the gateway; each op writes exactly one `ai_billable_usage` row on success with correct `feature_key`, `actor_persona`, `billing_scope`, `provider_cost_usd`, `units_charged`; offline/failed calls write no student energy charge.

### WS-3 — CV-JD matching: surface what is computed then discarded

**Design:** keep deterministic score authoritative (free). Persist and surface `semantic_scorer`'s structured per-requirement suggestions, evidence strength, and `overall_suggestion` (currently dropped by `job_fit_service.py`). Feed fit gaps into the **closed loop**: each gap exposes a one-click "apply improvement in CV Studio" that opens the existing `CvAiSuggestion` pending-diff flow (confirmation-gated, versioned, never silently mutates). Consolidate the 3 overlapping fit queries into one authoritative endpoint. AI narrative is on-demand, cached, charged; deterministic bands + gaps are free.

**Acceptance:** structured suggestions returned by the analysis endpoint; one-click gap→CV Studio diff works and is confirmation-gated; single authoritative fit endpoint; scores consistent across surfaces.

### WS-4 — Job detail redesign (`/[locale]/jobs/[id]`)

**Design:**
- Default view shows **only the fit score** (ring + 6 bands) — computed on mount (deterministic, cheap), no auto-firing of 3 calls.
- **"Phân tích CV" / "Analyze CV" button** → right-side `Sheet` drawer: best CV to use, matched/gaps with evidence, actionable improvements/additions, learning gaps, and one-click → CV Studio. This is an AI action: shows energy cost + remaining %, charges on success, cached per `(cv, job)`.
- **"Mức độ cạnh tranh" / "Competition" button** → right-side `Sheet` drawer: quality-adjusted competition dashboard (WS-5). Bands only — never a raw applicant count.
- Drawers slide from the right, keep the JD readable (dimmed, not occluded), preserve focus/Escape per `UI_QUALITY_BAR`. Guests never see personalized fit/competition. v9 Monochrome tokens; reconcile the glass-vs-card token inconsistency.

**Acceptance:** score-only default; both drawers open on click and are accessible; analysis charges energy with visible cost; competition shows no raw counts/PII; guest gate holds; no redundant fetches.

### WS-5 — Competition intelligence realism (quality-adjusted)

**Design:**
- **Fix the population bug:** persist `fit_score` (+ `scorer_version`) onto the immutable `application_cv_snapshots` at apply time → the applicant-quality pool = actual applicants, complete and reconstructable point-in-time.
- **Quality-adjusted headline:** count effective strong competitors (applicants with fit ≥ strong threshold and/or ≥ the student's fit). A job with 1000 weak applicants + 20 strong for 1 seat reads on the 20, not the 1000.
- **Bands, never counts:** applicants-per-seat band; strong-competitor-density band (few/some/many strong per seat); the student's standing vs the strong pool (ahead/among/behind); deadline pressure. Min-pool guard (≥5) → explicit low-signal state; never fabricate.
- **Multi-tier AI:** deterministic bands (free, authoritative) → cheap cached narrative ("why is this competitive for you") only on demand. AI never moves the numbers.
- **Read model `job_competition_daily`** (analogous to `partner_job_metrics_daily`) to avoid heavy live multi-domain joins on the hot job-detail surface; refreshed on apply events + daily.
- **Optional funnel discount:** remaining seats = headcount − advanced/hired (needs a `positions_filled` counter).
- **Standardize** on the student-aware variant for authenticated students; never show the thin public `compute_signal` badge to a logged-in student.

**Acceptance:** headline reflects applicant caliber, not raw volume; quality pool = real applicants; no raw counts/identities/ranks exposed; low-signal rendered honestly; competition computed from the projection on the hot path; public thin badge never shown to students.

### WS-6 — Additional world-class student features + known fixes

- **Interview simulator with memory:** persist sessions, answer history, and a progress/readiness trend across attempts; feed readiness signals; gate the `(public)/jobs/[jobId]/interview-sim` route to students; charge energy per feedback.
- **Agentic assistant loop-closing write tools (confirmation-gated):** "tailor my CV to this job", "draft + attach cover letter and apply", "set a job alert", "register for this event" — beyond the current `save_job`/`apply_job`. Each declares `confirmation_copy`, `side_effects`, `audit_event_type`, `fallback`.
- **i18n fix:** `ai_assistant/application/tools/specs.py` `ConfirmationCopy` → i18n vi/en.
- **Energy wallet UX** on `/student/billing`: weekly %, wallet balance, top-up (manual/bank transfer), upgrade nudges.
- **Notifications depth:** deadline nudges, application-status changes, interview reminders (re-engagement); currently read/mark-only.
- **Known fixes:** `onboarding/application/doc_verification.py:42` imports non-existent `async_session_factory` (runtime ImportError) → use `get_sessionmaker`; `budget_guard` platform layer sums ALL users' cost (one tenant exhausts the global cap) → scope it.
- **(Stretch) normalized skills table** (skill, 0-100 level) enabling proficiency-aware scoring + applicant analytics — flagged as a larger, separable change; not required for phase completion.

**Acceptance:** interview sessions persist with a visible trend; new write tools work with confirmation + audit; confirmation copy is i18n; wallet UX functional; deadline/status/interview notifications dispatched via the outbox; the two known bugs fixed with tests.

### WS-7 — Database migrations (consolidated)

Each migration has upgrade + downgrade; permission/tenant/failure-mode tests.

- Wire existing `ai_billable_usage` (no schema change to begin charging).
- **New** `ai_energy_account` (per-user O(1) meter): `user_id` PK, `plan_weekly_units`, `week_window_start`, `week_units_used`, `wallet_balance_units`, `updated_at`.
- **New** `ai_energy_transaction` (append-only audit: weekly refill / purchase grant / charge referencing the billable row).
- Add composite index `(user_id, created_at)` on the charge ledger for the 3h rolling window.
- Add `fit_score` + `scorer_version` to `application_cv_snapshots` (nullable; written at apply time).
- **New** `job_competition_daily` projection (seats/remaining, active-application band, strong-competitor-density band, quality distribution buckets, refreshed_at).
- Add `weekly_energy_units` to `subscription_plans.limits` per tier.
- Remove daily-only enforcement logic (config + code); keep tables.
- **Discovery/personalization (WS-12):** `recommendation_snapshots` (what a guest/student was shown, for audit/repro/eval). `discovery_sessions.coarse_tags` moves to a PII-free `{tag:{count,last_seen}}` shape — JSON-shape change + ranker weighting/decay, no column migration; add a compact per-session aggregate read-model only if the ranker needs it on the hot path.
- **Advertising (WS-13):** `ad_placement_metrics_daily` per-campaign analytics read-model (impressions/clicks/CTR/apply-starts/cost-per-apply/pacing). Targeting descriptor + budget/pacing persist in the existing `sponsored_placements.settings` JSON (no new column) unless budget needs its own indexed field.
- **(Optional)** `jobs.positions_filled` counter; normalized skills table.

### WS-8 — Testing strategy (economical real-model)

- Deterministic paths (energy accounting, idempotency, windows, competition bands, fit score, degradation branching): full unit/integration tests, **no LLM**.
- LLM paths: offline/fake provider for the bulk; adversarial/privacy/fallback eval datasets per `.claude/rules/ai.md` (5 categories) for each shipped AI task including new/changed ones (extraction metering, competition narrative, interview feedback, chatbot tools).
- Real-model smoke: cheap aliases (gemini-flash class), `AI_REAL_CALLS_ENABLED=true`, `AI_MAX_REAL_CALLS_PER_TEST_RUN` respected, **run once when confident → fix → retest**, not every run. Report count/alias/cost estimate without leaking provider/model id.
- CV ingestion tests cover: text PDF, Vietnamese CV, two-column, scanned/image, sparse-native-text, DOCX, blank, not-CV, password/corrupt, duplicate, OCR unavailable, **LLM disabled/unavailable**.

### WS-9 — Resilience & graceful degradation (accuracy-first)

**Goal:** the platform stays useful and correct when AI is disabled or the model errors; it degrades to offline for non-AI work and returns clear user-safe states for AI-required work; it never fabricates.

**Operation classification:**
- **Offline-capable (no AI needed):** DB job/company/event search, saved jobs, applications & status, CV library reads, native-text CV parsing, deterministic CV-JD fit score, deterministic competition bands, PDF export of template CVs.
- **AI-optional (deterministic result + optional AI enrichment):** CV-JD analysis (score always; narrative/suggestions degrade to hidden/"unavailable"), competition (bands always; narrative optional), job recommendations (deterministic ranking fallback), extraction of native-text CVs (text tier free; vision only for image/scanned).
- **AI-required (no deterministic substitute):** vision extraction of image/scanned CVs, cover letter draft, CV Studio AI edits, chatbot conversation, interview-sim question/feedback.

**Degradation contract (three failure modes, per op):**
1. **AI globally disabled** (feature flag / `ai_settings`): AI-optional ops return the deterministic result with an `ai_unavailable` marker; AI-required ops return a clear user-safe unavailable status (e.g. "AI đang tạm ngưng, thử lại sau"), never an error code/provider name; no energy charged.
2. **Provider error/timeout** (`real_provider_active()` false, or call fails after retries): same as (1) at the op boundary; the cascade tries the next capable tier first (native text before vision, deterministic before AI); a genuinely AI-required op that cannot complete surfaces a retryable status; no energy charged.
3. **Energy exhausted:** AI-required ops return the block/upgrade state before calling the provider; AI-optional ops still return their deterministic result.

**No-fabrication guarantees:** vision tier returns `is_cv=false`/no-result for non-CVs; the cascade never fabricates a CV from blank/junk; matching/competition never invent scores/claims below min-signal; the assistant answers only from system tools/data, never invented jobs/companies.

**Surface:** a health-aware capability state drives UI (upload button shows "AI extraction paused — you can still upload; we'll extract when AI is back" for scanned files, or proceeds offline for native-text). Reuse each tool's `fallback_behavior`.

**Acceptance:** with AI disabled and with a forced provider error, every student AI entry point returns a defined user-safe state (verified by tests); offline-capable flows still work; no fabricated CV/score/competition; no provider/model/token leak in any degraded response.

### WS-10 — Student chatbot (system-internal, chat-only, agentic)

**Goal:** a student-only assistant, fully separate from partner/university assistants, chat-only (no file upload), operating strictly within the platform (no external web search), that calls tools to search and act inside the system.

**Design:**
- **Persona isolation:** the student session exposes only `persona=[STUDENT]` tools (already the model in `tools/specs.py`); partner/university tools are never selectable in a student session. System prompt is the student variant.
- **No file upload:** the chat surface has no upload affordance and no upload tool; CV work is done via CV Studio / CV library, which the assistant can link to and act on by reference (CV id), not by ingesting uploads in chat.
- **System-internal tools only (no external calls):** existing student tools — `search_jobs`, `get_job_detail`, `recommend_jobs`, `get_skill_gap`, `get_career_advice`, `get_salary_benchmark`, `start_interview_sim`, `get_my_applications`/`cvs`/`saved_jobs`/`alerts`/`interviews`/`registered_events`, `search_companies`, `get_company_detail`/`reviews`, `knowledge_base_query` (internal KB RAG), `save_job`/`apply_job` (confirmation-gated). Add the WS-6 loop-closing write tools. All read/write the platform DB/read-models only; `knowledge_base_query` is restricted to the internal KB; there is no web/browse tool.
- **Agentic loop:** ReAct with `MAX_ITERATIONS=8`, `MAX_TOOL_CALLS_PER_TURN=12` (`.claude/rules/ai.md` §4.1); writes are confirmation-gated with visible cards + audit.
- **Metered:** each chat turn and each tool-invoked AI op charges energy via WS-1; the chat shows remaining %; exhaustion blocks with upgrade UX.
- **Degrades (WS-9):** if AI is off, the chat surface shows an unavailable state but deep-links to the equivalent deterministic UI (e.g. `/jobs` search); tool results that are deterministic (e.g. `search_jobs`) still power those UIs directly.

**Acceptance:** a student session can only see/call student tools; no upload path exists; the assistant answers only from system tools/data (no external content, no invented jobs); job search goes through `search_jobs` against the platform; writes are confirmation-gated + audited + metered; energy is shown and enforced; degraded state is safe.

### WS-11 — Multi-agent automation (product-facing)

**Goal:** use specialized/coordinated agents where they add real product value, always respecting confirmation gates and human final say.

**Design (grounded in existing infra):**
- **Extend the workforce coordinator** (`app/ai/agents/workforce.py`, `coordinator.py`, `worker_tasks.py`) — today it runs bulk screening briefs for partners — with student-relevant background jobs where deterministic-first + AI-escalation applies, e.g. batch re-scoring of a student's CVs against new matching jobs, or refreshing `job_competition_daily`. Celery tasks are idempotent.
- **Specialized AI passes as "agents":** the matching/competition pipelines are modeled as distinct passes — deterministic scorer → gap analyzer → narrative explainer — with confidence-gated escalation to a stronger model only when the cheaper pass is low-confidence. This is the "many layers of AI to save tokens" the owner asked for, kept advisory (AI never overrides deterministic numbers).
- **Assistant as orchestrator:** the student assistant composes read tools + confirmation-gated write tools to close loops (analyze → tailor CV → draft cover letter → apply) with explicit confirmations at each write.
- **Guardrails:** no autonomous consequential writes without confirmation; all agent runs audited; no provider/model leakage; background runs metered to the initiating user where they incur provider cost.

**Acceptance:** background agent runs are idempotent, audited, and metered; escalation only fires on low confidence; no autonomous unconfirmed writes; competition/matching numbers remain deterministic with AI explanation only.

### WS-12 — Public / guest discovery + progressive session personalization

**Goal:** a guest (not-logged-in) discovery experience that gets progressively better as the visitor browses, privacy-safe — by wiring the personalization loop that already exists in the backend but is dead-lettered on the capture side.

**Ground truth:** the ranker (`discovery/application/ranking_service.py:286` `_session_component`; `marketplace/application/overview_service.py:238-281`) already consumes `categories`/`industries`/`role_families` coarse signals and emits honest reason codes (`similar_industry`, `similar_role`, with `recent`/`popular` fallback). A privacy-safe guest session store exists (`discovery_sessions`, httpOnly `vinuni_discovery` cookie, default-deny allowlist `discovery/domain/allowlist.py`). **But no frontend surface emits industry/role signals, and the job-detail page records no `view` event** — so a guest reading 20 Finance JDs records nothing.

**Design:**
- **Emit the missing coarse signals** (`categories`/`industries`/`role_families`) from `JobListItem`/`JobRow` tracked items and the jobs/events/company mega-menus (today only `search_terms`/`company_ids`/`work_mode`/`city` flow).
- **Record a `view` discovery event on job detail** (`public-job-detail.tsx` fires only `apply_start` today) with the viewed job's industry/category/role_family in `signal_tags`; same for `event_detail` and `company_profile` (allowlist already defines these surfaces).
- **Signal weighting + decay + counts:** `coarse_tags` is presence-only, most-recent-wins, capped — so "viewed Finance 20×" cannot outrank "once" and a 29-day tag counts fully. Move to a PII-free `{tag: {count, last_seen}}` shape (or a compact per-session aggregate) and apply time-decay + frequency weighting in the ranker.
- **`recommendation_snapshots`** (spec §8, currently absent): persist what a guest/student was shown for audit/debug/repro and as the substrate for offline ranking evals.
- **Unify `search_logs` with the ranker:** keyword suggestions (`search_logs`) and job ranking (`discovery_sessions.coarse_tags`) are disconnected; feed recent search terms into `_query_component` or converge the stores.
- **Guest → login continuity:** on login, link `discovery_sessions.user_id` and carry accumulated coarse signals into the student's personalized recommendations (link column exists; ensure carry-over).
- **`career-explore` content:** replace the placeholder (`career-explore/page.tsx`) with real role guides / skill tracks / career-content rails for guests (spec §2/§6).
- **Privacy:** everything stays within the default-deny allowlist (no PII, exact location, raw IP, raw CV text, sensitive categories, third-party ad ids); opt-out and TTL honored.

**Acceptance:** guest browsing measurably improves recommendations (industry/role signals flow end-to-end); job-detail/event/company view events recorded with coarse tags; weighting/decay in effect; `recommendation_snapshots` persisted; `career-explore` is real content; guest→login carries signals; the forbidden-signal allowlist is enforced (tests). Honest source labels preserved — never label a rail "recommended" without a real signal.

### WS-13 — Advertising realism (campaign-grade + student relevance)

**Goal:** extend the already-solid advertising system to campaign-grade while preserving its trust guardrails. (Built today: `advertising` DDD module — `ad_packages`, `sponsored_placements`, `campaign_creatives`; disclosure taxonomy `advertising/domain/disclosure.py`; organic/recommended/sponsored/curated separation; partner campaign UI; university moderation; frequency cap.)

**Design (gaps to close):**
- **Targeting** (absent): a validated targeting descriptor persisted in the existing `sponsored_placements.settings` JSON (region, industry, role family, work mode, student segment, degree/major/year, language) for automatic/manual/university-restricted modes; wire into `inventory_facade.list_active_sponsored` / `ranking_service._resolve_sponsored` so paid slots are **relevance-filtered** (not newest-first) → sponsored inventory becomes relevant to the student/guest. **Reuse the discovery forbidden-signal allowlist** so targeting can never use PII/sensitive categories.
- **Budget & pacing** (absent — fixed price × duration only): budget/spend model, even pacing across the window, spend-based completion.
- **Per-campaign analytics for partners** (absent — `discovery_events.placement_id` captured but never aggregated): a per-placement read model (impressions, clicks, CTR, apply-starts, save-intent, cost-per-apply, pacing/frequency coverage) + partner endpoint + UI. Reuse `health_service` privacy discipline (aggregates only, no PII). This is a currently-failing spec acceptance gate.
- **Link ad spend to package entitlements** (billing standalone/manual today): either package entitlements grant/consume ad slots, or reconcile manual-pay into partner billing views.
- **Creative policy pre-checks** (human approve/reject only): deterministic pre-checks (dimensions vs `SLOT_SPECS`, banned claims, off-platform contact, disclosure presence) feeding the existing escalation queue.
- **Wire reserved slots** (`inline_card`, `event_banner`) + confirm event-target delivery parity.

**Preserve (do not regress):** paid disclosure non-removable; paid→editorial relabel blocked; curated fallback never tracked/reported as paid; organic/recommended rail never reordered by sponsored; university-curated stays on the editorial (SealCheck/Handshake) styling, never the amber ad chip.

**Acceptance:** sponsored inventory is relevance-targeted (privacy-safe); budget/pacing enforced; partner sees per-campaign analytics; ad spend reconciled with billing; creative pre-checks run; organic/paid separation + curated trust preserved. The student-relevant slice (targeting so sponsored is relevant) may ride with WS-12; the rest is partner/monetization-facing (Phase 4).

### WS-14 — Frontend IA/UX consolidation (student)

**Goal:** remove the "tùm lum" (messy) feeling. The audit confirms the IA is sound and state-complete (every screen has skeleton/empty/error/auth states; modals trap focus; monochrome tokens are correctly wired). The mess is **surface-treatment drift + duplication + dead files** — a consolidation/polish pass, not a rebuild.

**Design (prioritized):**
1. **Kill glass/gradient drift → flat `marketplace-card` on student operating surfaces** (glass reserved for topbar + slide-in panels only, per `DESIGN.md` §1.1.1 — the named "single biggest cause of a messy surface"). Offenders: `student-job-intelligence-panel.tsx`, `interview-prep-panel.tsx`, applications stat tiles/rows, `job-alerts-screen.tsx`, `saved-jobs-screen.tsx`, `interview-simulator-screen.tsx`, `student-events-screen.tsx`.
2. **Consolidate job-detail fit queries** (aligns with WS-4/WS-3): drive `StudentJobIntelligencePanel` from the single `student-intelligence` payload (already carries `.fit` incl. `explanation`); drop the redundant `cv-job-fit` + `fit-explanation` fetches, or make per-CV ranking authoritative and drop `.fit` from the intel contract. Removes duplicate band data + 1–2 round-trips.
3. **Replace the copy-pasted fake "AI Insights" banner** (4 screens: applications/saved/alerts/events) with one honestly-labeled shared component ("Tổng quan"/"Summary", not "AI") — the content is deterministic client heuristics; the "AI" label violates the quality bar.
4. **Delete dead/duplicate files:** `public-job-board (1).tsx`, `auth-shell (1).tsx`, `cv-fit-panel.tsx` (superseded), `job-fit-score-badge.tsx`, `student-mobile-nav.tsx`.
5. **Unify the student nav source of truth:** reconcile `PUBLIC_PRIMARY_NAV` (rendered) vs `STUDENT_PRIMARY_NAV`/`WORKSPACE_NAV.student` (config); remove unused `careerExplore`/`employers` keys and the vestigial sidebar model; de-scaffold the `(student)/student/[...slug]` catch-all "coming soon".
6. **Trim the job-detail right rail** (aligns with WS-4): collapse the two stacked AI panels (intelligence + interview prep) into progressive disclosure (tab/accordion), consistent with the on-demand drawers.
7. **Standardize the page header** (route CV Studio / notifications / job detail through `PageHeader` or document why they differ) and settle an 8–12px radius scale.
8. **i18n the onboarding shell** (hardcoded Vietnamese `NEXT_STEPS`, "Đăng xuất", step labels, right-rail marketing copy) — breaks the `en` locale.
9. **Monochrome:** convert homepage gradient icon chips → `icon-chip-*`; de-dup the dashboard hero placeholder cards; remove decorative gradients on operating surfaces.
10. **Nits:** fix non-standard `size-4.5` icons; remove the alerts double-padding; ensure fit color is always paired with a numeric label (color-not-only-signal).

**Acceptance:** one card treatment on operating surfaces; no duplicate fit fetches; no mislabeled "AI" banners; dead files removed; single nav source; consistent headers/radius; onboarding i18n; no decorative gradients on operating surfaces; monochrome + a11y pass. Do the job-detail items together with WS-4.

### WS-15 — Additional student intelligence & automation (owner: "còn thiếu nhiều cái thực tế")

**Goal:** the realistic, high-value student features that close the loop from discovery → applied → outcome. All deterministic-first with AI narrative; all AI writes confirmation-gated + metered; never fabricate.

- **CV strength + readiness coaching:** an overall CV strength score + completeness coaching, and per-job apply-readiness (extend `student_intelligence_service` apply_readiness). Deterministic signals + cheap AI narrative on demand.
- **AI job-alert digests (email):** scheduled digests of newly-matched jobs via the notifications outbox + matching (beyond static keyword alerts); respects preferences; energy-free (deterministic matching) except optional AI summary.
- **Offer comparison + negotiation helper:** when a student has multiple offers (`recruitment` offers), a side-by-side comparison + AI negotiation guidance grounded in the internal salary benchmark; confirmation-gated; never guarantees an outcome or exposes internals.
- **Learning resources from skill gaps:** map a job's learning gaps → internal/curated learning resources (closed loop from WS-3 gaps); no external scraping.
- **Smart apply ("improve then apply"):** one guided flow from job detail — analyze → tailor CV (confirmation-gated diff, WS-3) → draft cover letter (metered) → apply (confirmation-gated) — composed by the assistant (WS-10/WS-11).
- **Application next-best-action:** per application, a deterministic "what to do next" (follow up, prep interview, withdraw, improve CV) — grounded in real status, no fabrication.
- **AI feedback loop:** thumbs up/down on AI suggestions feeding the online eval sampling (`.claude/rules/ai.md` §10.2) for continuous improvement.
- **Duplicate-application guard:** surface already-applied state and prevent accidental re-apply.

**Acceptance:** each feature is deterministic-grounded, metered where it calls a model, confirmation-gated for writes, honestly labeled, and privacy-safe; no fabricated scores/claims; feedback samples recorded.

## 6. Phasing

- **Phase 1 — Foundation:** WS-1 (energy metering backbone), WS-2 (route all LLM ops), WS-9 (resilience/degradation), core WS-7 migrations, WS-8 harness. Root cause of the owner's complaints; unblocks everything. Shares the metering substrate with the partner overhaul.
- **Phase 2 — Job intelligence:** WS-3 (matching suggestions + closed loop), WS-4 (job-detail redesign + drawers), WS-5 (quality-adjusted competition), remaining WS-7 (`fit_score` snapshot, `job_competition_daily`), the job-detail slice of WS-14 (fit-query consolidation, glass→flat, rail trim), plus the WS-15 job-detail slice (CV strength/readiness, smart-apply, application next-best-action).
- **Phase 3 — Discovery & assistant:** WS-12 (guest personalization loop), WS-10 (student chatbot), WS-11 (multi-agent automation), plus WS-15 smart-apply orchestration + AI feedback loop.
- **Phase 4 — Polish, gaps & monetization:** WS-14 remainder (frontend consolidation/polish, nav unification, dead-file cleanup, onboarding i18n), WS-6 (interview memory, new write tools, notifications depth, wallet UX, known fixes), WS-15 remainder (alert digests, offer comparison/negotiation, learning resources, duplicate-application guard), WS-13 (advertising campaign-grade realism).

Each phase ends at a checkpoint: green backend quality gates, tests/evals, and a `docs/IMPLEMENTATION_STATUS.md` update distinguishing `implemented` / `API wired` / `browser verified` / `E2E verified`.

## 7. Rollout, rollback, risks

- **Rollout:** energy metering behind a flag; start in shadow (record charges without blocking) to calibrate weights, then enforce weekly hard block. Competition realism behind a flag; keep low-signal honest.
- **Rollback criteria** (per `.claude/rules/ai.md` §17): if metered enforcement produces false blocks or double-charges, revert to shadow; if competition realism misclassifies below min-pool, fall back to low-signal.
- **Risks:** energy-weight miscalibration (mitigate with shadow period + superadmin-tunable weights); population/snapshot backfill for existing applications (competition realism only complete for post-migration applies — document the backfill limit, never fabricate history); cache-hit accounting must charge 0 to avoid over-charge; removing daily must remove both mechanisms or daily remains live.

## 8. Open questions (non-blocking; resolve during planning)

- Exact weekly energy allowance numbers per tier (Free/Premium) and top-up pack sizes — needs a calibration pass from real-cost telemetry (shadow period).
- Whether to ship the normalized skills table now (WS-6 stretch) or defer to a separate spec.
- Whether `positions_filled` funnel discounting ships in Phase 2 or defers.
- Advertising billing model (WS-13): do package entitlements grant/consume ad slots, or keep manual bank-transfer pay and only reconcile it into partner billing views?
- Guest signal weighting (WS-12): `{tag:{count,last_seen}}` in the existing `coarse_tags` JSON vs a separate per-session aggregate read-model — decide by ranker hot-path cost.
- `career-explore` content scope (WS-12): how much role-guide / skill-track content ships in Phase 3 vs a later content pass.
