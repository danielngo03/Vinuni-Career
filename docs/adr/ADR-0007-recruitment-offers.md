# ADR-0007: Recruitment Offers — Approval, Send, Accept/Decline & the `hired` Outcome (Phase 2)

> **PARTIALLY SUPERSEDED (owner decision 2026-07-10):** the "accepted reveal
> handshake is a hard precondition to send an offer" / `409 reveal_required`
> rule is **retired**. Applications are always identified, so offers send freely.
> The partner approval-before-send gate, salary encryption, RBAC, and audit
> invariants stand. This ADR needs a formal amendment; the note here is
> authoritative until then.

**Status:** Accepted (Proposed for implementation in the next backend slice)
**Date:** 2026-06-28
**Owner:** system-architect
**Related:** `docs/PRODUCT_REQUIREMENTS.md` MODULE 7 (§11.4 Offer Management,
role/permission matrix "Offers | view, create, send, withdraw, counter"), §6
(student offers / comparison — deferred), line 1466 ("Offer accepted → placement
record. University confirm sau khi student start việc"); `docs/BUSINESS_LOGIC.md`
§3.3 ("Current stage là final stage → cần manual decision (offer/reject)"), §7.1
(review eligibility uses OFFER/ACCEPTED), §13 (career outcomes, LEVEL 4 = estimated
from application → offer accepted); `docs/DATA_MODEL.md` §9 (`offers`,
`applications.status`, `proj_partner_pipeline` `hired_count`, §17 `salary_amount`
Fernet, §27 `career_outcome_records`); `docs/SECURITY_PRIVACY.md` / `DATA_MODEL`
§17 (`salary_amount` Fernet — recruiter + student only); `docs/API_CONTRACTS.md`
(`/offers`, `/offers/{id}`, `/offers/{id}/respond`; `offer.*` event taxonomy);
`docs/NOTIFICATIONS_COMMUNICATIONS_SPEC.md` (offer received / offer response);
`docs/ARCHITECTURE.md` §4.1; `docs/EDGE_CASES_FAILURE_MODES.md`. Builds directly on
the **shipped** ADR-0004 stage engine, ADR-0005 scorecards, ADR-0006 interviews
(`backend/app/modules/recruitment/application/{stage_service.py,decision_service.py,interview_service.py,scorecard_service.py}`,
`domain/{lifecycle.py,pipeline.py,interview.py,models.py}`) and the ADR-0003
scheduler (`backend/app/modules/automation/scheduler/jobs.py`). This is the final
Phase-2 recruiting sub-layer: the `offers` table named-but-deferred by ADR-0004 §5
("ADR-0007 — Offers & approval: `offers` table … offer accept →
`applications.status=hired`, career-outcome `trust_level=4`").

## Context

The seeded canonical ladder (ADR-0004 §1) ends with an **Offer** stage
(`sort_order = 3`, `stage_type='offer'`, the template's last stage). ADR-0004 §1
left `applications.status` as the **coarse** outcome
(`submitted | under_review | rejected | withdrawn`) and recorded that **`hired`
arrives with the offers ADR** (`lifecycle.py` docstring; ADR-0004 conflict #3;
`DATA_MODEL` §9 `proj_partner_pipeline` already counts `hired_count`). The offer is
the **terminal POSITIVE outcome** — the only path to `hired` — exactly as `reject`
is the terminal negative one. Nothing creates offers today.

PRD §11.4 mandates: create an offer (position, gross/net salary, bonus, benefits,
start date, deadline); an internal approval before it reaches the candidate
(the role matrix separates `create`/`send`); the student Accept / Decline; and
"Offer accepted → trigger placement record tự động". Counter-offer,
request-extension, and offer-letter-template autofill are also listed there but are
heavier and deferred (§9).

Constraints that bound the decision (CLAUDE.md precedence: product > business >
security > architecture > API/data):

- **An offer reveals identity.** You cannot hire a `UV-xxxx` handle: a real offer
  carries the candidate's name/start-date and the student must see who is hiring
  them. As with ADR-0006 interviews, the reveal handshake (`SECURITY_PRIVACY`,
  `BUSINESS_LOGIC` §4.3) must stay the **only** identity path and must not be
  silently bypassed.
- **`salary_amount` is Fernet-encrypted at rest, "recruiter + student only"**
  (`DATA_MODEL` §17). Notification/email bodies carry **no** salary figure (same
  PII-safe-email rule that keeps CV text/scores/meeting links out of email bodies,
  `SECURITY_PRIVACY` §145) — the student opens the platform to see comp.
- **V1 payment default is manual/bank-transfer** (CLAUDE.md). Offers carry a comp
  *summary*; they do **not** trigger any payment, payroll, or reconciliation flow.
- **University confirms placement only AFTER the student starts** (PRD line 1466);
  the university does **not** approve individual offers. Approval is an
  **internal partner** gate.
- Local-first, small reversible additive slice; RBAC at the service layer; no
  business logic in routers; anonymity invariants intact; notifications via the
  outbox + ADR-0003 scheduler, never synchronous SMTP; audit on every write;
  optimistic `version` for concurrency; cross-org → `404`-not-`403`.

## Decision

### 1. Offer model + lifecycle — one LIVE offer per application, an 8-state machine

**One offer entity (`offers`) per application, with at most one LIVE offer at a
time.** The "round" is the pipeline stage (the Offer stage); the offer carries comp
+ deadline + an approval/response state machine.

**States (the full set; `applications.status` is NOT one of them — see §4):**

```
draft ──submit──▶ pending_approval ──approve──▶ approved ──send──▶ sent
  ▲                     │                                            │
  └──── reject ─────────┘ (approver sends back to draft)             ├─ accept  ▶ accepted   (TERMINAL +)
                                                                     ├─ decline ▶ declined   (TERMINAL −)
                                                                     └─ expire  ▶ expired    (TERMINAL)

rescind (partner) from { draft | pending_approval | approved | sent } ▶ rescinded (TERMINAL)
```

- **Non-terminal / LIVE:** `draft`, `pending_approval`, `approved`, `sent`.
- **Terminal:** `accepted`, `declined`, `expired`, `rescinded`.
- **Editable only while `draft`** (and after an approver `reject` bounces it back to
  `draft`): comp fields, start date, expiry, terms/notes are mutable in place under
  optimistic `version`. From `pending_approval` onward the **content is frozen**;
  only **status transitions** mutate the row (`approved_by`/`approved_at`,
  `sent_at`, `student_response_at`, `decline_reason`). This mirrors the
  ADR-0006 interview posture (editable-in-place, audit holds full history) but
  freezes content at submit so the candidate never sees post-send comp drift; the
  approval audit and notifications are the immutable record. We do **not** add a
  separate `offer_versions` table in V1 (audit covers it).
- **Comp is kept simple (CLAUDE.md / task): structured-minimal, no payment
  gateway.** Discrete `salary_amount` (Fernet-encrypted ciphertext), `salary_currency`
  (default `VND`), `salary_period` (default `monthly`), plus free-text
  `benefits_summary` and `terms_notes`. Gross/net is expressed in the summary text in
  V1 (no separate net column).
- **FKs:** `application_id` (the candidate), `stage_id` (the Offer stage the offer was
  raised at — mirrors `scorecards`/`interviews`), `org_id` (denormalized, org-scoped
  reads), `created_by`, `approved_by` (nullable until approved).

### 2. Approval flow — internal partner gate, manual per V1

**An offer cannot reach the student until an internal partner approver has approved
it.** Two distinct permission codes split create-vs-approve-vs-send (PRD role
matrix already separates `create`/`send`):

| Action | Permission | Transition |
| --- | --- | --- |
| create / edit draft / submit-for-approval | `recruitment:create_offer` | (insert) / `draft` (edit) / `draft → pending_approval` |
| approve / reject-back | `recruitment:approve_offer` | `pending_approval → approved` / `pending_approval → draft` |
| send | `recruitment:send_offer` | `approved → sent` (reveal precondition, §5) |
| rescind | `recruitment:withdraw_offer` | `{draft,pending_approval,approved,sent} → rescinded` |

- **The approval GATE is `send` requires `status='approved'`.** `send` from any other
  state → `409 offer_not_approved`. This is the structural control; orgs configure
  *which* role holds `approve_offer`/`send_offer` (RBAC is org-admin-defined, PRD
  §RBAC). **V1 does NOT enforce separation-of-duties** (the creator may also approve
  if they hold `approve_offer`); both `created_by` and `approved_by` are recorded and
  audited so SoD can be enforced later without a schema change. Flagged in §"Doc
  conflicts" (PRD matrix lacks an explicit `approve` action).
- **No university approval of individual offers** (PRD line 1466 — university confirms
  placement post-start, not the offer). Out of scope here; the university
  career-outcome confirmation (`trust_level=1`) is a later data-engineer flow.
- All four actions: partner-of-org RBAC via `decision_service._load_partner_application`
  (cross-org/non-partner → `404`), optimistic `version`, audit row per write.

### 3. Candidate accept / decline — the student-facing action

**The student responds via `POST /offers/{id}/respond`** (the exact
`API_CONTRACTS` contract): body `{ decision: "accepted" | "declined", notes?,
idempotency_key }`. Only the **applicant** may respond, only to a **`sent`** offer.

- **`accepted`:** offer `sent → accepted`; `student_response_at` set; in the **same
  transaction** `applications.status → hired` (§4), the open `candidate_stages` row
  (at the Offer stage) is **closed as PASSED** (`exit_kind='hired'`, a new exit kind),
  and a **career-outcome seam** fires (§4). Idempotent: re-respond `accepted` on an
  already-`accepted` offer is a no-op (no duplicate placement / notification).
- **`declined`:** offer `sent → declined`; `decline_reason` stored from `notes`
  (partner-internal). **The application is NOT auto-rejected** — it stays
  `under_review` at the Offer stage so the partner may rescind+re-offer or `reject`
  explicitly. (Avoids a destructive cascade the student didn't ask for.)
- **Expiry — lazy + scheduler sweep:** every read/respond first checks
  `now ≥ expiry_date AND status='sent' → expired` (lazy, so a stale row is never
  acted on); the authoritative flip + the candidate/partner notification are done by
  a new idempotent ADR-0003 job **`offer.expire_sweep`** (5 min) that also fires the
  **T-24h expiring reminder** to the candidate (§6). Responding to an expired offer →
  `409 offer_not_actionable`.
- **`counter` / request-extension (PRD §11.4) deferred** (§9). The `respond` schema
  accepts only `accepted|declined` in V1; a `409`/`422` on anything else.

### 4. Coarse-status interaction — `hired` becomes the 5th coarse status

**Decision: YES — accept moves `applications.status` to a new terminal coarse
`hired`.** This was pre-committed by ADR-0004 (§1, conflict #3), the `lifecycle.py`
docstring, and `DATA_MODEL` §9 (`proj_partner_pipeline` already emits `hired_count`).
Tracking placement only on the offer would split the outcome truth across two tables
and break the existing projection contract.

- `hired` is **terminal and inactive** (like `rejected`/`withdrawn`): NOT in
  `ACTIVE_STATUSES`, NOT `WITHDRAWABLE`. It is the positive sibling of `rejected`.
- **Migration impact on `applications.status`: NONE at the DDL level.** The column is
  already `VARCHAR(30)`; widening the value-set is a **domain change only** —
  `lifecycle.STATUSES` gains `HIRED`, a localized label is added (vi "Đã được tuyển" /
  en "Hired"), and `decision_service`/`stage_service` already commit `applications`
  rows the same way. `proj_partner_pipeline` already counts `hired` (no projection
  rewrite). The board's outcome summary (rejected/withdrawn) gains a `hired` bucket
  it already has a column for.
- Fine position: the Offer-stage `candidate_stages` row closes `PASSED` with
  `exit_kind='hired'` (new vocab value in `pipeline.py`); no new stage row is appended
  (Offer is the last stage).
- **Career-outcome seam (trust_level=4):** `API_CONTRACTS` requires accept to create a
  `career_outcome_records` row at `trust_level=4` (`source='system_estimate'`).
  Because the career-outcomes module may not be shipped yet, accept **emits an outbox
  domain event `offer.accepted` + an audit `application.hired`** carrying
  `{application_id, org_id, employer_org_id, position_title, start_date}` (NO salary in
  the event payload); the career-outcomes materializer (data-engineer, when that module
  lands) consumes it idempotently. **Accept never blocks on that module.** If the table
  already exists at implementation time, the service inserts the row directly behind
  the same seam.

### 5. Anonymity / reveal — SENDING an offer requires an already-accepted reveal

**An offer becomes visible to the student at `send`. For an anonymous application,
an accepted reveal handshake is a hard precondition to `send` an offer** — identical
posture to ADR-0006 §3 (interview scheduling). Drafting/approval may happen while the
application is still anonymous (internal), but the offer cannot reach the candidate —
and the candidate's identity cannot be put on a real offer — without consent.

```
# in offer_service.send_offer(), after the partner-app 404 gate + status='approved' check:
if app.is_anonymous and app.reveal_approved_at is None:
    raise RevealRequiredError()        # 409, reason="reveal_required" (reuses ADR-0006 error)
```

- Non-anonymous (or reveal already accepted) → sends freely; no new identity surface
  is created (identity is already lawfully visible to the org).
- In practice the Offer stage follows interviews where reveal already happened; this
  is a defensive backstop, reusing the existing `RevealRequiredError` so the board
  renders the same "obtain consent first" blocked state + reveal deep-link.
- **The student's own offer copy is identity-safe to them** — it is *their* offer
  (their name, the hiring company they applied to). What the reveal gates is the
  **partner** seeing the **student's** identity; that path is unchanged.

### 6. Notifications

All via the outbox + in-app feed (no synchronous SMTP); the expiry/expiring sweeps
via the ADR-0003 scheduler. New catalog entries (vi+en), category
`application_status` (student) / partner feed. **No salary figure in any body**
(`DATA_MODEL` §17) — the student opens the platform to view comp.

| Event | Recipient | Channel | Copy / payload |
| --- | --- | --- | --- |
| `recruitment.offer_received` | **candidate** | email + in-app | "You have an offer from {company} for {position} — respond by {expiry}. View it on the platform." No salary. |
| `recruitment.offer_expiring` | candidate | email (+ push if opted-in) | T-24h before `expiry_date`, only while `status='sent'`. |
| `recruitment.offer_expired` | candidate + partner feed | in-app (candidate also email) | Neutral "the offer has expired". |
| `recruitment.offer_accepted` | **partner feed** | in-app | Partner-internal: candidate hired, position, start date. |
| `recruitment.offer_declined` | partner feed | in-app | Partner-internal; `decline_reason` shown to partner only. |
| `recruitment.offer_rescinded` | candidate | email + in-app | Neutral withdrawal notice (only if it was already `sent`). |

- **`offer.expire_sweep` (5 min, ADR-0003):** a new idempotent job in
  `automation/scheduler/jobs.py` → `offer_service.sweep_offers(session, now)` finds
  `status='sent'` offers, flips those past `expiry_date` to `expired` (enqueue
  expired notices) and enqueues the T-24h `offer_expiring` reminder for those entering
  the window. Idempotent via `dedupe_key=f"offer.expiring:{offer_id}"` /
  `f"offer.expired:{offer_id}"`; flush-only (scheduler owns the commit) — exactly the
  `interview.reminder_sweep` / `reveal.expire_sweep` pattern. `sent`/`accepted`/
  `declined`/`rescinded` enqueue inline within their write txn.

### 7. Data model + migration — `0015_recruitment_offers`

**One migration `0015_recruitment_offers`** (upgrade + downgrade), revising
`0014_recruitment_interviews`. One new table; **no DDL on `applications`** (the
`hired` value is a domain widening, §4). Postgres runtime + SQLite tests via shared
`JsonType`/dialect guards.

| Table / change | Key columns / FKs | Notes |
| --- | --- | --- |
| **`offers`** (new) | `id`; `application_id → applications ON DELETE CASCADE`; `stage_id → pipeline_stages ON DELETE RESTRICT`; `org_id → organizations ON DELETE RESTRICT`; `position_title varchar(255)`; `department varchar(200) null`; `start_date date null`; `salary_amount varchar(255) null` (**Fernet ciphertext at rest**); `salary_currency varchar(5) default 'VND'`; `salary_period varchar(20) default 'monthly'`; `benefits_summary text null`; `terms_notes text null`; `expiry_date timestamptz`; `status varchar(20) default 'draft'`; `created_by → users ON DELETE RESTRICT`; `approved_by → users ON DELETE SET NULL null`; `approved_at timestamptz null`; `sent_at timestamptz null`; `student_response_at timestamptz null`; `decline_reason text null`; `version int default 1`; `created_at`; `updated_at` | `status ∈ {draft, pending_approval, approved, sent, accepted, declined, expired, rescinded}`. Editable-in-place while `draft`; content frozen at submit (§1). Index `(application_id)`, `(org_id, status)`, `(stage_id)`. **Partial unique `uq_offer_live_per_application (application_id) WHERE status IN ('draft','pending_approval','approved','sent')`** (PG-guarded; SQLite tests rely on the service guard) → at most one LIVE offer per application. |
| **`applications.status` value-set** (NO DDL) | adds `hired` | Column already `VARCHAR(30)`; widening is domain-only (`lifecycle.STATUSES` + label). `proj_partner_pipeline` already counts it. |
| **`candidate_stages.exit_kind`** (NO DDL) | adds `'hired'` | Already `VARCHAR(20)` nullable; new domain vocab value in `pipeline.py`. |

- **Salary encryption:** a new `recruitment/infrastructure/offer_salary_crypto.py`
  mirroring `meeting_link_crypto.py` (same `TOTP_ENCRYPTION_KEY` sourcing, distinct
  purpose label, legacy-tolerant decrypt). `salary_amount` is stored as the **Fernet
  ciphertext string** and decrypted only when rendering a **recruiter or the owning
  student** surface — never logged, never in a notification body, never in an
  analytics/event payload.
- **No seed step** — there are no offers until a partner creates one.
- ORM model `Offer` in `recruitment/domain/models.py` (mirrors `Interview`'s shape).

### 8. API surface

All HTTP-only routers; RBAC + transactions in `offer_service`. Partner offer
management lives under the recruitment router; the **student-facing `/offers`** paths
match `API_CONTRACTS` exactly.

**Partner (recruitment router):**

| Endpoint | Method | Authz / body | Behavior |
| --- | --- | --- | --- |
| `/applications/{id}/offers` | POST | `create_offer`. Body `{ position_title, department?, start_date?, salary_amount?, salary_currency?, salary_period?, benefits_summary?, terms_notes?, expiry_date }` | Create the `draft` offer at the app's current ACTIVE stage. A second LIVE offer → `409 offer_exists`. App not `under_review` → `409 illegal_transition`. Encrypts `salary_amount`. Audited. Returns the partner offer view. |
| `/applications/{id}/offers` | GET | `create_offer`/`view` | List the application's offers (partner view; salary decrypted for the partner). |
| `/applications/{id}/offers/{offer_id}` | PATCH | `create_offer` + `version?` | Edit comp/terms/expiry **only while `draft`** (else `409 offer_not_editable`). Optimistic `version`. Audited. |
| `/offers/{offer_id}/submit` | POST | `create_offer` + `version?` | `draft → pending_approval`. Audited. |
| `/offers/{offer_id}/approve` | POST | `approve_offer` + `version?`. Body `{ decision: "approve"\|"reject" }` | `pending_approval → approved` (set `approved_by`/`approved_at`) or `→ draft` (reject-back). Audited. |
| `/offers/{offer_id}/send` | POST | `send_offer` + `version?` | `approved → sent` (`sent_at`). **`409 offer_not_approved`** if not `approved`; **`409 reveal_required`** for anonymous w/o accepted reveal (§5). Notifies candidate (`offer_received`). Audited. |
| `/offers/{offer_id}/rescind` | POST | `withdraw_offer` + `version?` | `{draft,pending_approval,approved,sent} → rescinded`. Notifies candidate only if it was `sent`. Audited. |

**Student (`/offers` router — matches `API_CONTRACTS`):**

| Endpoint | Method | Authz / body | Behavior |
| --- | --- | --- | --- |
| `/offers` | GET | applicant | List the student's own offers (only `sent`+terminal states are visible to the student; `draft`/`pending_approval`/`approved` are partner-internal and never listed). |
| `/offers/{id}` | GET | applicant (owner) | The student's own offer detail — **full comp** (salary decrypted; they are the owning student per §17). Non-owner → `404`. |
| `/offers/{id}/respond` | POST | applicant. Body `{ decision: "accepted"\|"declined", notes?, idempotency_key }` | §3. Only a `sent` (non-expired) offer. Accept → `hired` + career seam; decline → `declined`. Idempotent on `idempotency_key`. Lazy-expire check first. |

- **Board / candidate-detail surfacing:** `stage_service._pipeline_block` (current
  stage only, Offer stage) gains a partner-only `offer` block `{ id, status,
  expiry_date, sent_at }` (no salary on the board glance — open the offer detail to
  see comp). **Student projection:** the student application-detail surfaces their own
  offer summary `{ status, position_title, start_date, expiry_date, comp_summary }`
  when an offer is `sent`+terminal — never a draft/pending offer, never partner
  internals (`approved_by`, `decline_reason`).

### 9. Scope boundary + first implementation slice

**THIS ADR (ADR-0007) covers:** the `offers` table (migration `0015`); the 8-state
machine (draft→pending_approval→approved→sent→accepted|declined|expired|rescinded);
the internal partner approval gate + the four permission codes; student
accept/decline via `/offers/{id}/respond`; the lazy + `offer.expire_sweep`
expiry/expiring handling; the `applications.status='hired'` terminal outcome
(domain widening, no DDL) + `exit_kind='hired'`; the career-outcome trust_level=4
**seam** (event/audit, non-blocking); the reveal precondition on `send`; salary
Fernet encryption; offer notifications; the partner board offer block + the student
offer summary; audit on every write.

**Explicitly LATER (named so FKs/behaviors stay stable, design deferred):**

- **Counter-offer + request-extension** (PRD §11.4 "student propose ngược → partner
  accept/reject/counter") — its own state-machine extension (a `counter_offers`
  child table or an offer-thread); the `respond` schema is `accepted|declined` only
  in V1.
- **Offer-letter PDF / template autofill + upload** (PRD §11.4 "Upload offer letter
  template, system điền thông tin") and **e-signature** — `offer_letter_path`
  (encrypted) is **omitted** from the V1 table and added by the documents/letter ADR.
- **Offer comparison tool** (PRD §6 student side-by-side multi-offer compare) —
  frontend/data, reads this table; no backend change.
- **Payment / bank-transfer reconciliation** — out of scope (CLAUDE.md manual default;
  offers do not trigger payment).
- **Career-outcome materialization + university post-start confirmation
  (trust_level=1)** — data-engineer, consumes the `offer.accepted` event.
- **Separation-of-duties** on approve/send and richer approval chains.

**First implementation slice (backend-first) — for `backend-developer`:**

1. **Migration `0015_recruitment_offers`** — create `offers` (+ the PG-guarded
   partial-unique live-offer index + the `(org_id,status)`/`(application_id)`/
   `(stage_id)` indexes), upgrade **and** downgrade. Add the `Offer` ORM model. **No**
   `applications` DDL.
2. **Domain** — new `recruitment/domain/offer.py`: `OFFER_STATUSES`, the transition
   map (event → allowed-from → to), `TERMINAL`/`LIVE`/`EDITABLE` sets, the
   `respond` decision tokens, pure `can_transition(event, current)`; add `HIRED`
   to `lifecycle.STATUSES` + its label; add `'hired'` exit kind to `pipeline.py`. No I/O.
3. **Infra** — `recruitment/infrastructure/offer_salary_crypto.py`
   (`encrypt_salary`/`decrypt_salary`), mirroring `meeting_link_crypto.py`.
4. **Service** — new `recruitment/application/offer_service.py`: `create_offer`,
   `update_draft`, `submit_offer`, `approve_offer`, `send_offer` (reveal precondition),
   `rescind_offer`, `respond_offer` (accept → `hired` + close stage row + career seam;
   decline), `list_offers_partner`, `list_offers_student`, `get_offer_student`, and
   `sweep_offers(session, now)`. Reuse `decision_service._load_partner_application`
   (404), `stage_service._active_stage`/the stage-close helper, `write_audit`, the
   outbox/feed enqueue helpers; emit the `offer.accepted` outbox event + `application.hired`
   audit on accept.
5. **Errors / API** — add `OfferExistsError` (`offer_exists`), `OfferNotEditableError`
   (`offer_not_editable`), `OfferNotApprovedError` (`offer_not_approved`),
   `OfferNotActionableError` (`offer_not_actionable`) to `recruitment/application/errors.py`
   (reuse `RevealRequiredError`, `ApplicationVersionConflictError`,
   `IllegalApplicationTransitionError`). Add the seven partner endpoints (recruitment
   router) + the three student `/offers` endpoints (a new offers router) + Pydantic
   schemas (HTTP only); presenters for the partner offer view (salary decrypted for
   partner) and the student offer view (salary decrypted for the owner; partner
   internals stripped).
6. **Notifications** — add the six catalog/template entries (vi+en, **no salary in
   body**) + in-app feed types; register `offer.expire_sweep` (5 min) in
   `automation/scheduler/jobs.py`.
7. **Tests (SQLite, `tester-qa` gate):** create draft → second live offer → `409
   offer_exists`; edit allowed only in `draft` (`409 offer_not_editable` after submit);
   submit → pending_approval; approve / reject-back; **send before approve → `409
   offer_not_approved`**; **anonymous + no accepted reveal → send `409 reveal_required`**,
   reveal accepted → sends; rescind from each live state (notifies only if was `sent`);
   student respond accept → offer `accepted` + `applications.status='hired'` + Offer
   `candidate_stages` row closed `PASSED`/`exit_kind='hired'` + `offer.accepted` event
   emitted (career seam, no salary in payload); respond decline → `declined`, app stays
   `under_review`; respond by non-owner → `404`; respond to expired → `409
   offer_not_actionable`; lazy-expire on read; `offer.expire_sweep` flips past-expiry
   `sent → expired` + enqueues T-24h reminder exactly once (dedupe), idempotent on
   re-run; cross-org partner action → `404`; optimistic `version` conflict → `409`;
   idempotent `respond` replay; **PII** — `salary_amount` encrypted at rest, absent
   from every notification body + the board glance + the `offer.accepted` event;
   **student projection** carries no `approved_by`/`decline_reason`/draft offer; audit
   row per write.

**Frontend slice (follows, after the contract is green) — `frontend-developer`:**
partner candidate-detail "Create offer" drawer (comp fields, expiry; no `confirm()`),
the approve/send action states (a "send blocked — obtain reveal first" state on `409
reveal_required` deep-linking the reveal flow; "needs approval" on `409
offer_not_approved`); the partner board Offer-stage offer chip (status + expiry, no
salary); the student application-timeline **own-offer** card (position, comp summary,
start, deadline countdown, Accept/Decline with a double-confirm modal per PRD
"accept_offer (double confirm)"); honest empty/permission/conflict (409 stale/expired)
states. Mark `API wired` → `browser verified` → `E2E verified` distinctly.

## Consequences

- **Positive:** offers ship small on stable ADR-0004/0005/0006 FKs and reach the
  documented terminal positive outcome; `hired` lands as a pure domain widening (no
  `applications` DDL, no projection rewrite — `proj_partner_pipeline` already counts
  it); the approval gate is a single `send-requires-approved` rule that org-configured
  RBAC layers on top of; the reveal precondition keeps the handshake the only identity
  path; expiry reuses the proven ADR-0003 sweep+dedupe pattern; salary encryption
  reuses the ADR-0006 Fernet infra; the career-outcome trust_level=4 record is a
  non-blocking event seam so the offers slice doesn't wait on the career-outcomes
  module.
- **Cost / limits:** V1 is single-LIVE-offer-per-application (no parallel offers), no
  counter-offer / extension, no offer-letter PDF / e-signature, no SoD on
  approve/send, comp is structured-minimal (gross/net in the summary text), no payment
  integration. All are documented end-states, not V1 blockers.
- **Reversibility:** additive — dropping `0015`, the offer endpoints, the
  `offer.expire_sweep` job, and reverting the `lifecycle.HIRED` widening restores the
  ADR-0006 surface exactly. No data depends on `hired` until an offer is accepted.

## Doc conflicts resolved (precedence: product > business > security > arch > API/data)

1. **`offers.status` value-set.** `DATA_MODEL` §9 lists `draft | sent | accepted |
   declined | expired | withdrawn` — it omits the **approval** states and names the
   partner withdrawal `withdrawn`. **Resolved:** add `pending_approval` + `approved`
   (PRD §11.4 / role matrix mandate an internal approval before send), and **rename
   `withdrawn → rescinded`** so the offer's partner-initiated withdrawal does not
   collide with `applications.status='withdrawn'` (the *student*-initiated application
   withdrawal). **Flag `DATA_MODEL` §9 `offers.status`** to the 8-state set with
   `rescinded`.
2. **`offers.salary_amount INT` (encrypted at rest).** A Fernet ciphertext is a
   variable-length base64 **string**, not an `INT`. **Resolved:** store
   `salary_amount VARCHAR(255)` holding the ciphertext (decrypted only for
   recruiter/student). **Flag `DATA_MODEL` §9 `offers.salary_amount`** type
   `INT → VARCHAR (encrypted)`.
3. **`offers` missing `org_id` / `stage_id` / `approved_by` / `approved_at` /
   `sent_at`.** `DATA_MODEL` §9 has none. **Resolved:** add all five (`org_id`
   denormalized like `scorecards`/`interviews`; `stage_id` binds the offer to the
   Offer stage; the approval timestamps/actor record the gate). **Flag `DATA_MODEL`
   §9 `offers`** to add these columns.
4. **PRD role matrix lacks an `approve` action** (it lists `view, create, send,
   withdraw, counter`). **Resolved:** the approval gate is structural
   (`send` requires `status='approved'`); V1 adds permission codes `create_offer`,
   `approve_offer`, `send_offer`, `withdraw_offer` and does **not** enforce SoD. **Flag
   PRD §RBAC Offers** to add an explicit `approve` action; SoD + approval chains
   deferred.
5. **`offer_letter_path` (encrypted).** `DATA_MODEL` §9 has it. **Resolved:** offer-letter
   PDF/template autofill + upload is **deferred** (§9); the column is **omitted** in V1
   and added by the letter ADR. **Flag `DATA_MODEL` §9 `offers.offer_letter_path`** as
   deferred.
6. **Career-outcome on accept (`API_CONTRACTS` "trust_level = 4").** The
   `career_outcome_records` module may not be shipped. **Resolved:** accept emits a
   non-blocking `offer.accepted` outbox event + `application.hired` audit; the
   data-engineer materializer creates the `trust_level=4` row idempotently. **Flag
   `API_CONTRACTS` Offers** that the record is created via the event seam, not inline,
   until the module lands.
7. **Counter-offer / request-extension (PRD §11.4).** **Resolved/flagged:** deferred;
   `respond` is `accepted|declined` only in V1.
