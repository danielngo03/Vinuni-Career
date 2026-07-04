# ADR-0005: Recruitment Scorecards & required-action gating (Phase 2)

**Status:** Accepted (Proposed for implementation in the next backend slice)
**Date:** 2026-06-28
**Owner:** system-architect
**Related:** `docs/PRODUCT_REQUIREMENTS.md` MODULE 7 (§7.2 movement, §7.3 scorecard,
§7.6 candidate view, §7.7 candidate detail), `docs/BUSINESS_LOGIC.md` §3.1
(required-action enforcement), §3.4 (parallel scorecard / anchoring bias),
`docs/DATA_MODEL.md` §9 (`scorecards`), `docs/API_CONTRACTS.md` (Candidate pipeline +
Pipeline Board), `docs/SECURITY_PRIVACY.md` (partner-internal evaluations,
anonymity/reveal), `docs/ARCHITECTURE.md` §4.1. Builds directly on the **shipped**
ADR-0004 stage engine (`backend/app/modules/recruitment/application/stage_service.py`,
`pipeline_board.py`, `decision_service.py`, `domain/pipeline.py`,
`domain/models.py`) — the `scorecards` table and `required_action=scorecard`
gating that ADR-0004 §5 explicitly deferred to "ADR-0005".

## Context

ADR-0004 shipped the configurable stage engine: `pipeline_templates` /
`pipeline_stages` / `candidate_stages` (append-only, one `ACTIVE` row =
current stage), `/advance` + `/rollback`, the partner kanban board, anonymity
preserved (UV-handle pre-reveal). It seeded a 3-stage default ladder with **all
stages `required_action = manual`**, and left two named seams open for this ADR:

- `pipeline_stages.required_action` already exists; the advance path already calls
  `pipeline.action_satisfied(required_action)` and **fail-closes** any non-`manual`
  action (`stage_service.advance_application_stage`, line ~438). The seam where
  `scorecard` gating plugs in is therefore already wired — V1 just needs the gate.
- `DATA_MODEL.md` §9 already declares a `scorecards` table (named-but-deferred in
  ADR-0004 §3) so this ADR's FKs are forward-compatible.

Constraints that bound the decision (CLAUDE.md precedence: product > business >
security > architecture > API/data):

- **PRD §7.3 mandates per-stage scorecards** with self-defined criteria, 1–5
  rating per criterion, free comment, and an overall recommendation. PRD §7.4 adds
  configurable templates. As with the stage builder in ADR-0004, **configurability
  is the documented end-state, not a V1-blocking surface.**
- **BUSINESS_LOGIC §3.1** defines `required_action ∈ {scorecard, score_threshold,
  manual}` and gates advance on `submitted >= required` evaluators.
- **BUSINESS_LOGIC §3.4** (parallel scorecard): individual scores per evaluator;
  "other interviewers see scores only AFTER submitting own scorecard (prevent
  anchoring bias)"; `required` derives from the stage **assignee model**
  (department/person), which ADR-0004 §4 **explicitly deferred** to a later ADR.
- **Evaluations are partner-internal** — PRD §7.6 "Không hiện … scorecard nội
  dung" to the student; they belong to the same privacy class as `rejection_reason`
  and the rollback reason, which the shipped code never sends to the student.
- Local-first, small reversible first slice; RBAC at the service layer; no business
  logic in routers; anonymity invariants intact (CLAUDE.md / `backend.md`).

## Decision

### 1. Scorecard model — fixed criteria set + recommendation, V1 defers the criteria editor

**Mirror ADR-0004's pattern exactly:** ship the evaluation *schema* and a
**fixed system-default criteria set** (a domain constant, like `DEFAULT_STAGES`),
**do not build the per-job criteria editor**. This satisfies PRD §7.3 end-to-end
without a JSONB blob that would need re-migration when the editor lands, and
without prematurely creating `scorecard_templates` / `scorecard_criteria`.

A scorecard is **one reviewer's evaluation of one candidate at one stage**:

