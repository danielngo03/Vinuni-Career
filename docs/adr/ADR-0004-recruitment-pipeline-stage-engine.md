# ADR-0004: Recruitment Pipeline Stage Engine (Phase 2 Foundation)

**Status:** Accepted (Proposed for implementation in the next backend slice)
**Date:** 2026-06-28
**Owner:** system-architect
**Related:** `docs/PRODUCT_REQUIREMENTS.md` MODULE 7, `docs/BUSINESS_LOGIC.md` §3,
`docs/DATA_MODEL.md` §9, `docs/API_CONTRACTS.md` (Candidate pipeline +
"Application Decision Status (partner) — Phase 1.5 subset"),
`docs/SECURITY_PRIVACY.md` (anonymity/reveal), `docs/ARCHITECTURE.md` §4.1,
`docs/EDGE_CASES_FAILURE_MODES.md`. Builds directly on the shipped Phase-1.5
decision subset (`backend/app/modules/recruitment/application/decision_service.py`,
`domain/lifecycle.py`) and ADR-0003 (scheduler — the future auto-advance host).

## Context

Phase 1.5 shipped the **minimal partner decision loop** on `applications`:
`POST /applications/{id}/review` (`submitted → under_review`) and `/reject`
(`{submitted,under_review} → rejected`), with coded partner-only reasons, neutral
student notifications, anonymity preserved, optimistic `version`, idempotency,
`404`-not-`403` cross-org masking, and per-write audit. The status doc and
`lifecycle.py` explicitly **deferred the configurable stage engine + `/advance` +
`/rollback` + scorecards + interviews + offers to Phase 2.**

This ADR designs that engine's **foundational layer only**: the stage data model
and the `/advance` / `/rollback` movement semantics. Scorecards, interview
scheduling, and offers are named here (so their FKs are stable) but their detailed
design is deferred to follow-on ADRs.

Constraints that bound the decision:

- **PRD MODULE 7 mandates a configurable, per-job pipeline** ("tính năng ATS cốt
  lõi… mạnh mẽ, linh hoạt"): ordered stages, types, assignees, required actions,
  SLA, auto-advance, per-stage candidate visibility, templates. This is **not** an
  optional ladder — configurability is product scope (precedence rank 1).
- `DATA_MODEL.md` §9 already declares `pipeline_templates`, `pipeline_stages`,
  `candidate_stages`, `interviews`, `scorecards`, `offers`.
- `ARCHITECTURE.md` §4.1 already fixes the state-machine shape: one `ACTIVE`
  `CandidateStage` per candidate per job; status `ACTIVE|PASSED|REJECTED|ROLLED_BACK`;
  ADVANCE/ROLLBACK/REJECT transitions; rollback reason ≥ 20 chars; audit on every
  move.
- The shipped review/reject subset is **correct and must not be broken or
  duplicated**; the new engine must compose with it, not replace it.
- Local-first, small reversible first slice (CLAUDE.md), no business logic in
  routers, RBAC at the service layer, anonymity invariants intact.

## Decision

### 1. Stage model — configurable schema, V1 ships a seeded canonical default

**Stages are per-org CONFIGURABLE templates (PRD MODULE 7 mandates it), but V1
does not build the template editor.** Instead we ship the configurable schema
(`pipeline_templates` / `pipeline_stages`) and **seed exactly one immutable
system-default template per org** so the stage engine works end-to-end against a
real configurable structure. This satisfies the docs without a throwaway hardcoded
ladder that would need re-migration when the builder lands.

**System-default template — canonical ordered ladder (V1 seed):**

| order | stage `name` (vi / en) | `stage_type` | `required_action` | terminal? |
| --- | --- | --- | --- | --- |
| 1 | Sàng lọc hồ sơ / Screening | `screening` | `manual` | no |
| 2 | Phỏng vấn / Interview | `interview` | `manual` | no |
| 3 | Đề nghị / Offer | `offer` | `manual` | **last stage** |

- The **coarse application outcome** lives on `applications.status` and is
  **unchanged** from the shipped subset: `submitted | under_review | rejected |
  withdrawn` (`hired` arrives with the offers ADR). `under_review` ≡ "active in the
  pipeline".
- The **fine pipeline position** lives entirely in `candidate_stages`. It is only
  meaningful while `applications.status = under_review`. The student is "in the
  pipeline" at exactly one `ACTIVE` `candidate_stages` row pointing at one
  `pipeline_stages` row of the org's template.
- `stage_type` is **metadata for UI/notification labeling only** — the engine
  branches on `sort_order` + `required_action`, never on type. V1 stores the coarse
  `DATA_MODEL` §9 set (`screening|interview|assessment|offer|custom`).
- For V1, **all default stages are `required_action = manual`**, so `/advance`
  works before scorecards/interviews exist. `scorecard` / `score_threshold` gating
  is the next ADR.

### 2. Transitions — `/advance` + `/rollback` layered on the shipped review/reject

**Decision: review/reject STAY SEPARATE coarse-outcome decisions (do not refactor
the shipped, working code into a generic transition engine). `/advance` and
`/rollback` are NEW operations on the fine `candidate_stages` position.** They
integrate through two well-defined seams:

- **`review` is the pipeline-entry trigger.** `submitted → under_review` (unchanged
  contract) now ALSO lazily materializes the first `candidate_stages` row at
  `sort_order = 1` of the org's default template (idempotent: the no-op
  already-`under_review` path also ensures the row exists). The student's
  pipeline life begins here.
