# Student AI — Phase 3: Discovery + Assistant — Plan

> Executes spec WS-12 (guest/public personalization), WS-10 (student chatbot), WS-11 (multi-agent), + WS-15 smart-apply orchestration slice. Worktree `feat/student-ai-overhaul`. TDD, offline AI provider, no commits until owner asks. All metered via `app.ai.energy`; privacy-safe; no external web/search — everything within the platform.

## Task E (frontend, WS-12) — Emit the coarse signals the ranker already waits for
**Problem:** the backend ranker (`ranking_service._session_component`, `marketplace/overview_service`) already consumes `categories`/`industries`/`role_families` coarse signals + honest reason codes, and the guest session store (`discovery_sessions`, httpOnly cookie, default-deny allowlist) is solid — but NO frontend surface emits industry/role signals and the job-detail page records NO `view` event. So a guest reading 20 Finance JDs records nothing.
**Do:**
- Emit `categories`/`industries`/`role_families` coarse signals (privacy-safe, allowlisted only) from `JobListItem`/`JobRow` `TrackedItem`s and the jobs/events/company mega-menu items (today only `search_terms`/`company_ids`/`work_mode`/`city` flow). First verify the job objects carry industry/category/role_family; if not, add them to the public job DTO (coordinate with a tiny backend read change).
- Record a `view` discovery event on job detail (`public-job-detail.tsx` fires only `apply_start`) with the viewed job's industry/category/role_family in `signal_tags`; same for event-detail and company-profile surfaces (allowlist already defines these).
**Acceptance:** browsing emits industry/role signals end-to-end; job/event/company detail record a `view` with coarse tags; only allowlisted signals sent (no PII); guest recommendations measurably shift after browsing (test the emitted payload shape).

## Task F (backend, WS-12) — Signal weighting/decay, snapshots, unify search_logs
- **Weighting + decay + counts:** `coarse_tags` is presence-only, most-recent-wins, capped — "viewed Finance 20×" can't outrank "once" and a 29-day tag counts fully. Move to a PII-free `{tag:{count,last_seen}}` shape (or a compact per-session aggregate) and apply frequency-weighting + time-decay in the ranker. Keep the allowlist/opt-out/TTL guarantees.
- **`recommendation_snapshots`** (spec §8, absent): persist what a guest/student was shown (audit/repro/eval substrate). Privacy-safe.
- **Unify `search_logs` with the ranker:** feed recent search terms into `_query_component` (today keyword suggestions and job ranking use disconnected stores).
- **Guest→login continuity:** on login, link `discovery_sessions.user_id` and carry coarse signals into the student's personalized recs (link column exists; ensure carry-over).
**Acceptance:** weighting/decay in effect (frequency changes ranking); snapshots persisted; search terms feed ranking; guest→login carries signals; allowlist enforced (tests). Honest source labels preserved (never "recommended" without a real signal).

## Task G (backend, WS-10) — Student chatbot loop-closing write tools + i18n
The student assistant is already persona-scoped (student-only tools, NO file upload, system-internal only) and metered (Phase 1). Add the missing loop-closing, confirmation-gated write tools + fix i18n.
- New tools in `ai_assistant/application/tools/specs.py` + `dispatch.py` + handlers (each: `permission_class=confirmation_required`, `confirmation_copy`, `side_effects`, `audit_event_type`, `fallback`, `persona=[STUDENT]`): `tailor_cv_to_job` (→ CV Studio pending diff, never auto-apply), `draft_and_attach_cover_letter` (draft + attach, confirm), `set_job_alert`, `register_for_event`. Metered via energy where a model runs.
- **i18n fix:** `ConfirmationCopy` in `specs.py` is hardcoded Vietnamese → i18n vi/en (the copy must be locale-driven).
- Verify: student session exposes ONLY student tools; no upload path; `knowledge_base_query` restricted to internal KB; NO web/browse tool exists.
**Acceptance:** new write tools work with confirmation + audit + metering; i18n vi/en; student-only isolation holds; no external search; eval datasets (5 categories) for any new AI-backed tool.

## Task H (backend, WS-11 + WS-15 slice) — Multi-agent + smart-apply orchestration (lighter)
- Extend `app/ai/agents/workforce.py`/`coordinator.py` with an idempotent student background job (e.g. batch re-score a student's CVs vs newly-matched jobs) — audited, metered to the initiating user, confirmation-gated for any consequential write.
- Model the matching/competition AI as specialized passes with confidence-gated escalation (deterministic → cheap-cached → stronger only on low confidence) — much already exists; document + tighten.
- **Smart-apply** (WS-15): the assistant composes analyze → tailor CV (confirm) → draft cover letter (confirm) → apply (confirm) using the new tools — each write confirmation-gated.
**Acceptance:** background job idempotent/audited/metered; no autonomous unconfirmed writes; smart-apply chains confirmations; numbers stay deterministic (AI explains only).

## Sequencing
- E (frontend) + F (backend) + G (backend) are independent → parallel. H after G (uses the new tools).
- Gate: `ruff`/`mypy`/`pytest` at baseline; frontend `typecheck`/`build`; eval datasets for new AI tools; update `IMPLEMENTATION_STATUS.md`.