- **Criteria (fixed V1 set, `DEFAULT_CRITERIA` in `domain/scorecard.py`),** each
  scored **1–5** (PRD §7.3 "1–5 sao"):

  | `criterion_key` | label (vi / en) |
  | --- | --- |
  | `technical` | Năng lực chuyên môn / Technical ability |
  | `communication` | Giao tiếp / Communication |
  | `culture_fit` | Phù hợp văn hóa / Culture fit |
  | `motivation` | Động lực & sự phù hợp / Motivation & fit |

- **`overall_score`** — derived = mean of the criterion scores, stored
  `NUMERIC(2,1)` (1.0–5.0) for cheap aggregation (matches `DATA_MODEL` §9
  `overall_score`). Not a separate user input in V1.
- **`recommendation`** (required) — **4-value enum `{strong_no, no, yes,
  strong_yes}`** (PRD §7.3 "Strongly Recommend / Recommend / No / Strongly No").
  This is the primary advance signal.
- **`comment`** — optional free text, partner-internal.

**Entities — TWO tables for V1** (`scorecard_templates` / `scorecard_criteria` are
**deferred** to the criteria-editor slice that ships alongside the pipeline
template builder):

- **`scorecards`** — the submitted evaluation: FK `application_id` + `stage_id`
  (the candidate's stage at submit time) + `org_id` (denormalized, org-scoped
  reads, mirrors `applications.org_id`) + `submitted_by_user_id`.
- **`scorecard_scores`** — one row per criterion per scorecard (`criterion_key` +
  `score`). Normalized rather than JSONB so per-criterion aggregation (board
  summary, the deferred §7.8 comparison view, and future `score_threshold` gating)
  is a SQL `GROUP BY`, and so the future criteria editor can map `criterion_key →
  criterion_id` without a data rewrite.

`interview_id` (the `DATA_MODEL` §9 `scorecards.interview_id NOT NULL` FK) is
**NOT** created here — interviews are ADR-0006. A scorecard binds to
`application_id` + `stage_id` directly. See conflict #1.

### 2. Who can submit & see — partner-internal, one-per-reviewer-per-(application,stage)

- **Submit / read:** a **partner member of the job's owning org**, gated by the
  SAME service-layer authz as advance/reject —
  `decision_service._load_partner_application` (cross-org / non-partner → `404`,
  not enumerable). New permission codes `recruitment:submit_scorecard` and
  `recruitment:read_scorecard`, both **default to partner members in V1** (like
  `recruitment:move_stage`). RBAC is enforced in the service, never the router.
- **Cardinality: one ACTIVE scorecard per `(application, stage, reviewer)`** —
  enforced by a Postgres partial unique index
  `uq_scorecard_reviewer_active (application_id, stage_id, submitted_by_user_id)
  WHERE status = 'submitted'` (dialect-guarded; SQLite tests rely on the
  service-layer guard, mirroring `uq_candidate_stage_active`).
- **Edit / withdraw own:** unlike `candidate_stages` (append-only state machine),
  **a scorecard is EDITABLE in place by its author** until a decision is taken.
  Re-submitting upserts the row + its `scorecard_scores` (recomputes
  `overall_score`), bumps the scorecard's own optimistic `version`, and writes
  `application.scorecard_updated` audit. **Withdraw** sets `status = withdrawn`
  (the row is retained for audit but excluded from gating + aggregates); a reviewer
  may only edit/withdraw **their own** scorecard. No reviewer may touch another's.
- **Who aggregates:** aggregation is a **service-layer read** over `status =
  submitted` rows (no stored aggregate row) — count, mean `overall_score`,
  recommendation distribution.
- **Anchoring-bias visibility (BUSINESS_LOGIC §3.4):** the list endpoint returns
  the **caller's own** scorecard always, but **other reviewers' scores/comments
  only after the caller has submitted their own** for that stage. Before that the
  caller sees only the *count* of submitted scorecards (so they know the round is
  in progress) — never others' scores. This rule lives in the service layer.