- **`reject` is the cross-cutting terminal exit (unchanged contract).** It may be
  called from any stage; in addition to setting `applications.status = rejected` it
  **closes the open `candidate_stages` row** (`status = REJECTED`, `exited_at`
  set). No new endpoint, no duplicated logic.

**New transition graph (on `candidate_stages`, only while `status=under_review`):**

```
ADVANCE  active@order N  ──▶  active@order N+1   (current row -> PASSED/exited)
ROLLBACK active@order N  ──▶  active@order M<N   (current row -> ROLLED_BACK/exited)
REJECT   active@any      ──▶  (no new stage row)  current row -> REJECTED/exited
```

- **`POST /applications/{id}/advance`** — moves the active row to the next stage by
  `sort_order`. Preconditions: `applications.status = under_review`; an `ACTIVE`
  stage row exists; `required_action` satisfied (V1 `manual` → always true); not
  already at the last stage. Effect (one txn): current row `→ PASSED` + `exited_at`;
  append new `ACTIVE` row at `N+1`; bump `applications.version`; audit
  `application.stage_advanced`; notify per §4.
- **`POST /applications/{id}/rollback`** — moves the active row back to a prior
  stage of the **same template**. Body `{ "target_stage_id", "reason", "version?" }`.
  `reason` ≥ 20 chars (422 otherwise). Effect (one txn): current row `→ ROLLED_BACK`
  + `exited_at`; append new `ACTIVE` row at the target prior stage; bump `version`;
  audit `application.stage_rolled_back` (reason in audit metadata only).
  **Limit:** max 3 rollbacks per application (`BUSINESS_LOGIC` §3.5); the 4th →
  `409` with a coded "needs university-admin approval" marker (approval workflow
  deferred — V1 just blocks the 4th).

**Invariants (identical to the shipped subset — same machinery):**

- **Optimistic `version`** on `applications` is the concurrency guard. Unlike
  review/reject, advance/rollback are **NOT silently idempotent no-ops** (each is a
  distinct forward/back move). A replay whose `version` no longer matches → `409`.
  An optional `Idempotency-Key` dedupes a true network retry of the *same* move
  (store last-applied key on the active stage row) so an at-least-once retry never
  double-advances.
- **Illegal transition → `409`** (advance past last stage; advance/rollback when
  `status ∈ {rejected, withdrawn}`; rollback target not a prior stage of the same
  template; 4th rollback).
