# Student AI — Phase 4: Polish + Gaps + Monetization — Plan

> Executes spec WS-14 (frontend consolidation), WS-6 (student gaps + known fixes), WS-15 remainder, WS-11 workforce job, WS-13 ads campaign-grade, + the cascade vision-cost fix. Worktree `feat/student-ai-overhaul`. TDD; offline AI; no commits until owner asks. Grounded in the Phase-0 audits (frontend UX-debt + advertising gaps). Alembic head currently `0088`.

## Batch 1 (independent — launch together)

### Task J (frontend, WS-14) — Frontend consolidation ("tùm lum" fix)
Per the frontend audit, the IA is state-complete; the mess is surface drift + duplication + dead files. Consolidation, NOT rebuild.
- **Glass/gradient → flat `marketplace-card`** on student OPERATING surfaces (glass reserved for topbar + slide-in panels per DESIGN §1.1.1): `student-applications-screen` stat tiles/rows, `job-alerts-screen`, `saved-jobs-screen`, `interview-simulator-screen`, `student-events-screen`, dashboard tiles. (Job-detail panels already converted in Phase 2.)
- **Replace the copy-pasted fake "AI Insights" banner** (applications/saved/alerts/events — deterministic client heuristics mislabeled "AI") with ONE honestly-labeled shared component ("Tổng quan"/"Summary", not "AI").
- **Delete dead/duplicate files:** `public-job-board (1).tsx`, `auth-shell (1).tsx`, `cv-fit-panel.tsx` (superseded), `job-fit-score-badge.tsx`, `student-mobile-nav.tsx`.
- **Unify student nav source of truth:** reconcile rendered `PUBLIC_PRIMARY_NAV` vs config `STUDENT_PRIMARY_NAV`/`WORKSPACE_NAV.student`; remove unused `careerExplore`/`employers` keys + the vestigial sidebar model; de-scaffold the `(student)/student/[...slug]` catch-all "coming soon".
- **i18n onboarding shell** (hardcoded Vietnamese `NEXT_STEPS`/"Đăng xuất"/step labels/right-rail copy → vi/en).
- **Monochrome:** homepage gradient icon chips → `icon-chip-*`; de-dup dashboard hero placeholder cards; remove decorative gradients on operating surfaces; standardize header (`PageHeader`) + 8–12px radius; fix `size-4.5`; alerts double-padding.
**Acceptance:** one flat card treatment on operating surfaces; no mislabeled "AI" banners; dead files gone; single nav source; onboarding i18n; no decorative gradients; typecheck/lint/message-parity green.

### Task K (backend, WS-6) — Known crashes + interview memory
- **Fix `onboarding/application/doc_verification.py:42`** — imports non-existent `async_session_factory`; use `get_sessionmaker`/the correct session factory (runtime ImportError crash — a known blocker + a mypy error).
- **Fix `budget_guard` platform layer** — it sums ALL users' cost with no tenant filter, so one busy tenant can exhaust the global daily cap and 402 everyone. Scope it correctly.
- **Interview simulator memory** — persist sessions + answer history + a progress/readiness trend across attempts (today ephemeral); gate the `(public)/jobs/[jobId]/interview-sim` route to students. Charge energy per feedback (already metered).
**Acceptance:** doc_verification imports resolve (crash gone, mypy error cleared); budget guard tenant-scoped (test one tenant can't starve others); interview sessions persist with a visible trend; route student-gated. Migration up/down for the interview-session table.

### Task L (ai/backend) — Cascade vision-cost fix + learning resources (WS-15)
- **Cascade tier-selection fix:** today every PDF with any native text is routed to the paid vision tier (charged 8) — a clean native-text PDF shouldn't need vision. Change `cv_ingestion_cascade.py` so vision is used ONLY when native text is insufficient/disordered/low-confidence; clean native-text PDFs stay free. Keep the scanned/image path on vision. Don't regress extraction accuracy (the degradation-matrix tests must stay green).
- **Learning resources from gaps (WS-15):** map a job's learning gaps → internal/curated learning resources (closed loop from the WS-3 gaps); no external scraping; deterministic-first.
**Acceptance:** native-text PDF extraction is free (0 energy) and still accurate; scanned/image still metered; degradation matrix green; learning-gap→resource mapping returns internal resources only.

## Batch 2 (after Batch 1)

### Task M (backend+frontend, WS-6) — Notifications depth + energy wallet UX
- Notifications: deadline nudges, application-status changes, interview reminders via the outbox + template renderer (re-engagement); currently read/mark-only.
- Energy wallet UX on `/student/billing`: weekly %, wallet balance, top-up (manual/bank transfer), upgrade nudges (consume the existing energy API).

### Task N (backend+frontend, WS-15) — Alert digests + offer compare + dup-guard
- AI job-alert email digests (outbox + matching; deterministic, optional AI summary).
- Offer comparison + negotiation helper (multiple offers → side-by-side + AI guidance grounded in internal salary benchmark; confirmation-gated).
- Duplicate-application guard (surface already-applied; prevent accidental re-apply).

### Task O (backend, WS-11) — Workforce background re-score job
- Idempotent student background job (batch re-score a student's CVs vs newly-matched jobs) in `app/ai/agents/workforce.py`/`coordinator.py`; audited, metered to the initiating user, confirmation-gated for any consequential write.

### Task P (backend+frontend, WS-13) — Advertising campaign-grade
- Targeting descriptor in `sponsored_placements.settings` (region/industry/role/segment/degree/year/language) reusing the discovery forbidden-signal allowlist; wire into `inventory_facade`/`ranking_service._resolve_sponsored` (relevance-filtered paid slots).
- Budget & pacing (spend model + even pacing + spend-based completion).
- Per-campaign analytics read-model (`ad_placement_metrics_daily`: impressions/clicks/CTR/apply-starts/cost-per-apply) + partner endpoint + UI.
- Link ad spend to package entitlements (or reconcile manual-pay into partner billing).
- Creative policy pre-checks (dimensions vs SLOT_SPECS, banned claims, off-platform contact, disclosure) → escalation queue.
- **Preserve trust:** paid disclosure non-removable; curated never tracked as paid; organic/recommended never reordered by sponsored.

## Gate (end of Phase 4)
Full `ruff`/`mypy`/`pytest` at-or-better than baseline (the doc_verification + budget_guard fixes should REDUCE mypy/known-blocker count); frontend `typecheck`/`build`; eval datasets for new AI tasks; update `docs/IMPLEMENTATION_STATUS.md` distinguishing implemented/API-wired/browser-verified.