**Visibility rule (explicit, non-negotiable):** scorecards — existence, scores,
recommendation, comment, aggregate — are **PARTNER-INTERNAL** and **NEVER** appear
in the student application projection, any student notification, or any email
body. They are the same privacy class as `rejection_reason` and the rollback
reason. The student is **never told a scorecard exists** (PRD §7.6,
`SECURITY_PRIVACY` partner-internal-evaluation rule). The advance notification the
student already receives (ADR-0004 §4) is unchanged and carries no evaluation data.

### 3. required_action gating — `scorecard` blocks `/advance`

When the candidate's **current** `pipeline_stages.required_action = 'scorecard'`,
`/advance` is **blocked until the gate is met**. The shipped advance path already
fail-closes non-`manual` actions; ADR-0005 replaces that single branch with an
**async gate check** (the pure `pipeline.action_satisfied` is insufficient — it
cannot query the DB):

```
# stage_service.advance_application_stage, replacing the action_satisfied branch:
gate = await scorecard_service.evaluate_advance_gate(
    session, application_id=app.id, stage=current
)
if not gate.allowed:
    raise ScorecardRequiredError(submitted=gate.submitted, required=gate.required)
```

- **`manual`** (the V1 default for every seeded stage): `gate.allowed = True`
  trivially — **the shipped manual path is unchanged**, no scorecard required, no
  query cost regression on the common path.
- **`scorecard`:** **V1 gate = `submitted_count >= 1`** (at least one submitted,
  non-withdrawn scorecard for `(application, current_stage)`). The full
  "all assigned reviewers / department threshold" rule (BUSINESS_LOGIC §3.1/§3.4)
  needs the **assignee model**, which is deferred — so `required` is **1** in V1.
  See conflict #2.
- **`score_threshold`** and any unknown action: **fail-closed** →
  `IllegalApplicationTransitionError` (unchanged behavior). `score_threshold`
  gating lands with the assignee/interview ADR.

**Exact error — `409 ScorecardRequiredError`**, a NEW error class:
`details.reason = "scorecard_required"`, `details = { submitted, required }`
(e.g. `{ "submitted": 0, "required": 1 }`). It is **distinct** from the generic
`illegal_transition` so the kanban can render a precise "complete a scorecard to
advance" blocked state (PRD §7.1 "Complete scorecard trước khi advance"). It
composes cleanly: `manual` stages never reach this branch; the optimistic
`version`, cross-org `404`, idempotency-key, audit, and anonymity invariants of
`/advance` are untouched.

Because the V1 seeded default ladder is all-`manual`, scorecard gating is
**dormant** until a stage's `required_action` is set to `scorecard` (tests set it
directly on a `pipeline_stages` row; production exercises it once the
template/criteria editor lands).

### 4. Anonymity

**Scorecards never weaken anonymity.** They reference `application_id` (already
redacted on the board and in every partner projection) — a scorecard carries **no
student identity field**; the reveal handshake stays the only identity path
(unchanged from ADR-0004). The board surfaces only an **aggregate** (count, mean,
recommendation distribution) attached to the existing anonymity-safe card; the
aggregate is **partner-only** and **never** flows to the student. It is **not a
re-identification vector**: the student never sees any scorecard data, and within
the partner org the candidate's identity is already governed by the existing
reveal rules — scores add no new identity surface. Reviewer identity
(`submitted_by_user_id`) is a *partner-org member*, not the student, and is only
visible to other partner members of the same org.

### 5. Data model + migration — `0013_recruitment_scorecards`

**Migration needed? YES — one migration `0013_recruitment_scorecards`** (upgrade +
downgrade), revising `0012_pipeline_stage_engine`. No change to `applications` /
`pipeline_stages` / `candidate_stages`. New tables (Postgres runtime + SQLite tests
via shared `JsonType` where needed):