- **RBAC at the service layer**, reusing `decision_service._load_partner_application`
  (partner member of the job's owning org; cross-org / non-partner →
  `404`-not-`403`, not enumerable). Permission codes `recruitment:move_stage`
  (advance) and `recruitment:rollback_stage` (rollback) per PRD permission matrix;
  both default to partner members in V1.
- **Audit on every move** (`write_audit`, actor + from/to stage + reason in
  metadata), per `ARCHITECTURE` §4.1.

### 3. Data model + migration — `0012_pipeline_stage_engine`

**Migration needed? YES — one migration `0012_pipeline_stage_engine`** (upgrade +
downgrade). `applications.status` semantics are **unchanged** (no column change to
`applications` in the first slice). New tables (Postgres runtime + SQLite tests via
shared `JsonType`):

| Table | Key columns / FKs | Notes |
| --- | --- | --- |
| `pipeline_templates` | `id`, `org_id → organizations`, `name`, `is_default bool`, `is_system bool`, `created_at` | One `is_default=is_system=true` row seeded per org. `DATA_MODEL` §9 shape + `is_system`. |
| `pipeline_stages` | `id`, `template_id → pipeline_templates ON DELETE CASCADE`, `name`, `stage_type`, `sort_order smallint`, `required_action varchar default 'manual'`, `sla_hours int null`, `is_terminal bool`, `candidate_visible bool default true`, `automation_rules jsonb` | Unique `(template_id, sort_order)`. |
| `candidate_stages` | `id`, `application_id → applications ON DELETE CASCADE`, `stage_id → pipeline_stages`, `status varchar`, `entered_at`, `entered_by → users`, `exited_at null`, `exit_kind null`, `reason text null`, `idempotency_key varchar null`, `notes text null` | **Append-only stage history** (see below). |

**`candidate_stages` IS the append-only stage history** — we do **not** add a
separate `application_stage_history` table (would duplicate it). Rows are inserted
on entry and only ever closed once (`exited_at` + `exit_kind` + `status` set on
exit); no row is mutated again, none is deleted. `status ∈
{ACTIVE, PASSED, ROLLED_BACK, REJECTED}` per `ARCHITECTURE` §4.1; `exit_kind ∈
{advanced, rolled_back, rejected}`. **Invariant: at most one `ACTIVE` row per
application** — enforced by a Postgres partial unique index
`uq_candidate_stage_active (application_id) WHERE status='ACTIVE'`
(dialect-guarded; SQLite tests rely on the service-layer guard).

**Named-but-deferred tables** (created in their own later ADRs/migrations, FKs
stated now so the engine is forward-compatible): `interviews(application_id,
stage_id, …)`, `scorecards(interview_id, reviewer_id, …)`, `offers(application_id,
…)` — exactly as `DATA_MODEL` §9.

**Seeding:** migration `0012` data step inserts the system-default template + its 3
stages for every existing org; the service additionally **lazily ensures** the
default template exists on first `review`/`advance` (covers orgs created later
before the builder ships).

### 4. Anonymity & notifications

**Anonymity survives every stage move — unconditionally.** Stage transitions never
touch identity. The `application_reveal_requests` handshake remains the **only**
path to a student's identity; the partner pipeline board renders the redacted
snapshot (`apply_service._partner_view`) regardless of stage. Reuse that one view so
the redaction rule lives in exactly one place (mirrors `decision_service`).

**Student notifications (neutral, localized, §4n pattern — coded reason NEVER sent):**

| Move | Notify student? | Copy |
| --- | --- | --- |
| `advance` into a `candidate_visible=true` stage | yes | New type `recruitment.application_stage_advanced` — neutral localized "hồ sơ của bạn đã chuyển sang vòng tiếp theo / advanced to the next round". Stage *name* sent only if `candidate_visible`; otherwise generic "đang được xem xét". |
| `advance` into a `candidate_visible=false` stage | no | silent (PRD 7.1 per-stage visibility). |
| `rollback` | yes | New type `recruitment.application_under_rereview` — neutral "Đang xem xét lại hồ sơ / Your application is being re-reviewed" (PRD 7.2). The rollback `reason` is **partner-internal** (audit + partner projection), never sent. |
| `reject` | yes | unchanged shipped `recruitment.application_rejected`. |

