# ADR-0006: Recruitment Interviews, Reviewer Assignees & Threshold Gating (Phase 2)

> **PARTIALLY SUPERSEDED (owner decision 2026-07-10):** every "anonymous
> application requires an accepted reveal to schedule an interview" /
> `409 reveal_required` precondition in this ADR is **retired**. Applications are
> always identified, so interviews schedule freely. All other invariants
> (assignee gating, `score_threshold`, `meeting_link` encryption, RBAC, audit)
> stand. This ADR needs a formal amendment; the note here is authoritative until
> then.

**Status:** Accepted (Proposed for implementation in the next backend slice)
**Date:** 2026-06-28
**Owner:** system-architect
**Related:** `docs/PRODUCT_REQUIREMENTS.md` MODULE 7 (§7.1 stage assignee/required-action,
§7.2 movement, §7.3 scorecard, §7.6 candidate view, §7.7 candidate detail), §6.6
(self-scheduling — deferred); `docs/BUSINESS_LOGIC.md` §3.1 (required-action
enforcement / `score_threshold`), §3.4 (parallel scorecard — DEPARTMENT/PERSON
assignee model + `threshold_pct`), §3.2 (interview/business-hours SLA — deferred);
`docs/DATA_MODEL.md` §9 (`interviews`, `scorecards`, `pipeline_stages`),
`docs/SECURITY_PRIVACY.md` (anonymity/reveal, `meeting_url` Fernet encryption,
PII-safe email), `docs/NOTIFICATIONS_COMMUNICATIONS_SPEC.md` (interview
schedule/reminder/cancel), `docs/API_CONTRACTS.md` (recruitment endpoints),
`docs/ARCHITECTURE.md` §4.1, `docs/EDGE_CASES_FAILURE_MODES.md`. Builds directly on
the **shipped** ADR-0004 stage engine and ADR-0005 scorecards
(`backend/app/modules/recruitment/application/{stage_service.py,scorecard_service.py,pipeline_board.py}`,
`domain/{pipeline.py,scorecard.py,models.py}`) and the ADR-0003 scheduler
(`backend/app/modules/automation/scheduler/jobs.py`) for reminders. This is the
ADR-0005 §7 / ADR-0004 §5 named-but-deferred seam: `scorecards.interview_id`, the
reviewer **assignee/threshold** model (so `required` becomes "all assigned
reviewers", not just ≥1), and `required_action=score_threshold`.

## Context

ADR-0004 shipped the configurable stage engine (`pipeline_templates` /
`pipeline_stages` / `candidate_stages`, one `ACTIVE` row = current position) with
all seeded stages `required_action=manual`. ADR-0005 shipped scorecards
(`scorecards` / `scorecard_scores`, migration `0013`): one editable scorecard per
`(application, stage, reviewer)`, a fixed `DEFAULT_CRITERIA` set, the 4-value
`recommendation`, the anchoring-bias visibility rule, and the
`required_action=scorecard` advance gate with a **fixed `required = 1`** because the
assignee model did not yet exist. Both ADRs explicitly deferred three things to
"ADR-0006":

1. `scorecards.interview_id` — a scorecard should be able to bind to the interview
   it evaluates (`DATA_MODEL` §9 declares the FK).
2. The **reviewer assignee model** so the scorecard gate can require **all assigned
   interviewers** (`BUSINESS_LOGIC` §3.4) rather than the V1 placeholder `≥ 1`.
3. **`required_action=score_threshold`** — `BUSINESS_LOGIC` §3.1: advance only when
   the **average** evaluator score reaches `stage.score_threshold` (`stage_service`
   currently fail-closes this action).

The shipped `scorecard_service.evaluate_advance_gate(session, application_id, stage)`
is the **single seam** through which both the GET aggregate and
`stage_service.advance_application_stage` ask "is the gate met?" — this ADR upgrades
that one function and adds the interview entities behind it.

Constraints that bound the decision (CLAUDE.md precedence: product > business >
security > architecture > API/data):

- **PRD §7.1 mandates per-stage assignees** (Mode = Department or Specific Person)
  and required actions; §7.3 scorecards per stage; §7.7 candidate detail shows
  interviews/scorecards. **Configurability is the documented end-state, not a
  V1-blocking surface** (same posture as ADR-0004/0005).
- **Scheduling an interview reveals candidate identity/contact to interviewers** —
  for an anonymous application this collides head-on with the reveal handshake
  (`SECURITY_PRIVACY`, `BUSINESS_LOGIC` §4.3): the student's identity is gated
  behind explicit consent and must not be silently bypassed. This is the key
  tension this ADR resolves.
- **`meeting_url` is Fernet-encrypted at rest, revealed only to attendees**
  (`DATA_MODEL` line ~1493); email/push bodies carry no CV text/scores/notes
  (`SECURITY_PRIVACY` §145).
- Local-first, small reversible first slice; RBAC at the service layer; no business
  logic in routers; anonymity invariants intact; notifications via the outbox +
  ADR-0003 scheduler, never synchronous SMTP.

## Decision

### 1. Interview model — ONE open interview per (application, stage) + N person-assignees

**Simplest V1 that satisfies the docs (favoring PRD §7.1 PERSON mode + §7.3
all-must-submit):** a single **open** interview per `(application, stage)` with an
explicit list of assigned interviewers, a scheduled time, a delivery **mode**, and a
location/link. Calendar/ICS sync, student self-scheduling + two-way confirm
(PRD §6.6), availability polling, panel-conflict detection, video integration, and
interview SLA (`BUSINESS_LOGIC` §3.2) are **deferred** (see §7).

- **The "round/type" is the pipeline stage itself** (`pipeline_stages.stage_type`,
  e.g. `interview`) plus a free `title` — the engine does NOT add a second
  interview-type taxonomy in V1 (mirrors ADR-0004's "engine never branches on
  `stage_type`"). The interview carries a **delivery `mode`** only:
  `onsite | online | phone`.
- **DEPARTMENT assignee mode** (PRD §7.1 / `BUSINESS_LOGIC` §3.4 "all members of a
  department") and **fractional `threshold_pct`** ("chỉ cần 2/3 phỏng vấn viên")
  are deferred. V1 ships **PERSON mode** (an explicit assignee list) with the
  documented **default `threshold_pct = 1.0` → all assigned interviewers must
  submit**. See conflict #5.

**Two tables (V1):**

- **`interviews`** — one row per scheduled interview, bound to `application_id` +
  `stage_id` (+ denormalized `org_id`, mirroring `scorecards.org_id`). **Editable
  in place** (reschedule mutates `scheduled_at`, status transitions, per-interview
  optimistic `version`), NOT append-only — its full history lives in audit.
- **`interview_assignees`** — the interviewer membership: one row per assigned
  partner user. Each assignee is **expected to submit a scorecard**; this set is
  what the upgraded gate counts.

`scorecards.interview_id` (nullable FK, added by this ADR) links a scorecard to the
interview it evaluates, when one exists.

### 2. Assignee + threshold gating — the upgraded `evaluate_advance_gate`

`scorecards.evaluate_advance_gate(session, application_id, stage)` stays the single
gate seam; this ADR makes it **assignee-aware and threshold-aware**. It resolves the
stage's **open interview** and its assignees, then:

- **`manual`** (the seeded V1 default): allowed, trivially. Unchanged.
- **`scorecard`:** let `A` = the set of assignee `user_id`s on the stage's open
  interview.
  - `required = len(A)` when `A` is non-empty (**all assigned interviewers must
    submit** — `threshold_pct = 1.0`); else `required = 1` (the ADR-0005 fallback,
    so a scorecard stage with no interview/assignees keeps working unchanged).
  - `submitted` = count of **submitted (non-withdrawn) scorecards** for
    `(application, stage)` whose `submitted_by_user_id ∈ A` (assignee scorecards
    only) when `A` is non-empty; else any submitted scorecard (ADR-0005 behavior).
  - `allowed = submitted >= required`.
- **`score_threshold`** (newly implemented): the assignee-count gate **first**, then
  the average-score gate.
  - Same `required`/`submitted` as `scorecard` (all assignees must be in before a
    meaningful average exists).
  - `avg_overall` = mean of `overall_score` across the counted submitted assignee
    scorecards; `threshold = stage.score_threshold` (new nullable column, §5).
  - `allowed = (submitted >= required) AND (avg_overall >= threshold)`.
- **Unknown action:** fail-closed (`IllegalApplicationTransitionError`), unchanged.

**Exact gate errors (raised by `stage_service.advance_application_stage`; all
`409`, partner-internal, NEVER leaked to the student):**

| Action | Failing condition | Error | `details` |
| --- | --- | --- | --- |
| `scorecard` / `score_threshold` | `submitted < required` | `409 scorecard_required` (ADR-0005 `ScorecardRequiredError`, now `required` may be > 1) | `{ reason:"scorecard_required", submitted, required }` |
| `score_threshold` | all submitted but `avg_overall < threshold` | `409 score_below_threshold` (**NEW** `ScoreBelowThresholdError(ConflictError)`) | `{ reason:"score_below_threshold", avg_overall, threshold }` |
| unknown | — | `409 illegal_transition` (unchanged) | `{ reason:"illegal_transition" }` |

`AdvanceGate` (the pure ADR-0005 dataclass) gains optional `avg_overall` /
`threshold` / `reason` fields so the single value object carries both failure modes.
The board/candidate-detail `evaluation` summary (ADR-0005 §6) is extended with
`required` (now assignee-derived), `avg_overall`, and `threshold` so a partner sees
precisely why a card is advance-blocked.

**`scorecards.interview_id` auto-link:** when `submit_scorecard` resolves the
candidate's current ACTIVE stage and an **open interview** exists for that stage, the
new/edited scorecard's `interview_id` is set to that interview (nullable otherwise).
A non-assignee partner member may still submit a scorecard (ADR-0005 RBAC unchanged),
but only **assignee** scorecards count toward `required`/`avg`.

### 3. Anonymity / reveal — scheduling REQUIRES an already-accepted reveal (no implicit bypass)

**The interview never auto-reveals identity. For an anonymous application, an
accepted reveal handshake is a hard precondition to schedule an interview.** The
reveal handshake (ADR-0004/0005 invariant, `BUSINESS_LOGIC` §4.3) stays the **only**
path to a student's identity, and the student's explicit consent is never silently
bypassed.

- Rejected alternative (b) "creating an interview triggers/implies a reveal" —
  **forbidden**: it would bypass the 72h student-consent handshake
  (`SECURITY_PRIVACY`, CLAUDE.md "must not silently bypass the student's consent").
- Rejected alternative (c) "schedule pre-reveal, keep identity redacted to
  interviewers" — incoherent: an onsite/phone/online interview cannot be conducted
  against a `UV-xxxx` handle.

**Rule (enforced in `interview_service.schedule_interview`, service layer, after the
partner-application 404 gate):**

```
if app.is_anonymous and app.reveal_approved_at is None:
    raise RevealRequiredError()        # 409, reason="reveal_required"
```

- **Non-anonymous applications** (identity already visible to the owning org)
  schedule freely — no reveal needed.
- **Anonymous + reveal accepted** (`reveal_approved_at` set): identity is already
  lawfully visible to the org, so interviewers may be assigned and shown the
  candidate's identity/contact. No new identity surface is created.
- **Error `409 reveal_required`** (NEW `RevealRequiredError(ConflictError)`,
  `details.reason="reveal_required"`) — distinct so the board renders "request and
  obtain the candidate's consent before scheduling an interview" and deep-links to
  the existing reveal request flow. It is partner-internal.

**The candidate is always notified about their OWN interview** regardless of
anonymity — the student knows their own identity, so an interview notification to the
student (date/time/mode/location/link) leaks nothing. What the reveal gates is the
**interviewers** seeing the **student's** identity; that path is unchanged.

### 4. Notifications

All via the notification **outbox** + in-app **feed** (no synchronous SMTP);
reminders via the ADR-0003 scheduler. New catalog entries (vi+en), category
`application_status` (student) / partner feed.

| Event | Recipient | Channel | Copy / payload |
| --- | --- | --- | --- |
| `recruitment.interview_scheduled` | **candidate** | email + in-app | Identity-safe (to the student about their own interview): date/time, `mode`, duration, location (onsite) or meeting link (online) or "the company will call you" (phone), the job/company they applied to. No assignee identities (PRD §7.6 "Không hiện: assignee"). |
| `recruitment.interview_rescheduled` | candidate | email + in-app | New date/time + the changed fields. |
| `recruitment.interview_cancelled` | candidate | email + in-app | Neutral cancellation notice. |
| `recruitment.interview_reminder` | candidate | email (+ push only if opted-in) | T-24h and T-1h before `scheduled_at` (PRD line 1486 "interview … reminder"; reuses the event-reminder cadence pattern). |
| `recruitment.interview_assigned` | **assigned interviewers** | in-app feed (+ email opt-in) | Partner-internal: candidate (identity visible — reveal precondition satisfied), stage, date/time, mode, link. Fired on assign + reschedule. |
| `recruitment.interview_reminder` (interviewer) | assigned interviewers | in-app feed | T-24h before `scheduled_at`. |

- **Meeting link** is included for the candidate (an attendee) and assignees
  (attendees) only; it is Fernet-encrypted at rest and decrypted only when rendering
  a notification/detail for an attendee (`DATA_MODEL` line ~1493). It never appears
  in any partner board glance or non-attendee surface.
- **Reminders use the ADR-0003 scheduler** — a new idempotent job
  `interview.reminder_sweep` (cadence every **5 min**) registered in
  `automation/scheduler/jobs.py` calls a new
  `interview_service.sweep_due_reminders(session, now)` that finds
  `status='scheduled'` interviews whose `scheduled_at` enters a reminder window and
  enqueues the student + assignee reminders. **Idempotent** via
  `dedupe_key=f"interview.reminder:{interview_id}:{window}"` (window ∈ {`24h`,`1h`}),
  flush-only (the scheduler owns the commit), exactly the `reveal.expire_sweep`
  pattern. `scheduled/rescheduled/cancelled` enqueue inline within the write txn.

### 5. Data model + migration — `0014_recruitment_interviews`

**Migration needed? YES — one migration `0014_recruitment_interviews`** (upgrade +
downgrade), revising `0013_recruitment_scorecards`. New tables + two additive
column adds (Postgres runtime + SQLite tests via shared `JsonType`/guards).

| Table / change | Key columns / FKs | Notes |
| --- | --- | --- |
| **`interviews`** (new) | `id`, `application_id → applications ON DELETE CASCADE`, `stage_id → pipeline_stages ON DELETE RESTRICT`, `org_id → organizations`, `title varchar(150) null`, `mode varchar(20)` (`onsite\|online\|phone`), `scheduled_at timestamptz`, `duration_minutes smallint default 60`, `location varchar(500) null` (onsite address), `meeting_link varchar(1000) null` (**Fernet-encrypted at rest**), `status varchar(20) default 'scheduled'`, `notes text null`, `created_by → users ON DELETE RESTRICT`, `version int default 1`, `created_at`, `updated_at` | **Editable in place** (not append-only). `status ∈ {scheduled, completed, cancelled, no_show, rescheduled}` — V1 actively uses `{scheduled, completed, cancelled, no_show}`; reschedule edits `scheduled_at` in place (status stays `scheduled`), so `rescheduled` is **reserved** for the future cancel-and-replace model. Index `(application_id, stage_id)`, `(org_id)`. Partial unique `uq_interview_open_per_stage (application_id, stage_id) WHERE status='scheduled'` (PG-guarded; SQLite tests rely on the service guard) → at most one OPEN interview per `(application, stage)`. |
| **`interview_assignees`** (new) | `id`, `interview_id → interviews ON DELETE CASCADE`, `user_id → users ON DELETE RESTRICT`, `created_at` | Unique `(interview_id, user_id)`. Index `(user_id)` for the "my interviews" read. Each assignee is expected to submit a scorecard; this set is the gate's `required` denominator. |
| **`scorecards.interview_id`** (alter) | `interview_id UUID NULL REFERENCES interviews(id) ON DELETE SET NULL` | The ADR-0005 §5 / `DATA_MODEL` §9 FK, added **nullable** (a scorecard may predate or exist without an interview). Auto-linked on submit when an open interview exists. `ON DELETE SET NULL` so deleting an interview never cascades away evaluation history. Index `(interview_id)`. |
| **`pipeline_stages.score_threshold`** (alter) | `score_threshold NUMERIC(2,1) NULL` | `BUSINESS_LOGIC` §3.1 references `stage.score_threshold`; it was absent from `0012`. Added nullable; meaningful only when `required_action='score_threshold'`. See conflict #4. |

- **No seed-data step** — there are no interviews until a partner schedules one;
  seeded stages stay `manual`, so the upgraded gate is dormant until a stage's
  `required_action` is set to `scorecard`/`score_threshold` (tests set it directly).
- ORM models in `recruitment/domain/models.py` (`Interview`, `InterviewAssignee`);
  add `interview_id` to the existing `Scorecard` model; add `score_threshold` to
  `PipelineStage`.

### 6. API surface

All under the existing recruitment router; HTTP-only routers, RBAC + transactions in
`interview_service`. New permission codes `recruitment:schedule_interview` and
`recruitment:manage_interview` (default to partner members in V1, like
`recruitment:move_stage`). Cross-org / non-partner → `404` (reusing
`decision_service._load_partner_application`).

| Endpoint | Method | Authz / body | Behavior |
| --- | --- | --- | --- |
| `/applications/{id}/interviews` | POST | partner member (`schedule_interview`). Body `{ mode, scheduled_at, duration_minutes?, location?, meeting_link?, assignee_ids: [uuid], title?, notes? }` | Schedule the candidate's interview for their **current ACTIVE stage**. **Anonymous + no accepted reveal → `409 reveal_required` (§3).** App not `under_review` / no ACTIVE stage → `409 illegal_transition`. A second OPEN interview for the stage → `409` (`reason:"interview_exists"`). `assignee_ids` must be members of the job's org (else `422`); `online` requires `meeting_link`, `onsite` requires `location` (else `422`). Encrypts `meeting_link`. Audited (`application.interview_scheduled`). Notifies candidate + assignees (§4). Returns the partner interview view. |
| `/applications/{id}/interviews` | GET | partner member (`manage_interview`) | List the application's interviews (partner-internal): `[{ id, stage_id, title, mode, scheduled_at, duration_minutes, location, meeting_link (attendee-only), status, assignees:[{user_id, name}], evaluation:{submitted, required, avg_overall, threshold, gate_met} }]`. |
| `/applications/{id}/interviews/{interview_id}` | PATCH | partner member (`manage_interview`) + `version?` | Reschedule / edit (`scheduled_at`, `mode`, `location`, `meeting_link`, `title`, `notes`). Optimistic `version` (stale → `409`). Audited (`application.interview_rescheduled`). Re-notifies candidate + assignees, re-arms reminders. |
| `/applications/{id}/interviews/{interview_id}/assignees` | PUT | partner member (`manage_interview`) | Replace the assignee set `{ assignee_ids:[uuid] }` (members of the org). Adds/removes `interview_assignees`. Audited (`application.interview_assignees_changed`). Notifies newly-assigned interviewers. **Changes the gate `required`.** |
| `/applications/{id}/interviews/{interview_id}/cancel` | POST | partner member (`manage_interview`) + `version?` | `status → cancelled`. Audited (`application.interview_cancelled`). Notifies candidate. Frees the partial-unique open slot. |
| `/applications/{id}/interviews/{interview_id}/complete` | POST | partner member (`manage_interview`) + `version?`. Body `{ outcome: "completed"\|"no_show" }` | `status → completed`/`no_show`. Audited (`application.interview_completed` / `…_no_show`). |

- **Board / candidate-detail surfacing:** `stage_service._pipeline_block` (current
  stage only) gains a partner-only `interview` block
  `{ id, mode, scheduled_at, status, assignee_count }` alongside the extended
  `evaluation` summary, so a partner sees the scheduled interview + whether the
  card is advance-blocked. `meeting_link` is **NOT** on the board glance (attendee
  surfaces only). **Student projection / notifications:** the student application
  detail surfaces only **their own** upcoming interview
  `{ scheduled_at, mode, location_or_link, status }` — **never** assignee identities,
  scorecards, the gate, or any other candidate's data.

### 7. Scope boundary + first implementation slice

**THIS ADR (ADR-0006) covers:** `interviews` + `interview_assignees` tables, the
nullable `scorecards.interview_id` FK, the `pipeline_stages.score_threshold` column
(migration `0014`); PERSON-mode assignees with `threshold_pct=1.0`
("all assigned interviewers submit"); the upgraded `evaluate_advance_gate`
(assignee-derived `required` for `scorecard`; new `score_threshold` action with the
`avg ≥ threshold` gate) and the new `409 score_below_threshold` /
`409 reveal_required` errors; the reveal precondition for scheduling anonymous
interviews; schedule / reschedule / cancel / complete / assignees / list endpoints;
interview notifications + the ADR-0003 `interview.reminder_sweep` job; the partner-only
board interview + extended evaluation summary; audit on every write.

**Explicitly LATER (named so FKs/behaviors stay stable, design deferred):**

- **Self-scheduling (PRD §6.6)** — partner availability windows, student slot pick,
  two-way confirm (`student_confirmed_at`), Google/Outlook **ICS** invite. Its own
  ADR (availability + calendar adapter).
- **DEPARTMENT assignee mode + fractional `threshold_pct`** (`BUSINESS_LOGIC` §3.4
  "2/3 interviewers") — V1 is PERSON mode @ 1.0; the gate already reads `required`
  from the assignee set, so a department resolver + a `threshold_pct` column drop in
  without a gate rewrite.
- **Interview SLA / business-hours** (`BUSINESS_LOGIC` §3.2) and **video
  integration** (Zoom/Meet provisioning) — later slices.
- **AI scorecard-from-notes** (PRD §7.3 "AI suggest scores từ interview notes") →
  ai-engineer / `AI_PRODUCT_SPEC` ADR; advisory, human-confirm, no provider leak.
- **Auto-advance worker** when `score_threshold`/`scorecard` met + `auto_advance=true`
  (`BUSINESS_LOGIC` §3.3) → ADR-0003 scheduler job on top of this gate.
- Offers → **ADR-0007**.

**First implementation slice (backend-first) — for `backend-developer`:**

1. **Migration `0014_recruitment_interviews`** — create `interviews` +
   `interview_assignees` (+ the PG-guarded partial-unique open-interview index and
   the `(user_id)` index); `ALTER scorecards ADD interview_id NULL` (FK
   `ON DELETE SET NULL`, indexed); `ALTER pipeline_stages ADD score_threshold
   NUMERIC(2,1) NULL`. Upgrade **and** downgrade. Add `Interview` /
   `InterviewAssignee` ORM models; add `interview_id` to `Scorecard`,
   `score_threshold` to `PipelineStage`.
2. **Domain** — new `recruitment/domain/interview.py`: `MODES = {onsite, online,
   phone}`, `INTERVIEW_STATUSES`, the `ACTION_SCORE_THRESHOLD = "score_threshold"`
   token, pure `avg_threshold_met(avg, threshold)`, and an extended `AdvanceGate`
   (optional `avg_overall`/`threshold`/`reason`). Extend
   `scorecard.required_for_action` to know `score_threshold`. No I/O.
3. **Service** — new `recruitment/application/interview_service.py`:
   `schedule_interview()` (reveal precondition + open-interview uniqueness + encrypt
   link + assignee validation + audit + notify), `reschedule_interview()`,
   `set_assignees()`, `cancel_interview()`, `complete_interview()`,
   `list_interviews()`, and `sweep_due_reminders(session, now)`. Reuse
   `decision_service._load_partner_application` (404), `stage_service._active_stage`,
   `write_audit`, the outbox/feed enqueue helpers.
4. **Upgrade the gate** — in `scorecard_service.evaluate_advance_gate` (+ a small
   `_stage_assignees` / `_assignee_submitted_count` helper), make `required`
   assignee-derived and add the `score_threshold` branch returning the extended
   `AdvanceGate`. In `stage_service.advance_application_stage`, raise
   `ScoreBelowThresholdError` when the threshold branch fails (keep the existing
   `ScorecardRequiredError` for the count branch). Auto-link `interview_id` in
   `submit_scorecard`. Extend `_pipeline_block`'s `evaluation` + add the `interview`
   block (current stage only).
5. **Errors / API** — add `ScoreBelowThresholdError` (`reason="score_below_threshold"`,
   `{avg_overall, threshold}`) and `RevealRequiredError` (`reason="reveal_required"`)
   to `recruitment/application/errors.py`; add the six interview endpoints + Pydantic
   schemas (HTTP only); presenter for the partner interview view (attendee-gated
   `meeting_link`) and the student own-interview block.
6. **Notifications** — add the catalog/template entries (vi+en, identity-safe) +
   in-app feed types; register `interview.reminder_sweep` (5 min) in
   `automation/scheduler/jobs.py`.
7. **Tests (SQLite, `tester-qa` gate):** schedule happy path (non-anonymous);
   **anonymous + no accepted reveal → `409 reveal_required`**; anonymous **+**
   accepted reveal → schedules; second open interview per stage → `409`; reschedule
   bumps version + re-notifies (stale version → `409`); cancel frees the slot;
   complete/no_show transitions; assignee set drives the gate — `scorecard` stage
   with 2 assignees needs **2** submitted assignee scorecards (1 submitted → `409
   scorecard_required {submitted:1, required:2}`); a non-assignee scorecard does NOT
   count toward `required`; `score_threshold` stage: all submitted but `avg <
   threshold` → `409 score_below_threshold {avg_overall, threshold}`, `avg ≥
   threshold` → advances; `interview_id` auto-linked on submit; reminder sweep
   enqueues exactly once per window (dedupe), idempotent on re-run; cross-org
   schedule/list → `404`; invalid mode/missing link/location → `422`; **anonymity** —
   student projection + notifications carry no assignee identity / scorecard / gate;
   **PII-safe** — `meeting_link` encrypted at rest, absent from the board glance and
   non-attendee surfaces; audit row per write.

**Frontend slice (follows, after the contract is green) — `frontend-developer`:**
partner candidate-detail "Schedule interview" drawer (mode, datetime, duration,
location/link, assignee multi-select; no `confirm()`); a "request reveal first"
blocked state on `409 reveal_required` deep-linking the reveal flow; the
interview/assignee status + extended `evaluation` ("2/3 scorecards", "avg 3.4/4.0")
on the board card and detail panel; the student application-timeline **own-interview**
card (date/mode/location/link, no assignees); honest empty/permission/conflict (409
stale) states. Mark `API wired` → `browser verified` → `E2E verified` distinctly.

## Consequences

- **Positive:** interviews + the assignee/threshold gate ship small on stable
  ADR-0004/0005 FKs; the single `evaluate_advance_gate` seam absorbs the upgrade so
  the `manual` and `scorecard`-without-interview paths are untouched (backward
  compatible); the reveal precondition keeps the handshake the **only** identity
  path — no consent bypass; reminders reuse the ADR-0003 scheduler with the proven
  sweep+dedupe pattern; `interview_id`/`score_threshold`/assignee tables make
  DEPARTMENT mode, fractional thresholds, calendar sync, SLA, and AI assist additive.
- **Cost / limits:** V1 is PERSON-mode @ `threshold_pct=1.0` (no department fan-out,
  no partial threshold); one open interview per `(application, stage)` (no panel
  rounds / multiple parallel interviews per stage); no calendar/ICS, no
  self-scheduling, no interview SLA. All are documented end-states, not V1 blockers.
- **Reversibility:** additive — dropping `0014`, the interview endpoints, the
  scheduler job, and reverting `evaluate_advance_gate` to the ADR-0005
  `required=1` / fail-closed-`score_threshold` restores the ADR-0005 surface exactly.
  Seeded stages stay `manual`, so nothing breaks.

## Doc conflicts resolved (precedence: product > business > security > arch > API/data)

1. **`interviews.interviewers UUID[]`.** `DATA_MODEL` §9 stores assignees as a
   Postgres array. **Resolved:** normalize into the `interview_assignees` join table
   (queryable membership, unique constraint, `(user_id)` index for "my interviews",
   no array ops on SQLite tests). **Flag `DATA_MODEL` §9 `interviews`** to replace
   `interviewers UUID[]` with the join table.
2. **`interviews.interview_type {phone|video|onsite|technical}`.** `DATA_MODEL` §9
   conflates delivery channel and round descriptor. **Resolved:** V1 stores a
   delivery `mode {onsite, online, phone}` only (`video → online`); the round
   descriptor is the `pipeline_stages.stage_type` (the engine never adds a second
   interview-type taxonomy, mirroring ADR-0004). **Flag `DATA_MODEL` §9** to rename
   `interview_type` → `mode` with the 3-value set.
3. **`scorecards.interview_id NOT NULL`.** `DATA_MODEL` §9 makes it non-null; ADR-0005
   bound a scorecard to `application_id` + `stage_id`. **Resolved:** added
   **nullable** with `ON DELETE SET NULL`, auto-linked when an open interview exists.
   **Flag `DATA_MODEL` §9** `scorecards.interview_id` as nullable (completes the
   ADR-0005 §conflict-1 flag).
4. **`stage.score_threshold` has no column.** `BUSINESS_LOGIC` §3.1 reads
   `stage.score_threshold` but `0012`/`DATA_MODEL` §9 `pipeline_stages` lack it
   (only `automation_rules JSONB`). **Resolved:** add an explicit
   `score_threshold NUMERIC(2,1) NULL` column (typed, indexable, not buried in
   JSONB). **Flag `DATA_MODEL` §9 `pipeline_stages`** to add `score_threshold`.
5. **DEPARTMENT assignee mode + fractional `threshold_pct`.** `BUSINESS_LOGIC` §3.4 /
   PRD §7.1 define DEPARTMENT mode and "2/3 interviewers". **Resolved:** V1 ships
   PERSON mode @ `threshold_pct = 1.0` (all assigned submit); the gate already reads
   `required` from the assignee set, so DEPARTMENT resolution + a `threshold_pct`
   column are additive. **Flag `BUSINESS_LOGIC` §3.4** as partially implemented
   (DEPARTMENT mode + fractional threshold deferred).
6. **Self-scheduling + calendar invite (PRD §6.6) and `interviews.student_confirmed_at`
   (`DATA_MODEL` §9).** **Resolved:** V1 is partner-scheduled (no two-way confirm /
   ICS); `student_confirmed_at` is **not** added until the self-scheduling ADR.
   **Flag PRD §6.6 / `DATA_MODEL` §9** as deferred.
</content>
</invoke>