| Table | Key columns / FKs | Notes |
| --- | --- | --- |
| `scorecards` | `id`, `application_id → applications ON DELETE CASCADE`, `stage_id → pipeline_stages ON DELETE RESTRICT`, `org_id → organizations`, `submitted_by_user_id → users ON DELETE RESTRICT`, `recommendation varchar(20)`, `overall_score NUMERIC(2,1) null`, `comment text null`, `status varchar(20) default 'submitted'`, `version int default 1`, `submitted_at`, `created_at`, `updated_at` | **Editable-by-author** (not append-only). `status ∈ {submitted, withdrawn}`. Index `(application_id, stage_id)`. Partial unique `uq_scorecard_reviewer_active (application_id, stage_id, submitted_by_user_id) WHERE status='submitted'` (PG-guarded; not on the ORM model so `create_all` omits it on SQLite). |
| `scorecard_scores` | `id`, `scorecard_id → scorecards ON DELETE CASCADE`, `criterion_key varchar(40)`, `score SMALLINT CHECK 1..5` | Unique `(scorecard_id, criterion_key)`. Replaced (delete+insert) on edit. |

- **Append-only vs editable:** `candidate_stages` is append-only (state machine);
  `scorecards` are **editable-in-place by their author** with a per-scorecard
  optimistic `version` + audit on every write. Withdrawal is a soft `status`
  transition, not a delete — the row survives for the audit trail.
- **No seed data step** (unlike `0012`): there are no scorecards until reviewers
  submit; `DEFAULT_CRITERIA` is a domain constant, not seeded rows.
- ORM models in `recruitment/domain/models.py` (`Scorecard`, `ScorecardScore`).

### 6. API surface

All under the existing recruitment router; HTTP-only routers, RBAC + transactions
in `scorecard_service`. Responses carry **no student identity** and the student
projection is **never** touched.

| Endpoint | Method | Authz / body | Behavior |
| --- | --- | --- | --- |
| `/applications/{id}/scorecards` | POST | partner member of the job's org (`recruitment:submit_scorecard`) + `version?`. Body `{ "recommendation": "strong_no\|no\|yes\|strong_yes", "scores": [{ "criterion_key", "score": 1..5 }], "comment"?: <text> }` | Submit / **upsert** the caller's scorecard for the candidate's **current ACTIVE stage**. `recommendation` required (422 otherwise); every `DEFAULT_CRITERIA` key required, `score ∈ 1..5` (422). `app.status ≠ under_review` or no ACTIVE stage → `409` (`illegal_transition`). Recomputes `overall_score`. Audited (`application.scorecard_submitted` / `…_updated`). Returns the caller's scorecard + the anchoring-safe aggregate. |
| `/applications/{id}/scorecards` | GET | partner member (`recruitment:read_scorecard`); optional `?stage_id=` (default: all stages, for the §7.7 detail panel) | Returns `{ "mine": <scorecard\|null>, "scorecards": [<others, ONLY if caller has submitted own for that stage>], "aggregate": { "submitted_count", "required", "gate_met", "avg_overall", "recommendation_summary": { "strong_yes": n, … }, "by_criterion": { "<key>": <avg> } } }`. **Anchoring rule (§3.4) enforced here.** |
| `/applications/{id}/scorecards/{scorecard_id}/withdraw` | POST | author only (else `404`) | `status → withdrawn`; excluded from gate + aggregate. Audited (`application.scorecard_withdrawn`). |

**Board / kanban surfacing:** `stage_service._pipeline_block` (and the
`pipeline_board` card) gain an **optional partner-only `evaluation` summary** on
the **current** stage: `{ submitted_count, required, gate_met, avg_overall,
recommendation_summary }` — so a partner sees at a glance whether a card is
advance-blocked (`gate_met=false` on a `scorecard` stage). The board already caps
cards and batches queries (ADR-0004); the aggregate is one batched grouped query
keyed by `(application_id, current stage_id)` — **no N+1**. The **student
application projection and notifications carry NO `evaluation` field, ever.**

### 7. Scope boundary + first implementation slice