- Student copy carries only the localized label + the job/company they already
  applied to — never internal stage `required_action`, rollback reason, or rejection
  code. Locale follows the applicant's preference. Email body MUST NOT contain CV
  text, scores, or private notes (`SECURITY_PRIVACY` §145).
- **Partner notifications (V1 minimal):** a feed row to the acting org on each move
  (`application.status_changed` outbox event). Full next-stage **assignee routing**
  (department/person fan-out, PRD 7.1) is deferred to the scorecards/interviews ADR
  (assignee model lands there).
- New catalog entries (vi+en), category `application_status`:
  `recruitment.application_stage_advanced`, `recruitment.application_under_rereview`.

### 5. Scope boundary

**THIS ADR (ADR-0004) covers:** the stage data model decision (configurable schema
+ seeded canonical default), tables `pipeline_templates` / `pipeline_stages` /
`candidate_stages`, migration `0012`, the `/advance` + `/rollback` endpoints with
`required_action = manual`, optimistic-version / illegal-transition-409 / RBAC-404 /
audit / anonymity / neutral-notification invariants, and the review→pipeline-entry
+ reject→stage-close integration with the shipped subset.

**Explicitly LATER ADRs (named so FKs are stable, design deferred):**

- **ADR-0005 — Scorecards & required-action enforcement:** `scorecards` table,
  `required_action ∈ {scorecard, score_threshold}` gating of `/advance`, parallel
  scorecards, anchoring-bias visibility (`BUSINESS_LOGIC` §3.1, §3.4).
- **ADR-0006 — Interview scheduling & calendar:** `interviews` table, self-scheduling
  (PRD 6.6), `meeting_url` encryption, business-hours SLA (`BUSINESS_LOGIC` §3.2).
- **ADR-0007 — Offers & approval:** `offers` table, salary/letter encryption, offer
  accept → `applications.status=hired`, career-outcome `trust_level=4`.
