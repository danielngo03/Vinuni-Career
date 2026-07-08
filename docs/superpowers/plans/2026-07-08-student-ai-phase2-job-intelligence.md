# Student AI — Phase 2: Job Intelligence (Competition realism + Matching + Job-detail) — Plan

> Executes spec WS-3, WS-4, WS-5 + job-detail slices of WS-14/WS-15. Backend contract first, then frontend. Worktree `feat/student-ai-overhaul`. TDD, offline AI provider, no real-model calls except one capped smoke at the gate. No commits until owner asks.

**Goal:** Make the logged-in student job-detail experience realistic and useful: a quality-adjusted competition signal grounded in *real applicants* (not browsers), structured CV-improvement suggestions that are currently computed then discarded, and an on-demand job-detail UI (score inline + right-side "Analyze CV" and "Competition" drawers) — all privacy-safe, deterministic-first, energy-metered where a model runs.

## Global constraints (inherit Phase 1)
- Masked energy % only; charge via `app.ai.energy` (`enforce_energy`/`build_usage_context`/`charge_units`) on success. Deterministic bands/scores are free.
- Competition = privacy-safe coarse **bands only** — never raw applicant counts, individual scores, exact ranks, or identities. `low_signal` when below min pool. Never fabricate.
- No heavy live multi-domain joins on the hot job-detail surface → use a projection.
- Fit score stays deterministic + authoritative (AI never moves the number); AI only explains, on demand, cached.
- Guests never see personalized fit/competition.

---

### Task A (backend, WS-5 foundation) — Capture fit_score on the immutable application snapshot
**Files:** `backend/app/modules/documents/domain/models.py` (`ApplicationCvSnapshot` ~:479 — add `fit_score: int|None`, `scorer_version: str|None`), new migration `008X_snapshot_fit_score.py` (nullable cols; down drops), apply flow that creates the snapshot (recruitment apply path + `documents` snapshot creation), tests.
- At apply time, compute/read the deterministic fit of the chosen CV vs the job (reuse `job_fit`/`fit_store`) and write it onto the snapshot — immutable, point-in-time. Never overwrite an existing snapshot.
- Backfill: none (document that competition quality pool is complete only for post-migration applies; never fabricate history).
**Acceptance:** applying writes `fit_score`+`scorer_version` on the snapshot; immutability preserved; migration up/down; test that two applies capture independent point-in-time scores.

### Task B (backend, WS-5) — Quality-adjusted competition + projection
**Files:** `backend/app/modules/opportunities/application/competition_service.py`, new `job_competition_daily` projection (model + migration + refresh, analogous to `partner_job_metrics_daily`), refresh hook on apply events + daily, tests.
- Fix the population bug: build the applicant-quality pool from **actual applicants** (JOIN `applications` × snapshot `fit_score` by active status), not from `cv_job_fit_scores` (browsers).
- Quality-adjust the headline: effective **strong-competitor count** = applicants with fit ≥ strong threshold and/or ≥ the student's fit; fold into the level so 1000 weak applicants + 20 strong for 1 seat reads on the 20.
- New bands (coarse, min-pool ≥5 guarded, `low_signal` otherwise): applicants-per-seat, strong-competitor-density (few/some/many per seat), student standing vs strong pool (ahead/among/behind). Never emit raw counts.
- Read from `job_competition_daily` on the hot path; compute deterministically (free). AI narrative ("why is this competitive for you") only on the user-triggered Competition drawer, cached, energy-metered (`FEATURE_*` explanation weight).
- Standardize: authenticated students use the student-aware variant; never the thin public `compute_signal`.
**Acceptance:** competition reflects applicant caliber not volume; pool = real applicants; bands only, no raw counts/PII; `low_signal` honest; projection used on hot path; AI narrative on demand + cached + metered.

### Task C (backend, WS-3) — Surface discarded matching suggestions + one authoritative fit endpoint
**Files:** `backend/app/modules/documents/application/job_fit_service.py`, `app/ai/cv/semantic_scorer.py` (already parses per-requirement `MatchGap.suggestion`/evidence/`overall_suggestion` — stop discarding), the student-intelligence endpoint(s), tests.
- Return structured per-requirement suggestions + evidence strength + overall suggestion (currently only the free-text summary survives).
- Consolidate the 3 overlapping fit queries (`studentIntelligence`, `cvApi.jobFit`, `fitExplanation`) into ONE authoritative endpoint/contract so the frontend fetches once (WS-14 dedup).
- Closed loop: each gap exposes a payload the CV Studio pending-diff flow (`CvAiSuggestion`) can consume ("apply this improvement") — confirmation-gated, versioned; wire the hand-off (do not auto-apply).
**Acceptance:** analysis endpoint returns structured suggestions + evidence + learning gaps; one authoritative fit contract; gap→CV-Studio hand-off works and is confirmation-gated; AI narrative metered on demand.

### Task D (frontend, WS-4 + WS-14/WS-15 job-detail) — after A/B/C contract is stable
**Files:** `frontend/src/components/jobs/public-job-detail.tsx`, `student-job-intelligence-panel.tsx`, `interview-prep-panel.tsx`, reuse `components/ui/sheet.tsx`, new drawer components, tests.
- Default: show ONLY the fit score (ring + 6 bands) computed on mount (cheap); stop auto-firing the 3 overlapping queries.
- **"Phân tích CV / Analyze CV"** button → right-side `Sheet` drawer: best CV, matched/gaps + evidence, actionable improvements (from Task C), learning gaps, one-click → CV Studio diff. Shows energy cost + remaining %; charges on the AI narrative; cache per (cv, job).
- **"Mức độ cạnh tranh / Competition"** button → right-side `Sheet` drawer: the WS-5 bands dashboard. No raw counts. `low_signal` state rendered honestly.
- Drawers slide from the right, keep the JD readable (dim, not occluded), focus/Escape a11y. Guest gate holds.
- WS-14 job-detail slice: consolidate to the single fit query (Task C), convert glass→flat `marketplace-card` on the intelligence/interview panels, collapse the two stacked AI panels into progressive disclosure (tab/accordion).
- WS-15 job-detail slice: CV strength/readiness indicator + "improve then apply" entry; application next-best-action where relevant.
**Acceptance:** score-only default; both drawers open on click, accessible, JD stays readable; one fit fetch; flat consistent cards; guest gate; energy cost shown for the AI analysis; typecheck/build green.

---

## Sequencing
- A + C in parallel (independent). B after A (needs snapshot `fit_score`). D after A/B/C (stable contract).
- Gate: full `ruff`/`mypy`/`pytest` at baseline (no new failures) + one capped real-model smoke on a cheap alias for the competition/analysis narrative; frontend `typecheck`/`build`; update `docs/IMPLEMENTATION_STATUS.md`.