**THIS ADR (ADR-0005) covers:** `scorecards` + `scorecard_scores` tables
(migration `0013`); the fixed `DEFAULT_CRITERIA` set + 4-value recommendation;
submit/upsert + list + withdraw endpoints with RBAC-404 / anchoring-bias
visibility / partner-internal anonymity; the `required_action=scorecard` advance
gate (`submitted ≥ 1`) with the new `409 scorecard_required`; the partner-only
board aggregate; audit on every write.

**Explicitly LATER (named so FKs/behaviors stay stable, design deferred):**

- **Criteria editor** — `scorecard_templates` / `scorecard_criteria` (per-job
  configurable criteria, PRD §7.3/§7.4), shipping **with the ADR-0004 pipeline
  template-builder** slice. V1's `criterion_key` maps onto `criterion_id` then,
  no data rewrite.
- **Assignee model + `score_threshold` + department threshold gating** (BUSINESS_LOGIC
  §3.1/§3.4 `required = count_required_evaluators`) → **ADR-0006 (interviews &
  scheduling)**, which also adds the nullable `scorecards.interview_id` FK.
- **AI scorecard assist** (PRD §7.3 "AI suggest scores từ interview notes") →
  AI-engineer / `AI_PRODUCT_SPEC` ADR; advisory, human-confirm, no provider leak.
- **Candidate comparison view** (PRD §7.8 side-by-side scorecard ratings) → its own
  frontend/data slice on top of `by_criterion` aggregates.
- **Auto-advance worker** when `required_action` is met + `auto_advance=true`
  (BUSINESS_LOGIC §3.3) → ADR-0003 scheduler job; **bulk advance** gated on
  scorecard completion (§3.6).
- Offers → **ADR-0007**.

**First implementation slice (backend-first) — for `backend-developer`:**

1. **Migration `0013_recruitment_scorecards`** — create `scorecards` +
   `scorecard_scores` (+ the PG-guarded partial unique active-scorecard index and
   the `score` CHECK) with upgrade **and** downgrade. Add `Scorecard` /
   `ScorecardScore` ORM models to `recruitment/domain/models.py`.
2. **Domain** — new `recruitment/domain/scorecard.py`: `DEFAULT_CRITERIA`,
   `RECOMMENDATIONS = {strong_no, no, yes, strong_yes}`, `SCORECARD_SUBMITTED /
   _WITHDRAWN` status vocab, pure `overall_of(scores)` mean, pure
   `gate_met(submitted_count, required)`; an `AdvanceGate` dataclass `{allowed,
   submitted, required}`. No I/O.
3. **Service** — new `recruitment/application/scorecard_service.py`:
   `submit_scorecard()` (upsert + version + audit), `withdraw_scorecard()`,
   `list_scorecards()` (anchoring-rule visibility + aggregate), and
   `evaluate_advance_gate(session, application_id, stage)` reused by both the GET
   aggregate and the advance hook. Reuse `decision_service._load_partner_application`
   (404 gate) + `write_audit`. Resolve the candidate's **current ACTIVE stage** via
   `stage_service._active_stage` for submit.
4. **Wire the gate** — in `stage_service.advance_application_stage`, replace the
   `if not pipeline.action_satisfied(...)` branch with the
   `scorecard_service.evaluate_advance_gate` check raising the new
   `ScorecardRequiredError`; keep `manual` a trivial allow. Add the
   `evaluation` summary to `_pipeline_block` + the board card (current stage only).
5. **Errors / API** — add `ScorecardRequiredError(ConflictError)`
   (`reason="scorecard_required"`, `{submitted, required}`) to
   `recruitment/application/errors.py`; add the three endpoints + Pydantic schemas
   to the recruitment router (HTTP only); presenter for the scorecard + aggregate.