- **Deferred (own slices):** the per-job pipeline **template builder UI** + richer
  PRD stage-type taxonomy; the **auto-advance worker** (`BUSINESS_LOGIC` §3.3 — plugs
  into the ADR-0003 scheduler as a new idempotent job); **bulk advance/reject**
  (`BUSINESS_LOGIC` §3.6); the `proj_partner_pipeline` projection rebuild
  (data-engineer — must count from `candidate_stages`, see conflict #4).

### 6. First implementation slice (backend-first)

A small, self-contained slice a `backend-developer` can pick up next:

1. **Migration `0012_pipeline_stage_engine`** — create the 3 tables above (+ partial
   unique active-stage index, PG-guarded) with upgrade **and** downgrade; data step
   seeds the system-default template + 3 stages for existing orgs. Add ORM models to
   `recruitment/domain/models.py`.
2. **Domain** — new `recruitment/domain/pipeline.py` (or extend `lifecycle.py`):
   stage statuses + `exit_kind` vocab, `DEFAULT_STAGES` ladder, pure predicates
   `can_advance(current_order, max_order)`, `can_rollback(target_order, current_order,
   same_template)`, rollback-count guard. No I/O.
3. **Service** — new `recruitment/application/stage_service.py`:
   `advance_application_stage()` + `rollback_application_stage()`, reusing
   `decision_service._load_partner_application` (404 gate), `apply_service._partner_view`
   (anonymity), `write_audit`, and the neutral `_notify_student` pattern; a
   `default_pipeline_provider.ensure_org_default(session, org_id)` helper; hook
   `review_application` to materialize the first `candidate_stages` row and
   `reject_application` to close the open row.
4. **API** — `POST /applications/{id}/advance` and `/rollback` in
   `recruitment/api/router.py` (HTTP only); Pydantic schemas (advance: optional
   `version`; rollback: `target_stage_id` + `reason` min 20 + optional `version`);
   presenter returns the partner projection incl. current stage + position.
5. **Notifications** — add the two catalog/template entries (vi+en, neutral) +
   in-app feed types.
6. **Tests (SQLite, `tester-qa` gate):** advance happy path
   (`under_review`→stage1→stage2→offer); advance past last stage → `409`;
   advance/rollback when `rejected`/`withdrawn` → `409`; rollback appends `ACTIVE` +
   prior row `ROLLED_BACK`; rollback reason < 20 → `422`; 4th rollback → `409`;
   optimistic `version` conflict → `409`; idempotency-key replay does not
   double-advance; cross-org → `404`; **anonymity preserved** (partner view still
   redacted after moves); **neutral student notification** (no stage/reason leak,
   silent on `candidate_visible=false`); review materializes stage row; reject closes
   it; audit row per move.

**Frontend slice (follows, after the contract is green):** partner pipeline board
(kanban columns = template stages, cards = candidates read from `candidate_stages`
position); advance / rollback actions via modal (no `confirm()`), rollback reason
field (min 20, inline validation); neutral candidate-facing status on the student
application-detail timeline; honest empty/permission/conflict (409 stale) states.
Mark `API wired` → `browser verified` → `E2E verified` distinctly.

## Consequences

- **Positive:** the foundational stage engine ships small and doc-faithful;
  scorecards/interviews/offers attach to stable FKs without rework. The shipped
  review/reject subset is reused, not rewritten — `applications.status` stays the
  stable coarse outcome (projection-friendly), fine position is isolated in
  `candidate_stages`. Anonymity and the neutral-notification pattern are inherited
  unchanged. Auto-advance later plugs into the existing ADR-0003 scheduler.
- **Cost / limits:** one migration (`0012`); the template **builder** and the richer
  PRD stage-type taxonomy are deferred (V1 orgs all run the same 3-stage default —
  acceptable; product confirmed configurability is the *end state*, not a V1-blocking
  surface). `proj_partner_pipeline` must be reworked to read stage position from
  `candidate_stages` (data-engineer follow-up).
- **Reversibility:** the engine is additive; dropping `0012` and the two endpoints
  restores the Phase-1.5 surface exactly (review/reject untouched).

## Doc conflicts resolved (precedence: product > business > security > arch > API/data)

1. **`stage_type` taxonomy.** PRD MODULE 7 lists 9 rich types
   (`CV_REVIEW|WRITTEN_TEST|…|OFFER`); `DATA_MODEL` §9 lists 5
   (`screening|interview|assessment|offer|custom`). **Resolved:** V1 stores the
   coarse §9 set (the engine never branches on type); the PRD taxonomy is deferred to
   the template-builder ADR as UI labels mapping onto coarse types. Flagged: reconcile
   when the builder lands.
2. **`candidate_stages.status` column.** `DATA_MODEL` §9 omits it; `ARCHITECTURE` §4.1
   + `BUSINESS_LOGIC` §3.5 require `ACTIVE|PASSED|REJECTED|ROLLED_BACK`. **Resolved:**
   add the `status` (+ `exit_kind`, `entered_by`, `reason`) columns. Flag
   `DATA_MODEL` §9 `candidate_stages` as needing the status column added.
3. **`applications.status` value set.** `DATA_MODEL` §9 lists per-stage values
   (`screening|interview|offer`) on `applications.status`. **Resolved:**
   `applications.status` stays **coarse** (`submitted|under_review|rejected|withdrawn`
   +future `hired`); fine position = `candidate_stages`. Flag the §9
   `applications.status` comment as superseded by this ADR.
4. **`proj_partner_pipeline` projection.** `DATA_MODEL` line ~1342 counts by
   `applications.status IN ('interview','offer',…)`, which no longer carries fine
   position. **Resolved/flagged:** the projection must be recomputed from
   `candidate_stages` stage positions; assigned to data-engineer as a follow-up (not
   in this slice).