6. **Tests (SQLite, `tester-qa` gate):** submit happy path (scores → `overall_score`
   mean + recommendation); upsert edits own (version bump, no duplicate row);
   second reviewer creates a separate scorecard; **anchoring** — reviewer B cannot
   see A's scores until B submits; withdraw excludes from gate + aggregate; advance
   on a `required_action=scorecard` stage with 0 scorecards → `409
   scorecard_required` (`{submitted:0, required:1}`); with ≥1 → advances; advance on
   a `manual` stage is unaffected (no scorecard needed); cross-org submit/list →
   `404`; missing recommendation / score out of 1..5 → `422`; **anonymity** — student
   projection + notifications carry no scorecard/evaluation field after a submit;
   audit row per submit/update/withdraw; board aggregate is partner-only and
   `gate_met` correct.

**Frontend slice (follows, after the contract is green) — `frontend-developer`:**
candidate-detail scorecard panel (criteria 1–5 inputs, recommendation selector,
comment) with submit/edit/withdraw (no `confirm()`); anchoring-aware list (others
hidden until you submit); board card "scorecard required to advance" blocked state
on a `409 scorecard_required`; the §7.7 detail "all scorecards" view; **no
scorecard surface anywhere in the student application timeline.** Mark `API wired`
→ `browser verified` → `E2E verified` distinctly.

## Consequences

- **Positive:** scorecards ship small and doc-faithful on stable ADR-0004 FKs; the
  manual advance path is untouched (gating is opt-in per stage); the anchoring rule
  and partner-internal visibility live in one service; `scorecard_scores` keeps
  per-criterion data queryable for the deferred comparison view and future
  `score_threshold` gating; the criteria editor attaches later via `criterion_key`
  with no data rewrite.
- **Cost / limits:** the V1 gate is `submitted ≥ 1` (no department/threshold
  evaluator counting until the assignee model lands); criteria are a fixed set
  (no per-job criteria until the editor ships); `interview_id` is absent until
  ADR-0006. All three are documented end-states, not V1 blockers.
- **Reversibility:** additive — dropping `0013`, the three endpoints, and the
  advance-gate branch (reverting to the ADR-0004 fail-closed) restores the
  ADR-0004 surface exactly. Seeded stages stay `manual`, so nothing breaks.

## Doc conflicts resolved (precedence: product > business > security > arch > API/data)

1. **`scorecards.interview_id NOT NULL`.** `DATA_MODEL` §9 makes a scorecard FK an
   interview, but interviews are deferred (ADR-0006) and the shipped engine has
   stages, not interviews. **Resolved:** V1 binds a scorecard to `application_id` +
   `stage_id` directly; `interview_id` is added **nullable** by ADR-0006. **Flag
   `DATA_MODEL` §9 `scorecards`** to add `application_id` + `stage_id` and relax
   `interview_id` to nullable.
2. **Gating `required` count.** BUSINESS_LOGIC §3.1/§3.4 compute `required =
   count_required_evaluators(stage)` from the assignee/department model.
   **Resolved:** that model is deferred (ADR-0004 §4), so V1 fixes `required = 1`
   (`submitted ≥ 1`). **Flag** BUSINESS_LOGIC §3.1/§3.4 as partially implemented
   (assignee-threshold gating arrives with ADR-0006).
3. **Recommendation enum width.** PRD §7.3 lists **4** values (Strongly Recommend /
   Recommend / No / Strongly No); `DATA_MODEL` §9 lists **5** (adds `neutral`).
   **Resolved (product precedence):** V1 uses the **4-value** `{strong_no, no, yes,
   strong_yes}`. **Flag `DATA_MODEL` §9** `scorecards.recommendation` as superseded
   (drop `neutral`).
4. **Criterion score scale.** `DATA_MODEL` §9 `criteria JSONB {criterion: score}`
   is unconstrained and `overall_score` is 1.0–5.0; PRD §7.3 says **1–5** per
   criterion. **Resolved:** criterion `score SMALLINT 1..5`, normalized into
   `scorecard_scores` (not JSONB), `overall_score` = mean. **Flag `DATA_MODEL` §9**
   to record the normalized `scorecard_scores` shape replacing the `criteria` JSONB.
